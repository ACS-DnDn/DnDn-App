import json
import boto3
import subprocess
import threading
import time
import os
import shutil

# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")  # Legacy
# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")  # us 전용
MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID", "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
)
REGION = os.getenv("AWS_REGION", "ap-northeast-2")


def _find_uvx() -> str:
    """uvx 실행 경로 자동 탐지 (환경변수 → PATH → 기본 경로 순)"""
    return (
        os.getenv("UVX_PATH")
        or shutil.which("uvx")
        or os.path.expanduser("~/.local/bin/uvx")
    )


# ─────────────────────────────────────────────────
# MCP Client (AWS Documentation MCP)
# ─────────────────────────────────────────────────


class AWSDocsMCPClient:
    """awslabs.aws-documentation-mcp-server와 stdio JSON-RPC 통신"""

    def __init__(self):
        self.proc = None
        self._req_id = 0
        self._lock = threading.Lock()

    def start(self):
        self.proc = subprocess.Popen(
            [_find_uvx(), "awslabs.aws-documentation-mcp-server@latest"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={**os.environ, "FASTMCP_LOG_LEVEL": "ERROR"},
        )
        self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "dndn-report", "version": "1.0"},
                },
            }
        )
        self._read()
        self._send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        req_id = self._next_id()
        self._send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        )
        resp = self._read()
        content = resp.get("result", {}).get("content", [])
        return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")

    def stop(self):
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
            except Exception:
                pass
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
# 이벤트 타입 → AWS 문서 검색 쿼리 매핑
# ─────────────────────────────────────────────────

EVENT_SEARCH_MAP = {
    "AWS_EKS_PLANNED_LIFECYCLE_EVENT": "EKS cluster version upgrade Kubernetes migration guide",
    "AWS_LAMBDA_RUNTIME_DEPRECATION_SCHEDULED": "Lambda runtime deprecation python upgrade migration",
    "AWS_RDS_CERTIFICATE_ROTATION_REQUIRED": "RDS SSL TLS certificate rotation CA update",
    "AWS_EC2_INSTANCE_STOP_SCHEDULED": "EC2 instance scheduled maintenance stop",
    "AWS_GUARDDUTY_RUNTIME_FINDING": "GuardDuty finding remediation security",
    "SOFTWARE_VULNERABILITY": "Security Hub finding vulnerability remediation patch",
    "AWS_CONFIG_RULE_NONCOMPLIANT": "AWS Config rule compliance remediation",
}


def _fetch_aws_docs_by_query(query: str) -> str:
    """쿼리 직접 지정해서 AWS Documentation MCP 조회 (S3 캐시 24h TTL)"""
    if not query:
        return ""
    from .s3_client import get_mcp_docs_cache, set_mcp_docs_cache

    cached = get_mcp_docs_cache(query)
    if cached is not None:
        print(f"[MCP] S3 캐시 HIT: '{query}'")
        return cached
    mcp = AWSDocsMCPClient()
    try:
        mcp.start()
        result = mcp.call_tool("search_documentation", {"search_phrase": query})
        docs = result if result else ""
        print(f"[MCP] AWS 문서 조회 완료: '{query}' ({len(docs)}자)")
        set_mcp_docs_cache(query, docs)
        return docs
    except Exception as e:
        print(f"[MCP] AWS 문서 조회 실패 (계속 진행): {e}")
        return ""
    finally:
        mcp.stop()


def _fetch_aws_docs(event_type_code: str = "", service: str = "") -> str:
    """AWS Documentation MCP로 관련 문서 조회 (캐싱 적용)"""
    query = EVENT_SEARCH_MAP.get(event_type_code, "")
    if not query and service:
        query = f"AWS {service} best practices guide"
    if not query:
        return ""
    return _fetch_aws_docs_by_query(query)


