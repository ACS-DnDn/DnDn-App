import json
import logging
import os
import shutil
import boto3
import subprocess
import threading
import time
from typing import Any
from github import Github

from .database import SessionLocal

logger = logging.getLogger(__name__)

# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")  # Legacy
# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")  # us-east-1
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "apac.anthropic.claude-3-5-sonnet-20241022-v2:0")
HAIKU_MODEL_ID = os.getenv(
    "BEDROCK_HAIKU_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)
REGION = os.getenv("AWS_REGION", "ap-northeast-2")

def _find_uvx() -> str:
    return (
        os.getenv("UVX_PATH")
        or shutil.which("uvx")
        or os.path.expanduser("~/.local/bin/uvx")
    )


# ─────────────────────────────────────────────────
# MCP Client (stdio transport)
# ─────────────────────────────────────────────────

class TerraformMCPClient:
    """awslabs.terraform-mcp-server와 stdio JSON-RPC 통신"""

    def __init__(self):
        self.proc = None
        self._req_id = 0
        self._lock = threading.Lock()

    def start(self):
        self.proc = subprocess.Popen(
            [_find_uvx(), "awslabs.terraform-mcp-server@latest"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # initialize 핸드셰이크
        self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dndn-report", "version": "1.0"},
            },
        })
        resp = self._read()
        # initialized 알림
        self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        return resp

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        resp = self._read()
        content = resp.get("result", {}).get("content", [])
        return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")

    def stop(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.terminate()
            self.proc = None

    def _next_id(self):
        with self._lock:
            self._req_id += 1
            return self._req_id

    def _send(self, obj: dict):
        line = json.dumps(obj) + "\n"
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def _read(self) -> dict:
        for _ in range(30):
            line = self.proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            try:
                obj = json.loads(line)
                if "id" in obj:
                    return obj
            except json.JSONDecodeError:
                continue
        return {}


# ─────────────────────────────────────────────────
# GitHub .tf 수집
# ─────────────────────────────────────────────────

_MAX_EXISTING_TF_CHARS = 40_000  # 이 크기 이상이면 Haiku 요약 적용


def _summarize_tf_code(tf_text: str) -> str:
    """기존 .tf 코드가 클 때 Haiku로 구조 요약. 리소스명/변수명/모듈 구조 보존."""
    if len(tf_text) <= _MAX_EXISTING_TF_CHARS:
        return tf_text
    logger.info("[Haiku] 기존 .tf 코드 요약 시작 (%d자)", len(tf_text))
    try:
        client = boto3.client("bedrock-runtime", region_name=REGION)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "system": (
                "당신은 Terraform 코드 분석 전문가입니다. "
                "다음 기존 Terraform 코드를 분석하여 새 코드 생성 시 충돌을 방지할 수 있도록 요약하세요.\n\n"
                "반드시 포함할 항목:\n"
                "- 모든 resource/data/module 블록의 타입과 이름 (예: resource \"aws_instance\" \"web\")\n"
                "- 모든 variable/output/local 이름과 타입\n"
                "- provider 설정과 backend 설정\n"
                "- 네이밍 컨벤션 패턴 (접두사, 태그 구조 등)\n"
                "- 리소스 간 참조 관계 (depends_on, 변수 참조)\n\n"
                "코드 전체를 복사하지 말고, 위 항목을 구조화된 목록으로 정리하세요."
            ),
            "messages": [{"role": "user", "content": tf_text}],
        }
        response = client.invoke_model(
            modelId=HAIKU_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        result = json.loads(response["body"].read())
        summary = result["content"][0]["text"]
        logger.info("[Haiku] 기존 .tf 코드 요약 완료 (%d자 → %d자)", len(tf_text), len(summary))
        return summary
    except Exception as e:
        logger.warning("[Haiku] .tf 요약 실패, truncate 폴백: %s", e)
        return tf_text[:_MAX_EXISTING_TF_CHARS] + "\n... (truncated)"


def load_tf_from_github(repo_name: str, token: str | None = None) -> str:
    g = Github(token) if token else Github()
    repo = g.get_repo(repo_name)
    tf_files = []
    contents = repo.get_contents("")
    while contents:
        f = contents.pop(0)
        if f.type == "dir":
            contents.extend(repo.get_contents(f.path))
        elif f.name.endswith(".tf"):
            tf_files.append(f"# === {f.path} ===\n{f.decoded_content.decode()}")
    raw = "\n\n".join(tf_files)
    return _summarize_tf_code(raw)


# ─────────────────────────────────────────────────
# MCP 컨텍스트 조회
# ─────────────────────────────────────────────────

def _extract_resource_hint(workplan: dict) -> str:
    """작업계획서에서 AWS 리소스 타입 추출"""
    title = workplan.get("title", "").lower()
    steps_text = " ".join(
        s.get("description", "") for s in workplan.get("steps", [])
    ).lower()
    combined = title + " " + steps_text

    resource_map = {
        "eks": "aws_eks_cluster",
        "lambda": "aws_lambda_function",
        "rds": "aws_db_instance",
        "ec2": "aws_instance",
        "s3": "aws_s3_bucket",
        "waf": "aws_wafv2_web_acl",
        "alb": "aws_lb",
        "vpc": "aws_vpc",
        "iam": "aws_iam_role",
        "cloudwatch": "aws_cloudwatch_metric_alarm",
        "certificate": "aws_acm_certificate",
        "인증서": "aws_acm_certificate",
        "인스턴스": "aws_instance",
        "클러스터": "aws_eks_cluster",
        "런타임": "aws_lambda_function",
    }
    for keyword, resource in resource_map.items():
        if keyword in combined:
            return resource
    return ""


def _fetch_mcp_context(workplan: dict) -> dict:
    """MCP 서버에서 AWS Provider 문서 + Best Practices 조회"""
    context = {"aws_docs": "", "best_practices": ""}

    mcp = TerraformMCPClient()
    try:
        mcp.start()
        resource_hint = _extract_resource_hint(workplan)

        # AWS Provider 문서 조회
        if resource_hint:
            docs = mcp.call_tool("SearchAwsProviderDocs", {"asset": resource_hint})
            context["aws_docs"] = docs[:3000] if docs else ""
            print(f"[MCP] AWS 문서 조회 완료: {resource_hint} ({len(context['aws_docs'])}자)")

        # AWS AWSCC Provider 문서도 조회 (best practices 대체)
        if resource_hint:
            awscc_hint = resource_hint.replace("aws_", "awscc_", 1)
            awscc = mcp.call_tool("SearchAwsccProviderDocs", {"asset": awscc_hint})
            context["best_practices"] = awscc[:2000] if awscc else ""
            print(f"[MCP] AWSCC Provider 문서 조회 완료 ({len(context['best_practices'])}자)")

    except Exception as e:
        print(f"[MCP] 컨텍스트 조회 실패 (계속 진행): {e}")
    finally:
        mcp.stop()

    return context


def _run_checkov_scan(files: list) -> dict:
    """생성된 .tf 파일 Checkov 보안 스캔"""
    import tempfile, os

    if not files:
        return {}

    checkov_result = {}
    mcp = TerraformMCPClient()
    try:
        mcp.start()
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files:
                # path traversal 방지: basename만 허용, .tf 확장자 강제
                safe_name = os.path.basename(f.get("filename", "main.tf"))
                if not safe_name.endswith(".tf"):
                    safe_name = safe_name + ".tf"
                with open(os.path.join(tmpdir, safe_name), "w") as fp:
                    fp.write(f.get("content", ""))

            result = mcp.call_tool("RunCheckovScan", {
                "working_directory": tmpdir,
                "framework": "terraform",
                "output_format": "json",
            })
            if result:
                try:
                    parsed = json.loads(result)
                    # Checkov는 리스트([{...}]) 또는 단일 dict로 반환
                    if isinstance(parsed, list):
                        parsed = parsed[0] if parsed else {}
                    summary = parsed.get("summary", {})
                    passed = summary.get("passed", 0)
                    failed = summary.get("failed", 0)
                    checkov_result = {
                        "summary": {"passed": passed, "failed": failed},
                        "failed_checks": parsed.get("results", {}).get("failed_checks", []),
                    }
                    print(f"[MCP] Checkov 스캔 완료 — passed: {passed}, failed: {failed}")
                except (json.JSONDecodeError, KeyError, IndexError):
                    checkov_result = {"raw": result[:500]}

    except Exception as e:
        print(f"[MCP] Checkov 스캔 실패 (계속 진행): {e}")
        checkov_result = {"error": str(e)}
    finally:
        mcp.stop()

    return checkov_result


# ─────────────────────────────────────────────────
# OPA 정책 조회 (DB)
# ─────────────────────────────────────────────────

def _load_opa_policies(workspace_id: str) -> list[dict]:
    """workspaces 테이블의 opa_settings JSON 컬럼에서 정책을 읽는다."""
    from sqlalchemy import text

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT opa_settings FROM workspaces WHERE id = :ws_id"),
            {"ws_id": workspace_id},
        ).fetchone()
        if not row or not row[0]:
            return []
        settings = row[0] if isinstance(row[0], list) else json.loads(row[0])
        return settings
    except Exception as e:
        logger.warning("OPA 정책 조회 실패 (계속 진행): %s", e)
        return []
    finally:
        db.close()


