"""
OPA 정책 엔진 — python-hcl2로 .tf 파싱 + 동적 .rego 생성 + opa eval 실행
"""

import io
import json
import logging
import os
import subprocess
import tempfile

import hcl2

logger = logging.getLogger(__name__)

OPA_BIN = os.getenv("OPA_BIN", "opa")


# ─────────────────────────────────────────────────
# 1. HCL → JSON 파싱
# ─────────────────────────────────────────────────

def parse_tf_files(files_map: dict[str, str]) -> dict:
    """여러 .tf 파일 내용을 python-hcl2로 파싱 → 단일 JSON 구조로 병합"""
    merged: dict = {}
    for fname, content in files_map.items():
        try:
            parsed = hcl2.load(io.StringIO(content))
        except Exception as e:
            logger.warning("HCL 파싱 실패 (%s): %s", fname, e)
            continue
        for key, val in parsed.items():
            if key in merged:
                if isinstance(merged[key], list) and isinstance(val, list):
                    merged[key].extend(val)
                elif isinstance(merged[key], list):
                    merged[key].append(val)
                else:
                    merged[key] = [merged[key], val] if not isinstance(val, list) else [merged[key], *val]
            else:
                merged[key] = val
    return merged


# ─────────────────────────────────────────────────
# 2. DB opa_settings → .rego 정책 생성
# ─────────────────────────────────────────────────

_REGO_HEADER = """\
package dndn

import rego.v1

violations contains result if {
    false  # 기본: 위반 없음 (아래 규칙들이 추가)
}
"""


def _rego_set(values: list[str]) -> str:
    """Python 리스트 → Rego set 리터럴"""
    items = ", ".join(f'"{v}"' for v in values)
    return "{" + items + "}"


def _rego_set_lower(values: list[str]) -> str:
    items = ", ".join(f'"{v.lower()}"' for v in values)
    return "{" + items + "}"


def generate_rego(policies: list[dict]) -> str:
    """DB opa_settings에서 .rego 정책 파일 동적 생성"""
    rules: list[str] = []

    for category in policies:
        for item in category.get("items", []):
            if not item.get("on"):
                continue
            key = item.get("key", "")
            severity = item.get("severity", "warn")
            label = item.get("label", "")
            params = item.get("params")

            rule = _generate_rule(key, severity, label, params)
            if rule:
                rules.append(rule)

    if not rules:
        return _REGO_HEADER

    header = """\
package dndn

import rego.v1

"""
    return header + "\n\n".join(rules) + "\n"


def _generate_rule(key: str, severity: str, label: str, params: dict | None) -> str | None:
    """정책 키별 .rego 규칙 생성"""
    sev = f'"{severity}"'
    lbl = f'"{label}"'

    # ── 네트워크 보안 ──
    if key == "net-sg-open":
        allowed = _rego_set(params["values"]) if params and params.get("values") else '{"10.0.0.0/8", "172.16.0.0/12"}'
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_security_group"
    some name, config in instances
    some j
    ingress := config.ingress[j]
    some cidr in ingress.cidr_blocks
    not cidr in {allowed}
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("보안그룹 '%s'의 ingress에 허용되지 않은 CIDR %s", [name, cidr])}}
}}"""

    if key == "net-rds-public":
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_db_instance"
    some name, config in instances
    config.publicly_accessible == true
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("RDS '%s'에 퍼블릭 접근이 활성화됨", [name])}}
}}"""

    if key == "net-flow-log":
        return f"""\
# {label}
_has_flow_log contains vpc_id if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_flow_log"
    some _, config in instances
    vpc_id := config.vpc_id
}}

violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_vpc"
    some name, _ in instances
    not name in _has_flow_log
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("VPC '%s'에 Flow Log가 없습니다", [name])}}
}}"""

    # ── IAM 보안 ──
    if key == "iam-wildcard":
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt in {{"aws_iam_policy", "aws_iam_role_policy", "aws_iam_user_policy", "aws_iam_group_policy"}}
    some name, config in instances
    policy_str := config.policy
    contains(policy_str, "\\"Action\\": \\"*\\"")
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("IAM 정책 '%s'에 와일드카드(*) Action 사용", [name])}}
}}

violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt in {{"aws_iam_policy", "aws_iam_role_policy", "aws_iam_user_policy", "aws_iam_group_policy"}}
    some name, config in instances
    policy_str := config.policy
    contains(policy_str, "\\"Resource\\": \\"*\\"")
    contains(policy_str, "\\"Effect\\": \\"Allow\\"")
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("IAM 정책 '%s'에 와일드카드(*) Resource + Allow 사용", [name])}}
}}"""

    if key == "iam-admin-attach":
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt in {{"aws_iam_role_policy_attachment", "aws_iam_user_policy_attachment", "aws_iam_group_policy_attachment"}}
    some name, config in instances
    contains(config.policy_arn, "AdministratorAccess")
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("'%s'에 AdministratorAccess 정책 직접 연결", [name])}}
}}"""

    if key == "iam-boundary":
        return None  # Permission Boundary 체크는 복잡 — 향후 구현

    # ── 스토리지 보안 ──
    if key == "stor-s3-public":
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_s3_bucket"
    some name, config in instances
    config.acl == "public-read"
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("S3 버킷 '%s'에 public-read ACL 설정", [name])}}
}}

violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_s3_bucket_public_access_block"
    some name, config in instances
    config.block_public_acls == false
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("S3 '%s' public access block이 비활성화됨", [name])}}
}}"""

    if key == "stor-s3-encrypt":
        return f"""\
# {label}
_has_s3_encryption contains bucket_name if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_s3_bucket_server_side_encryption_configuration"
    some bucket_name, _ in instances
}}

violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_s3_bucket"
    some name, _ in instances
    not name in _has_s3_encryption
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("S3 버킷 '%s'에 암호화 설정 없음", [name])}}
}}"""

    if key == "stor-rds-encrypt":
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_db_instance"
    some name, config in instances
    not config.storage_encrypted
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("RDS '%s'의 스토리지 암호화가 비활성화됨", [name])}}
}}"""

    if key == "stor-ebs-encrypt":
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_ebs_volume"
    some name, config in instances
    not config.encrypted
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("EBS 볼륨 '%s'이 암호화되지 않음", [name])}}
}}"""

    # ── 컴퓨팅 제어 ──
    if key == "comp-ec2-public-ip":
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_instance"
    some name, config in instances
    config.associate_public_ip_address == true
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("EC2 '%s'에 퍼블릭 IP 자동 할당 활성화", [name])}}
}}"""

    if key == "comp-instance":
        if not params or not params.get("values"):
            return None
        allowed = _rego_set(params["values"])
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_instance"
    some name, config in instances
    not config.instance_type in {allowed}
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("EC2 '%s'의 인스턴스 타입 '%s'이 허용 목록에 없음", [name, config.instance_type])}}
}}"""

    if key == "comp-tag":
        if not params or not params.get("values"):
            return None
        required_tags = params["values"]
        tag_rules = []
        for tag in required_tags:
            tag_rules.append(f"""\
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt in {{"aws_instance", "aws_s3_bucket", "aws_db_instance", "aws_vpc", "aws_subnet", "aws_security_group", "aws_lb", "aws_eks_cluster", "aws_lambda_function"}}
    some name, config in instances
    not config.tags["{tag}"]
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("리소스 '%s.%s'에 필수 태그 '{tag}' 누락", [rt, name])}}
}}""")
        return f"# {label}\n" + "\n\n".join(tag_rules)

    # ── 로깅 / 모니터링 ──
    if key == "log-cloudtrail":
        return f"""\
# {label}
# CloudTrail은 보통 코드에 포함 — 존재 여부만 체크
_has_cloudtrail if {{
    some i
    resource_block := input.resource[i]
    some rt, _ in resource_block
    rt == "aws_cloudtrail"
}}

violations contains result if {{
    not _has_cloudtrail
    count(input.resource) > 0
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": "Terraform 코드에 CloudTrail 리소스가 없습니다"}}
}}"""

    # ── 비용 관리 ──
    if key == "cost-region":
        if not params or not params.get("values"):
            return None
        allowed = _rego_set(params["values"])
        return f"""\