def _detect_event_info(data: dict) -> tuple[str, str]:
    """데이터에서 eventTypeCode, service 추출"""
    try:
        # Health raw JSON
        if data.get("source") == "aws.health":
            return (
                data.get("detail", {}).get("eventTypeCode", ""),
                data.get("detail", {}).get("service", ""),
            )
        # Health 보고서 데이터 구조
        if data.get("이벤트_상세", {}).get("이벤트_유형_코드"):
            code = data["이벤트_상세"]["이벤트_유형_코드"]
            service = code.split("_")[1] if "_" in code else ""
            return code, service
        # Health canonical (resources[].extensions.aws_health)
        aws_health = (
            data.get("resources", [{}])[0].get("extensions", {}).get("aws_health", {})
        )
        if aws_health:
            return (
                aws_health.get("event_type_code", ""),
                aws_health.get("service", ""),
            )
        # SecurityHub canonical
        findings = (
            data.get("resources", [{}])[0]
            .get("extensions", {})
            .get("security_finding", {})
        )
        if findings:
            return "SOFTWARE_VULNERABILITY", "SecurityHub"
    except Exception:
        pass
    # 주간/이벤트 보고서 ai_summary → action_items 카테고리로 서비스 추출
    ai_summary = data.get("ai_summary", {})
    if ai_summary:
        items = ai_summary.get("action_items", [])
        categories = list(
            set(i.get("category", "") for i in items if i.get("category"))
        )
        if categories:
            return "", " ".join(categories)
    # events 배열이 있는 경우 (주간 보고서)
    events = data.get("events", [])
    if events:
        first = events[0] if events else {}
        code = first.get("eventTypeCode", "") or first.get("type", "")
        service = first.get("service", "")
        return code, service
    return "", ""


# ─────────────────────────────────────────────────
# 공통 HTML 템플릿 CSS (DnDn 디자인 시스템)
# ─────────────────────────────────────────────────

_BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; font-size: 13px; line-height: 1.65; color: #1a1a1a; background: #f4f6f9; }
.doc { background: #fff; max-width: 860px; margin: 32px auto; padding: 36px 44px 52px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-radius: 4px; }
.doc-header { display: flex; flex-direction: column; gap: 10px; padding-bottom: 10px; border-bottom: 3px solid #1f3864; margin-bottom: 20px; }
.doc-header-top { display: flex; justify-content: space-between; align-items: center; }
.doc-header-logo { height: 28px; width: auto; display: block; }
.doc-header-title { font-size: 23px; font-weight: 800; color: #1f3864; text-align: center; line-height: 1.4; }
.doc-header-meta { text-align: right; font-size: 11px; color: #666; line-height: 1.75; }
.section { margin-bottom: 20px; }
.section-title { background: #1f3864; color: #fff; font-size: 12.5px; font-weight: 700; padding: 6px 12px; letter-spacing: 0.3px; margin-bottom: 7px; }
.sub-title { font-size: 12px; font-weight: 700; color: #333; margin: 14px 0 8px; padding-left: 2px; }
.sub-heading { background: #edf0f7; color: #1f3864; font-size: 12px; font-weight: 700; padding: 5px 10px; margin: 16px 0 7px; border-left: 3px solid #1f3864; }
.tbl-info { width: 100%; border-collapse: collapse; border: 1px solid #bbb; margin-bottom: 22px; }
.tbl-info th { padding: 7px 11px; background: #d4dae6; font-size: 12.5px; font-weight: 600; color: #1f3864; text-align: center; border: 1px solid #bbb; white-space: nowrap; vertical-align: middle; width: 110px; }
.tbl-info td { padding: 7px 11px; border: 1px solid #bbb; color: #1a1a1a; vertical-align: middle; font-size: 12.5px; text-align: center; }
.tbl-info .td-main { font-weight: 700; font-size: 13px; }
.tbl { width: 100%; border-collapse: collapse; border: 1px solid #bbb; font-size: 12.5px; }
.tbl th { padding: 7px 11px; background: #d4dae6; font-weight: 600; color: #1f3864; border: 1px solid #bbb; text-align: center; vertical-align: middle; white-space: nowrap; }
.tbl td { padding: 7px 11px; border: 1px solid #bbb; color: #1a1a1a; vertical-align: top; line-height: 1.65; }
.tbl tbody tr:nth-child(even) td:not(.td-item):not(.td-step):not(.td-risk) { background: #fafafa; }
.td-item { font-weight: 600; color: #1a1a1a; width: 155px; background: #f0f0f0 !important; text-align: center !important; vertical-align: middle !important; }
.th-before { color: #a00 !important; }
.th-after  { color: #197340 !important; }
.td-before { color: #a00; text-align: center; vertical-align: middle; }
.td-after  { color: #197340; font-weight: 600; text-align: center; vertical-align: middle; }
.th-label { width: 110px; text-align: center !important; }
.td-time { font-family: SFMono-Regular, Consolas, monospace; font-size: 12px; white-space: nowrap; text-align: center; vertical-align: middle; }
.td-type { font-weight: 600; color: #333; vertical-align: middle; text-align: center; }
.td-step { font-weight: 600; color: #1a1a1a; background: #f0f0f0; text-align: center !important; vertical-align: middle !important; }
.td-exec { text-align: center; font-size: 12px; }
.td-risk { text-align: center; font-weight: 600; color: #1a1a1a; background: #f0f0f0; vertical-align: middle; }
.r-hi  { font-size: 12.5px; font-weight: 700; color: #c00; }
.r-mid { font-size: 12.5px; font-weight: 700; color: #555; }
.r-low { font-size: 12.5px; font-weight: 700; color: #888; }
.na-box { padding: 10px 14px; background: #f9f9f9; border: 1px solid #ddd; border-left: 3px solid #aaa; font-size: 12px; color: #777; }
.doc ul, .doc ol { padding-left: 0; list-style-position: inside; margin: 6px 0 10px; }
.doc li { margin-bottom: 4px; line-height: 1.65; font-size: 12.5px; }
code { font-family: SFMono-Regular, Consolas, Menlo, monospace; font-size: 11.5px; background: #f4f4f4; border: 1px solid #ddd; padding: 0 4px; border-radius: 2px; }
.note { font-size: 11.5px; color: #666; margin-top: 6px; line-height: 1.65; }
.doc-footer { margin-top: 28px; padding-top: 8px; border-top: 1px solid #bbb; display: flex; justify-content: flex-end; font-size: 11px; color: #999; }
.tbl-summary { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
.tbl-summary td { width: 25%; padding: 10px 12px; border: 1px solid #ddd; vertical-align: middle; text-align: center; }
.s-label { font-size: 12.5px; color: #888; margin-bottom: 4px; }
.s-value { font-size: 16px; font-weight: 800; color: #1f3864; line-height: 1.2; }
.s-value.red { color: #c00; }
.s-value.orange { color: #c05800; }
.cost-up   { color: #c00; font-weight: 600; }
.cost-down { color: #197340; font-weight: 600; }
.cost-sum td { font-weight: 700; background: #f5f5f5 !important; }
.st-crit   { color: #c00; font-weight: 700; }
.st-high   { color: #c05800; font-weight: 700; }
.st-med    { color: #9a7000; font-weight: 600; }
.st-low    { color: #888; font-weight: 600; }
.st-ok     { color: #197340; font-weight: 600; }
.st-warn   { color: #9a7000; font-weight: 600; }
.st-danger { color: #c00; font-weight: 700; }
.st-skip   { color: #888; font-weight: 600; }
@media print { body { font-size: 11px; } .doc { padding: 0; max-width: 100%; } }
""".strip()

_STYLE_RULES = """
HTML 구조 규칙 (반드시 준수):
- <html>, <head>, <body>, <style> 태그 없이 콘텐츠만 출력
- 최상위 래퍼: <div class="doc">
- 헤더:
    <div class="doc-header">
      <div class="doc-header-top">
        <div style="font-size:18px;font-weight:900;color:#1f3864;">DnDn</div>
        <div class="doc-header-meta">문서번호: XXX<br>작성일: YYYY.MM.DD</div>
      </div>
      <div class="doc-header-title">제목</div>
    </div>
- Overview(기본 정보): <div class="section"><div class="section-title">Overview</div><table class="tbl-info">...</table></div>
- 일반 섹션: <div class="section"><div class="section-title">N. 섹션명</div>...</div>
- 서브헤딩: <div class="sub-heading">소제목</div>
- 정보 테이블 (th/td 교차): <table class="tbl-info"><tbody><tr><th>라벨</th><td>값</td><th>라벨</th><td>값</td></tr></tbody></table>
- 일반 테이블: <table class="tbl"><thead><tr><th>컬럼</th></tr></thead><tbody><tr><td>값</td></tr></tbody></table>
- 위험도 분석 테이블 행: <tr><td class="td-risk">항목명</td><td style="text-align:center;vertical-align:middle;"><span class="r-hi">상</span></td><td>설명</td></tr>
- 작업 절차 테이블 행: <tr><td class="td-step">①</td><td class="td-exec">단계명</td><td>내용</td><td class="td-exec">담당</td></tr>
- Before/After 행: <tr><td class="td-item">항목</td><td class="td-before">이전</td><td class="td-after">이후</td></tr>  (헤더: <th class="th-before">변경 전</th><th class="th-after">변경 후</th>)
- 상태 텍스트: <span class="st-crit">위험</span> / <span class="st-high">상</span> / <span class="st-ok">정상</span> / <span class="st-warn">주의</span>
- 심각도: <span class="r-hi">상</span> / <span class="r-mid">중</span> / <span class="r-low">하</span>
- KPI 카드: <table class="tbl-summary"><tbody><tr><td><div class="s-label">지표명</div><div class="s-value">값</div></td></tr></tbody></table>
- code 태그: <code>리소스ID</code>
- 푸터: <div class="doc-footer"><span>문서번호 &nbsp;/&nbsp; 날짜</span></div>
"""


def _wrap_html(title: str, body: str) -> str:
    """Claude가 생성한 body 콘텐츠를 완전한 HTML 문서로 래핑"""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
{_BASE_CSS}
</style>
</head>
<body>
{body.strip()}
</body>
</html>"""


# ─────────────────────────────────────────────────
# Bedrock 공통 호출
# ─────────────────────────────────────────────────


def get_bedrock_client():
    from botocore.config import Config

    config = Config(read_timeout=300, connect_timeout=10)
    return boto3.client("bedrock-runtime", region_name=REGION, config=config)


def _invoke_claude(system_prompt: str, user_content: str) -> str:
    """Bedrock Claude 공통 호출 → raw text 반환"""
    client = get_bedrock_client()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip()


def call_claude(system_prompt: str, user_content: str) -> str:
    """HTML 보고서 반환 (raw text)"""
    return _invoke_claude(system_prompt, user_content)


# ─────────────────────────────────────────────────
# 보고서 생성 함수들
# ─────────────────────────────────────────────────


def generate_event_report(canonical: dict) -> str:
    """SecurityHub / 일반 이벤트 보고서 HTML 생성 (MCP AWS 문서 참조)

    Args:
        canonical: S3에 저장된 canonical JSON dict
            - meta.title / meta.run_id : 문서 제목
            - resources[].extensions.aws_health : AWS Health 이벤트 정보
            - resources[].extensions.actionability : 조치 가능성 분석
            - resources[].extensions.securityhub_finding : SecurityHub Finding
            - content : 이벤트 내용 설명 (선택)
    """
    meta = canonical.get("meta", {})
    title = meta.get("title") or meta.get("run_id") or "이벤트 보고서"

    # extension fields
    resources = canonical.get("resources", [{}])
    first_ext = resources[0].get("extensions", {}) if resources else {}
    aws_health = first_ext.get("aws_health", {})
    actionability = first_ext.get("actionability", {})
    securityhub_finding = first_ext.get("securityhub_finding", {})

    event_code = aws_health.get("event_type_code", "")
    service = aws_health.get("service", "")
    aws_docs = _fetch_aws_docs(event_code, service)

    ext_section = ""
    if aws_health:
        ext_section += f"\n## AWS Health 이벤트\n{json.dumps(aws_health, ensure_ascii=False, indent=2)}\n"
    if actionability:
        ext_section += f"\n## 조치 가능성 분석\n{json.dumps(actionability, ensure_ascii=False, indent=2)}\n"
    if securityhub_finding:
        ext_section += f"\n## SecurityHub Finding\n{json.dumps(securityhub_finding, ensure_ascii=False, indent=2)}\n"
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회)\n{aws_docs}\n" if aws_docs else ""
    )
    canonical_section = (
        f"\n## Canonical JSON (전체)\n{json.dumps(canonical, ensure_ascii=False, indent=2)}\n"
    )

    system = f"""
당신은 AWS 인프라 보안 이벤트 분석 전문가입니다.
이벤트 canonical JSON을 분석하여 한국어 HTML 보고서 콘텐츠를 생성하세요.

{_STYLE_RULES}

콘텐츠 규칙 — 아래 순서대로 각각 독립된 section-title을 가진 섹션으로 구성하세요:

① Overview
  - tbl-info: 감지 이벤트(한 줄 설명), 대상 리소스, AWS 계정, 심각도, 감지 일시
  - securityhub_finding 있으면: Finding ID, 컨트롤 ID, 준수 기준(compliance standard)도 포함

② 이벤트 개요
  - tbl (th.th-label + td): 이벤트 유형, 감지 출처, Finding ID(있을 때), 영향 범위, 보안 기준, 이벤트 주체
  - securityhub_finding.title / description / severity / compliance_status 데이터 활용

③ 이벤트 타임라인
  - tbl: 시간(td-time), 구분(td-type), 내용 — CloudTrail events, worker 트리거 등 시간 순 나열

④ 영향 분석
  - sub-heading "영향 범위": tbl-info로 영향 리소스, 리소스 유형, 외부 노출 여부, 준수 상태
  - sub-heading "위험도 분석": tbl로 위험 항목(td-risk), 수준(r-hi/r-mid/r-low), 분석 내용

⑤ AWS Health 영향 요약 (aws_health 데이터 있을 때만)
  - tbl: 영향 서비스, event_type_code, event_type_category, 기간, 영향 엔티티 목록
  - actionability 있으면: 위험 수준, 마감 기한, 권장 조치 목록도 sub-heading으로 추가

⑥ 보안 Finding 상세 (securityhub_finding 데이터 있을 때만)
  - tbl (th.th-label + td): 감지 서비스, 컨트롤 ID, 보안 기준, 심각도/Score, 준수 상태, 리소스 유형, 계정 별칭, 최초/최근 감지
  - remediation URL 있으면 참고 링크로 표시

⑦ 권장 조치
  - tbl: 구분(td-step), 우선순위(td-step), 조치 내용
  - actionability.recommended_actions 항목을 우선순위 순으로 정렬
  - AWS 공식 문서 remediation 링크 포함

⑧ 자동 조치 가능성 (actionability.immediate_action_required 또는 Terraform 후보 여부가 있을 때만)
  - 자동화 가능한 조치, Terraform/AWS Config Remediation 후보 여부 간략히 설명

영어 텍스트는 자연스러운 한국어로 번역하세요. 데이터가 없는 섹션은 출력하지 마세요.
""".strip()

    user = f"""
다음 이벤트 canonical JSON을 분석하여 <div class="doc">...</div> 콘텐츠만 출력하세요.
{ext_section}
{canonical_section}
{aws_docs_section}
""".strip()

    return _wrap_html(title, call_claude(system, user))


def generate_weekly_report(canonical: dict) -> str:
    """주간 보고서 HTML 생성 (MCP AWS Well-Architected 문서 참조)

    Args:
        canonical: S3에 저장된 canonical JSON dict
            - meta.title / meta.period : 제목 및 기간
            - extensions.advisor_checks / advisor_rollup : AWS Trusted Advisor
            - extensions.access_analyzer_findings / access_analyzer_rollup
            - extensions.cost_explorer_summary / cost_explorer_groups
            - extensions.cloudwatch_alarms / cloudwatch_rollup
    """
    meta = canonical.get("meta", {})
    title = meta.get("title") or "주간 보고서"
    period = meta.get("period", {})
    ext = canonical.get("extensions", {})

    advisor_checks = ext.get("advisor_checks", [])
    advisor_rollup = ext.get("advisor_rollup", {})
    access_analyzer_findings = ext.get("access_analyzer_findings", [])
    access_analyzer_rollup = ext.get("access_analyzer_rollup", {})
    cost_explorer_summary = ext.get("cost_explorer_summary", {})
    cost_explorer_groups = ext.get("cost_explorer_groups", [])
    cloudwatch_alarms = ext.get("cloudwatch_alarms", [])
    cloudwatch_rollup = ext.get("cloudwatch_rollup", {})

    print("[MCP] 주간 보고서용 AWS Well-Architected 문서 조회 중...")
    wa_docs = _fetch_aws_docs_by_query(
        "AWS Well-Architected Framework security reliability best practices weekly review"
    )
    wa_docs_section = (
        f"\n## AWS Well-Architected 가이드 (MCP 실시간 조회)\n{wa_docs}\n"
        if wa_docs
        else ""
    )

    ext_section = ""
    if advisor_rollup or advisor_checks:
        ext_section += f"\n## Trusted Advisor 요약\n{json.dumps(advisor_rollup, ensure_ascii=False, indent=2)}\n"
        if advisor_checks:
            ext_section += f"### 체크 항목 ({len(advisor_checks)}건)\n{json.dumps(advisor_checks[:20], ensure_ascii=False, indent=2)}\n"
    if access_analyzer_rollup or access_analyzer_findings:
        ext_section += f"\n## Access Analyzer 요약\n{json.dumps(access_analyzer_rollup, ensure_ascii=False, indent=2)}\n"
        if access_analyzer_findings:
            ext_section += f"### Findings ({len(access_analyzer_findings)}건)\n{json.dumps(access_analyzer_findings[:20], ensure_ascii=False, indent=2)}\n"
    if cost_explorer_summary:
        ext_section += f"\n## 비용 요약\n{json.dumps(cost_explorer_summary, ensure_ascii=False, indent=2)}\n"
        if cost_explorer_groups:
            ext_section += f"### 서비스별 비용\n{json.dumps(cost_explorer_groups[:30], ensure_ascii=False, indent=2)}\n"
    if cloudwatch_rollup or cloudwatch_alarms:
        ext_section += f"\n## CloudWatch 알람 요약\n{json.dumps(cloudwatch_rollup, ensure_ascii=False, indent=2)}\n"
        if cloudwatch_alarms:
            ext_section += f"### 알람 목록 ({len(cloudwatch_alarms)}건)\n{json.dumps(cloudwatch_alarms[:20], ensure_ascii=False, indent=2)}\n"

    canonical_section = f"\n## Canonical JSON (전체)\n{json.dumps(canonical, ensure_ascii=False, indent=2)}\n"

    system = f"""
당신은 AWS 인프라 주간 보고서 생성 전문가입니다.
canonical JSON 데이터를 분석하여 한국어 HTML 주간 보고서 콘텐츠를 생성하세요.

{_STYLE_RULES}

콘텐츠 규칙 — 아래 순서대로 각각 독립된 section-title을 가진 섹션으로 구성하세요. 절대 섹션을 합치지 마세요:

① Overview
  - tbl-info: AWS 계정, 보고 기간
  - tbl-summary (4칸 KPI 카드): 총 비용(cost_explorer_summary.total_cost_usd), 운영 경보(cloudwatch_rollup: ALARM/전체), 보안 Findings(access_analyzer_rollup.total_findings), 리소스 점검(advisor_rollup.total_checks)

② 운영 경보(ALARM) 현황 (cloudwatch_alarms / cloudwatch_rollup 데이터 있을 때)
  - tbl: 알람명, 상태(st-crit/st-warn/st-ok), 메트릭, 임계치, 현재값, 리소스
  - ALARM 상태인 것을 상단에 표시

③ 운영 점검 결과 요약 (advisor_checks / advisor_rollup 데이터 있을 때)
  - sub-heading "점검 요약": advisor_rollup 수치 (전체/red/yellow/green)
  - sub-heading "주요 점검 항목": tbl로 점검 항목명(td-risk), 위험도(r-hi/r-mid/r-low), 영향 리소스 수, 설명
  - status=error → r-hi, warning → r-mid, ok → r-low

④ 접근/권한 리스크 요약 (access_analyzer_findings / access_analyzer_rollup 데이터 있을 때)
  - sub-heading "요약": access_analyzer_rollup 수치 (전체/활성/아카이브)
  - sub-heading "Finding 목록": tbl로 리소스, 상태(st-warn/st-ok), 설명

⑤ 비용 현황 (cost_explorer_summary / cost_explorer_groups 데이터 있을 때)
  - sub-heading "서비스별 비용 분석": tbl로 서비스, 비용(USD), 비중(%)
  - 합계 행에 cost-sum 클래스, 비용 증가 서비스에 cost-up 클래스
  - cost_explorer_summary.vs_last_week_pct 있으면 전주 대비 증감 표시

⑥ 액션 아이템
  - tbl: 구분(td-risk), 조치 사항, 우선순위(r-hi/r-mid/r-low)
  - advisor/access_analyzer/cloudwatch 데이터에서 도출된 우선순위 항목
  - AWS Well-Architected 가이드 내용 반영

데이터가 없는 섹션은 출력하지 마세요. 영어 텍스트는 자연스러운 한국어로 번역하세요.
""".strip()

    user = f"""
다음 주간 보고서 canonical JSON을 분석하여 <div class="doc">...</div> 콘텐츠만 출력하세요.

보고 기간: {period.get('start', '')} ~ {period.get('end', '')}
{ext_section}
{canonical_section}
{wa_docs_section}
""".strip()

    return _wrap_html(title, call_claude(system, user))


def generate_work_plan(target: str, content: str, context: dict | None = None) -> str:
    """작업계획서 HTML 생성 (MCP AWS 문서 참조)

    Args:
        target: 작업 대상 (리소스명, 서비스명 등)
        content: 작업 내용 설명
        context: ref_doc_ids로 병합된 canonical 컨텍스트 (선택)
    """
    ctx = context or {}

    aws_docs = ctx.get("aws_docs", "")
    if aws_docs:
        print("[MCP] 작업계획서: aws_docs 재사용 (MCP 조회 스킵)")
    else:
        event_code, service = _detect_event_info(ctx)
        print(
            f"[MCP] 작업계획서용 AWS 문서 조회 중... (event: {event_code or service or 'unknown'})"
        )
        aws_docs = _fetch_aws_docs(event_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회) — 작업 절차에 반영하세요\n{aws_docs}\n"
        if aws_docs
        else ""
    )
    context_section = (
        f"\n## 참고 컨텍스트 (이전 보고서)\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n"
        if ctx
        else ""
    )

    system = f"""
당신은 AWS 인프라 작업계획서 생성 전문가입니다.
작업 대상과 내용, 참고 컨텍스트를 분석하여 한국어 HTML 작업계획서 콘텐츠를 생성하세요.

{_STYLE_RULES}

콘텐츠 규칙:
1. 필수 섹션: 개요(작업명/대상/담당자/예정일), 작업 단계(최대 6단계), 변경 전/후, 위험 분석, 롤백 계획
   — 작업 성격에 따라 필요한 섹션을 자유롭게 추가하세요 (예: 사전 점검 항목, 영향 범위, 승인 이력 등)
2. 작업 단계는 번호 매겨서 간결하게 (CLI 명령어 포함 금지)
""".strip()

    user = f"""
다음 작업 정보를 분석하여 <div class="doc">...</div> 콘텐츠만 출력하세요.

작업 대상: {target}
작업 내용: {content}
{context_section}
{aws_docs_section}
""".strip()

    title = target or "작업계획서"
    return _wrap_html(title, call_claude(system, user))


def generate_health_event_report(canonical: dict) -> str:
    """AWS Health 이벤트 보고서 HTML 생성 (MCP AWS 문서 참조)

    Args:
        canonical: S3에 저장된 canonical JSON dict
            - meta.title / meta.run_id : 문서 제목
            - resources[].extensions.aws_health : AWS Health 이벤트 상세
            - resources[].extensions.actionability : 조치 가능성 분석
    """
    meta = canonical.get("meta", {})

    resources = canonical.get("resources", [{}])
    first_ext = resources[0].get("extensions", {}) if resources else {}
    aws_health = first_ext.get("aws_health", {})
    actionability = first_ext.get("actionability", {})

    event_type_code = aws_health.get("event_type_code", "")
    service = aws_health.get("service", "")
    title_candidate = meta.get("title") or service or "이벤트"

    print(
        f"[MCP] Health 이벤트 보고서용 AWS 문서 조회 중... ({event_type_code or service})"
    )
    aws_docs = _fetch_aws_docs(event_type_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회) — 권장 조치 작성에 반영하세요\n{aws_docs}\n"
        if aws_docs
        else ""
    )

    ext_section = ""
    if aws_health:
        ext_section += f"\n## AWS Health 이벤트 상세\n{json.dumps(aws_health, ensure_ascii=False, indent=2)}\n"
    if actionability:
        ext_section += f"\n## 조치 가능성 분석\n{json.dumps(actionability, ensure_ascii=False, indent=2)}\n"

    canonical_section = f"\n## Canonical JSON (전체)\n{json.dumps(canonical, ensure_ascii=False, indent=2)}\n"

    system = f"""
당신은 AWS 인프라 운영 전문가입니다.
AWS Health 이벤트 canonical JSON과 AWS 공식 문서를 분석하여 한국어 HTML 이벤트 보고서 콘텐츠를 생성하세요.

{_STYLE_RULES}

콘텐츠 규칙:
1. 필수 섹션: Overview(기본정보), 이벤트 개요, 이벤트 타임라인, 이벤트 상세, 권장 조치(최소 3단계)
2. actionability 데이터가 있으면 조치 우선순위 섹션으로 표현하세요
3. 이벤트 유형에 따라 1~2개 섹션을 자유롭게 추가하세요 (예: 영향 리소스 목록, 조치 체크리스트)
4. UTC 시각은 KST(+9시간)로 변환하세요
""".strip()

    user = f"""
다음 AWS Health 이벤트 canonical JSON을 분석하여 <div class="doc">...</div> 콘텐츠만 출력하세요.
{ext_section}
{canonical_section}
{aws_docs_section}
""".strip()

    title = f"AWS Health 이벤트 보고서 — {title_candidate}"
    return _wrap_html(title, call_claude(system, user))


if __name__ == "__main__":
    from pathlib import Path

    sample_path = (
        Path(__file__).parent.parent / "ui/src/data/health-eks-version-eol.json"
    )
    raw_json = json.loads(sample_path.read_text())
    canonical = {
        "meta": {"type": "HEALTH", "title": "EKS"},
        "resources": [{"extensions": {"aws_health": raw_json.get("detail", raw_json)}}],
    }
    print("=== Health 이벤트 보고서 생성 테스트 (MCP) ===")
    result = generate_health_event_report(canonical)
    print(result)