def _format_opa_for_prompt(policies: list[dict]) -> str:
    """OPA 정책을 Bedrock 프롬프트에 삽입할 자연어 제약조건 텍스트로 변환한다."""
    if not policies:
        return ""

    lines = []
    for category in policies:
        cat_name = category.get("category", "")
        items = category.get("items", [])
        active_items = [it for it in items if it.get("on")]
        if not active_items:
            continue

        lines.append(f"\n### {cat_name}")
        for item in active_items:
            severity = item.get("severity", "warn").upper()
            label = item.get("label", "")
            line = f"- [{severity}] {label}"

            params = item.get("params")
            if params:
                p_type = params.get("type")
                if p_type == "list":
                    values = params.get("values", [])
                    if values:
                        line += f" (허용 값: {', '.join(values)})"
                elif p_type == "number":
                    line += f" (최소값: {params.get('value', '')} {params.get('unit', '')})"
                elif p_type == "services":
                    values = params.get("values", [])
                    if values:
                        line += f" (적용 서비스: {', '.join(values)})"

            exceptions = item.get("exceptions", [])
            if exceptions:
                line += f" — 예외: {', '.join(exceptions)}"

            lines.append(line)

    if not lines:
        return ""

    return "\n".join(lines)


# ─────────────────────────────────────────────────
# Bedrock 호출
# ─────────────────────────────────────────────────