# {label}
violations contains result if {{
    some i
    provider_block := input.provider[i]
    some provider_name, config in provider_block
    provider_name == "aws"
    not config.region in {allowed}
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("provider의 리전 '%s'이 허용 목록에 없음. 허용: {', '.join(params['values'])}", [config.region])}}
}}"""

    # ── 가용성 ──
    if key == "avail-multi-az":
        if not params or not params.get("values"):
            return None
        services = [s.lower() for s in params["values"]]
        rules = []
        if "rds" in services:
            rules.append(f"""\
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_db_instance"
    some name, config in instances
    not config.multi_az
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("RDS '%s'에 Multi-AZ가 비활성화됨", [name])}}
}}""")
        if "elasticache" in services:
            rules.append(f"""\
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_elasticache_replication_group"
    some name, config in instances
    config.automatic_failover_enabled == false
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("ElastiCache '%s'에 자동 장애조치가 비활성화됨", [name])}}
}}""")
        if "aurora" in services:
            rules.append(f"""\
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_rds_cluster"
    some name, config in instances
    count(config.availability_zones) < 2
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("Aurora 클러스터 '%s'의 AZ가 2개 미만", [name])}}
}}""")
        if not rules:
            return None
        return f"# {label}\n" + "\n\n".join(rules)

    if key == "avail-backup":
        min_days = params.get("value", 7) if params else 7
        return f"""\
# {label}
violations contains result if {{
    some i
    resource_block := input.resource[i]
    some rt, instances in resource_block
    rt == "aws_db_instance"
    some name, config in instances
    config.backup_retention_period < {min_days}
    result := {{"severity": {sev}, "key": "{key}", "label": {lbl}, "detail": sprintf("RDS '%s'의 백업 보존 기간이 %d일 미만 (최소 {min_days}일)", [name, config.backup_retention_period])}}
}}"""

    logger.debug("알 수 없는 OPA 정책 키: %s — 스킵", key)
    return None


# ─────────────────────────────────────────────────
# 3. OPA 실행
# ─────────────────────────────────────────────────

def run_opa_eval(rego_content: str, input_data: dict) -> list[dict]:
    """opa eval 바이너리로 .rego 정책 평가 → 위반 목록 반환"""
    with tempfile.TemporaryDirectory() as tmpdir:
        rego_path = os.path.join(tmpdir, "policy.rego")
        input_path = os.path.join(tmpdir, "input.json")

        with open(rego_path, "w", encoding="utf-8") as f:
            f.write(rego_content)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(input_data, f, ensure_ascii=False)

        try:
            result = subprocess.run(
                [OPA_BIN, "eval", "-d", rego_path, "-i", input_path,
                 "--format", "json", "data.dndn.violations"],
                capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError:
            logger.error("OPA 바이너리를 찾을 수 없습니다 (OPA_BIN=%s)", OPA_BIN)
            raise RuntimeError("OPA 바이너리가 설치되지 않았습니다. `opa` 명령이 PATH에 있는지 확인하세요.")
        except subprocess.TimeoutExpired:
            raise RuntimeError("OPA 평가 타임아웃 (30초)")

        if result.returncode != 0:
            logger.error("OPA eval 실패: %s", result.stderr)
            raise RuntimeError(f"OPA eval 오류: {result.stderr[:500]}")

        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.error("OPA 출력 파싱 실패: %s", result.stdout[:500])
            raise RuntimeError("OPA 출력을 JSON으로 파싱할 수 없습니다")

        # OPA eval 결과: {"result": [{"expressions": [{"value": [...], ...}]}]}
        violations = []
        for r in output.get("result", []):
            for expr in r.get("expressions", []):
                val = expr.get("value", [])
                if isinstance(val, list):
                    violations.extend(val)
                elif isinstance(val, set):
                    violations.extend(list(val))
        return violations


# ─────────────────────────────────────────────────
# 4. 통합 평가 함수
# ─────────────────────────────────────────────────

def evaluate_opa_policies(
    files_map: dict[str, str],
    policies: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    .tf 파일 + DB 정책 → OPA 평가 → (blocks, warns) 반환

    Returns:
        (blocks, warns) — 각각 {"key", "label", "detail"} 딕셔너리 리스트
    """
    if not policies:
        return [], []

    # 1. HCL 파싱
    tf_json = parse_tf_files(files_map)
    if not tf_json:
        logger.warning("HCL 파싱 결과가 비어있습니다 — OPA 스킵")
        return [], []

    # 2. .rego 생성
    rego_content = generate_rego(policies)
    if "violations" not in rego_content:
        return [], []

    # 3. OPA 실행
    violations = run_opa_eval(rego_content, tf_json)

    # 4. severity별 분류
    blocks = []
    warns = []
    for v in violations:
        entry = {
            "key": v.get("key", ""),
            "label": v.get("label", ""),
            "detail": v.get("detail", ""),
        }
        if v.get("severity") == "block":
            blocks.append(entry)
        else:
            warns.append(entry)

    return blocks, warns