_MAX_PROMPT_CHARS = 150_000  # Bedrock 프롬프트 전체 최대 크기


def _build_deploy_log_section(deploy_log: list[dict] | None) -> str:
    """이전 배포 실패 이력을 프롬프트 섹션으로 변환"""
    if not deploy_log:
        return ""
    failures = [e for e in deploy_log if e.get("status") == "failure"]
    if not failures:
        return ""
    lines = []
    for e in failures:
        event_labels = {
            "checks_failed": "PR 검증 실패",
            "apply_failed": "Terraform Apply 실패",
        }
        label = event_labels.get(e.get("event", ""), e.get("event", ""))
        desc = e.get("description", "")
        ctx_name = e.get("context", "")
        line = f"- [{label}]"
        if ctx_name:
            line += f" ({ctx_name})"
        if desc:
            line += f": {desc}"
        lines.append(line)
    return "\n## 이전 배포 실패 이력 (반드시 참고하여 동일 원인이 재발하지 않도록 수정하세요)\n" + "\n".join(lines) + "\n"


def _build_user_prompt(workplan_json: str, existing_tf: str, aws_docs_section: str,
                       best_practices_section: str, opa_section: str,
                       deploy_log_section: str = "") -> str:
    return f"""
## 작업계획서
{workplan_json}

## 기존 테라폼 코드 (스타일/컨벤션 참고)
{existing_tf}
{aws_docs_section}
{best_practices_section}
{opa_section}
{deploy_log_section}

위 내용을 모두 반영하여 바로 apply 가능한 테라폼 코드를 생성해주세요.

다음 JSON 형식으로 반환하세요:
{{
  "files": [
    {{
      "filename": "파일명.tf",
      "content": "테라폼 코드 전체 내용"
    }}
  ],
  "summary": "생성된 코드 설명 (한국어, 2~3문장)"
}}
""".strip()


def _call_bedrock(workplan: dict, existing_tf: str, mcp_context: dict, opa_text: str = "", deploy_log: list[dict] | None = None) -> dict:
    client = boto3.client("bedrock-runtime", region_name=REGION)

    aws_docs_section = (
        f"\n## AWS Provider 공식 문서 (MCP 실시간 조회)\n{mcp_context['aws_docs']}\n"
        if mcp_context.get("aws_docs") else ""
    )
    best_practices_section = (
        f"\n## AWS Terraform Best Practices (MCP)\n{mcp_context['best_practices']}\n"
        if mcp_context.get("best_practices") else ""
    )

    opa_rule = ""
    opa_section = ""
    if opa_text:
        opa_rule = "\n5. 워크스페이스 인프라 정책(OPA)을 반드시 준수하세요. BLOCK 정책 위반 시 해당 리소스 설정을 정책에 맞게 수정하세요."
        opa_section = f"\n## 워크스페이스 인프라 정책 (OPA)\n아래 정책을 반드시 준수하여 코드를 생성하세요. BLOCK은 필수 준수, WARN은 권고 사항입니다.\n{opa_text}\n"

    system = f"""
당신은 AWS 인프라 테라폼 코드 전문가입니다.
작업계획서, 기존 테라폼 코드, AWS 공식 문서를 분석하여 바로 apply 가능한 테라폼 코드를 생성하세요.

규칙:
1. 기존 코드의 네이밍 컨벤션, 변수 스타일, 태그 구조를 반드시 따르세요
2. AWS Provider 공식 문서의 최신 argument를 사용하세요
3. AWS Best Practices를 반드시 준수하세요
4. Checkov 보안 스캔을 통과할 수 있도록 보안 설정을 포함하세요{opa_rule}
6. 반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요
""".strip()

    # workplan에서 Terraform 생성에 불필요한 대용량 필드 제거
    _STRIP_KEYS = {"aws_docs", "ref_docs", "ref_doc_contents"}
    workplan_slim = {k: v for k, v in workplan.items() if k not in _STRIP_KEYS}
    workplan_json = json.dumps(workplan_slim, ensure_ascii=False, indent=2)
    # workplan_json도 너무 크면 truncate
    _MAX_WORKPLAN_CHARS = 30_000
    if len(workplan_json) > _MAX_WORKPLAN_CHARS:
        logger.warning("workplan_json 축소: %d → %d자", len(workplan_json), _MAX_WORKPLAN_CHARS)
        workplan_json = workplan_json[:_MAX_WORKPLAN_CHARS] + "\n... (truncated)"

    deploy_log_section = _build_deploy_log_section(deploy_log)

    # 프롬프트 크기 안전장치: existing_tf부터 순차 축소
    user = _build_user_prompt(workplan_json, existing_tf, aws_docs_section, best_practices_section, opa_section, deploy_log_section)
    total = len(system) + len(user)
    if total > _MAX_PROMPT_CHARS:
        over = total - _MAX_PROMPT_CHARS
        existing_tf = existing_tf[: max(0, len(existing_tf) - over)]
        user = _build_user_prompt(workplan_json, existing_tf, aws_docs_section, best_practices_section, opa_section, deploy_log_section)
        logger.warning("프롬프트 축소: %d → %d자", total, len(system) + len(user))

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    clean = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(clean, strict=False)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답 JSON 파싱 실패: {e}\n원문: {clean[:200]}") from e


# ─────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────

def generate_terraform_code(
    workplan: dict,
    repo_name: str,
    github_token: str = None,
    workspace_id: str | None = None,
    deploy_log: list[dict] | None = None,
) -> dict:
    """
    작업계획서 + OPA 정책 + MCP(AWS Provider 문서 + Checkov) → 테라폼 코드 생성

    흐름:
    1. GitHub .tf 수집 (기존 스타일 학습)
    2. DB에서 워크스페이스 OPA 정책 조회
    3. MCP로 AWS Provider 문서 + Best Practices 조회
    4. Bedrock으로 코드 생성 (OPA 정책 포함)
    5. MCP Checkov로 보안 스캔
    """
    print("[1/5] GitHub .tf 코드 수집 중...")
    existing_tf = load_tf_from_github(repo_name, github_token)

    opa_text = ""
    if workspace_id:
        print("[2/5] DB에서 OPA 정책 조회 중...")
        opa_policies = _load_opa_policies(workspace_id)
        opa_text = _format_opa_for_prompt(opa_policies)
        if opa_text:
            print(f"[2/5] OPA 정책 {sum(len(c.get('items', [])) for c in opa_policies)}개 항목 로드 완료")
        else:
            print("[2/5] 활성화된 OPA 정책 없음")
    else:
        print("[2/5] workspace_id 없음 — OPA 정책 스킵")

    print("[3/5] MCP로 AWS 문서 조회 중...")
    mcp_context = _fetch_mcp_context(workplan)

    print("[4/5] Bedrock으로 코드 생성 중...")
    generated = _call_bedrock(workplan, existing_tf, mcp_context, opa_text, deploy_log=deploy_log)

    print("[5/5] MCP Checkov 보안 스캔 중...")
    checkov_result = _run_checkov_scan(generated.get("files", []))

    return {**generated, "checkov": checkov_result}
