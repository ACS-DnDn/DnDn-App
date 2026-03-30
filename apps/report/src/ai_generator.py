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
    docs = _fetch_aws_docs_by_query(query)
    # MCP 결과가 너무 크면 잘라서 반환 (토큰 초과 방지)
    if len(docs) > _MAX_AWS_DOCS_CHARS:
        docs = docs[:_MAX_AWS_DOCS_CHARS] + "\n... (truncated)"
    return docs


# ── 프롬프트 크기 제한 상수 ──
_MAX_AWS_DOCS_CHARS = 40_000     # AWS 문서 최대 ~10K 토큰
_MAX_REF_DOCS = 2                # 참조 문서 최대 개수
_MAX_PROMPT_CHARS = 150_000      # 최종 user prompt 안전 상한 ~40K 토큰
_SUMMARIZE_THRESHOLD = 20_000    # 이 글자수 이상이면 Haiku 요약 적용


def _summarize_large_text(text: str, purpose: str = "작업계획서") -> str:
    """큰 텍스트를 Haiku로 요약. 임계값 미만이면 원본 반환."""
    if len(text) <= _SUMMARIZE_THRESHOLD:
        return text
    print(f"[Haiku] {purpose} 요약 시작 ({len(text)}자 → Haiku)")
    try:
        summary = _invoke_claude(
            "당신은 AWS 인프라 문서 요약 전문가입니다. "
            f"다음 문서를 {purpose} 작성에 필요한 핵심 정보만 한국어로 요약하세요. "
            "영향 범위, 조치 방안, 리소스 정보, 위험 요소를 반드시 포함하세요.",
            text,
            model_id=HAIKU_MODEL_ID,
        )
        print(f"[Haiku] 요약 완료 ({len(text)}자 → {len(summary)}자)")
        return summary
    except Exception as e:
        print(f"[Haiku] 요약 실패, truncate 폴백: {e}")
        return text[:_SUMMARIZE_THRESHOLD] + "\n... (truncated)"


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

def _style_rules(doc_meta: dict | None = None) -> str:
    """doc_meta가 있으면 헤더에 로고/문서번호/담당자를 동적으로 삽입"""
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST).strftime("%Y.%m.%d %H:%M")

    meta = doc_meta or {}
    logo_url = meta.get("company_logo_url", "")
    doc_num = meta.get("doc_num") or "(자동부여)"
    author_label = meta.get("author_label", "")

    if logo_url:
        logo_html = f'<img src="{logo_url}" alt="logo" style="height:32px;">'
    else:
        logo_html = '<div style="font-size:18px;font-weight:900;color:#1f3864;">DnDn</div>'

    author_rule = ""
    if author_label:
        author_rule = f"\n- Overview 테이블의 '작업 담당자' 값은 반드시 '{author_label}'로 출력하세요."

    return f"""
HTML 구조 규칙 (반드시 준수):
- <html>, <head>, <body>, <style> 태그 없이 콘텐츠만 출력
- 최상위 래퍼: <div class="doc">
- 헤더:
    <div class="doc-header">
      <div class="doc-header-top">
        {logo_html}
        <div class="doc-header-meta">문서번호: {doc_num}<br>작성일: {now_kst}</div>
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
- 푸터: <div class="doc-footer"><span>{doc_num} &nbsp;/&nbsp; {now_kst}</span></div>
- ⚠️ 문서번호 필드(헤더·푸터)에는 위에 제시된 값을 **그대로** 출력하세요. 절대 임의의 번호를 생성하지 마세요.{author_rule}
"""


# 하위호환: 보고서(EVT/RPT)는 doc_meta 없이 기본값 사용
_STYLE_RULES = _style_rules()


def _wrap_html(title: str, body: str) -> str:
    """Claude가 생성한 body 콘텐츠를 완전한 HTML 문서로 래핑.
    Claude가 <div class="doc"> 앞에 설명 텍스트를 붙이는 경우 제거."""
    import re
    clean = body.strip()
    # <div class="doc"> 이전의 비-HTML 텍스트 제거
    m = re.search(r'<div\s+class="doc"', clean)
    if m and m.start() > 0:
        clean = clean[m.start():]
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
{clean}
</body>
</html>"""


# ─────────────────────────────────────────────────
# Bedrock 공통 호출
# ─────────────────────────────────────────────────


def get_bedrock_client():
    from botocore.config import Config

    config = Config(read_timeout=300, connect_timeout=10)
    return boto3.client("bedrock-runtime", region_name=REGION, config=config)


HAIKU_MODEL_ID = os.getenv(
    "BEDROCK_HAIKU_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)


def _invoke_claude(system_prompt: str, user_content: str, model_id: str | None = None) -> str:
    """Bedrock Claude 공통 호출 → raw text 반환"""
    client = get_bedrock_client()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 12000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    response = client.invoke_model(
        modelId=model_id or MODEL_ID,
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


def generate_event_report(canonical: dict, *, doc_meta: dict | None = None) -> str:
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

    evt_style = _style_rules(doc_meta)

    system = f"""
당신은 AWS 인프라 보안 이벤트 분석 전문가입니다.
이벤트 canonical JSON을 분석하여 한국어 HTML 보고서 콘텐츠를 생성하세요.

{evt_style}

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


def generate_weekly_report(canonical: dict, *, doc_meta: dict | None = None) -> str:
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
    period = meta.get("period", {}) or meta.get("time_range", {})
    # canonical_summary(extensions_summary) 및 full canonical(extensions) 모두 지원
    ext = canonical.get("extensions_summary") or canonical.get("extensions", {})

    # canonical_summary의 advisor_checks는 dict 형태 {"items": [...], "total_count": N}
    _advisor = ext.get("advisor_checks", {})
    advisor_checks = _advisor.get("items", []) if isinstance(_advisor, dict) else _advisor
    advisor_rollup = ext.get("advisor_rollup", {})
    _aa = ext.get("access_analyzer_findings", {})
    access_analyzer_findings = _aa.get("items", []) if isinstance(_aa, dict) else _aa
    access_analyzer_rollup = ext.get("access_analyzer_rollup", {})
    cost_explorer_summary = ext.get("cost_explorer_summary", {})
    _cg = ext.get("cost_explorer_groups", {})
    cost_explorer_groups = _cg.get("items", []) if isinstance(_cg, dict) else _cg
    _cw = ext.get("cloudwatch_alarms", {})
    cloudwatch_alarms = _cw.get("items", []) if isinstance(_cw, dict) else _cw
    cloudwatch_rollup = ext.get("cloudwatch_rollup", {})
    flow_logs_rollup = ext.get("flow_logs_rollup", {})
    _fl_rejected = ext.get("flow_logs_rejected_top", {})
    flow_logs_rejected = _fl_rejected.get("items", []) if isinstance(_fl_rejected, dict) else _fl_rejected
    _fl_ports = ext.get("flow_logs_port_distribution", {})
    flow_logs_port_dist = _fl_ports.get("items", []) if isinstance(_fl_ports, dict) else _fl_ports
    _fl_trend = ext.get("flow_logs_traffic_trend", {})
    flow_logs_trend = _fl_trend.get("items", []) if isinstance(_fl_trend, dict) else _fl_trend
    _fl_talkers = ext.get("flow_logs_top_talkers", {})
    flow_logs_talkers = _fl_talkers.get("items", []) if isinstance(_fl_talkers, dict) else _fl_talkers
    _fl_external = ext.get("flow_logs_external_comm", {})
    flow_logs_external = _fl_external.get("items", []) if isinstance(_fl_external, dict) else _fl_external
    _fl_proto = ext.get("flow_logs_protocol_dist", {})
    flow_logs_proto = _fl_proto.get("items", []) if isinstance(_fl_proto, dict) else _fl_proto
    events_summary = canonical.get("events_summary", {})
    resources_summary = canonical.get("resources_summary", {})

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
    if flow_logs_rollup or flow_logs_rejected:
        ext_section += f"\n## VPC Flow Logs 요약\n{json.dumps(flow_logs_rollup, ensure_ascii=False, indent=2)}\n"
        if flow_logs_trend:
            ext_section += f"### 일별 트래픽 추이 ({len(flow_logs_trend)}일)\n{json.dumps(flow_logs_trend, ensure_ascii=False, indent=2)}\n"
        if flow_logs_talkers:
            ext_section += f"### Top Talkers — 트래픽 최다 IP ({len(flow_logs_talkers)}건)\n{json.dumps(flow_logs_talkers[:10], ensure_ascii=False, indent=2)}\n"
        if flow_logs_external:
            ext_section += f"### 외부 통신 상위 목록 ({len(flow_logs_external)}건)\n{json.dumps(flow_logs_external[:10], ensure_ascii=False, indent=2)}\n"
        if flow_logs_port_dist:
            ext_section += f"### 포트별 트래픽 분포\n{json.dumps(flow_logs_port_dist[:20], ensure_ascii=False, indent=2)}\n"
        if flow_logs_proto:
            ext_section += f"### 프로토콜 분포\n{json.dumps(flow_logs_proto, ensure_ascii=False, indent=2)}\n"
        if flow_logs_rejected:
            ext_section += f"### 거부 트래픽 상위 소스 ({len(flow_logs_rejected)}건)\n{json.dumps(flow_logs_rejected[:20], ensure_ascii=False, indent=2)}\n"
    if events_summary:
        ext_section += f"\n## CloudTrail 이벤트 요약\n{json.dumps(events_summary, ensure_ascii=False, indent=2)}\n"
    if resources_summary:
        top_resources = resources_summary.get("top_resources", [])
        ext_section += f"\n## 주요 변경 리소스 (반드시 '주요 변경 리소스' sub-heading으로 tbl 표시)\n"
        ext_section += f"총 추적 리소스 수: {resources_summary.get('total_tracked', len(top_resources))}\n"
        if top_resources:
            # 모델이 파싱하기 쉽도록 단순 목록으로 정리
            rows = []
            for r in sorted(top_resources, key=lambda x: x.get("change_summary", {}).get("event_count", 0), reverse=True)[:10]:
                res = r.get("resource", {})
                cs = r.get("change_summary", {})
                rows.append({
                    "리소스ID": res.get("arn") or res.get("resource_id", ""),
                    "유형": res.get("resource_type", ""),
                    "이벤트수": cs.get("event_count", 0),
                    "최근활동": cs.get("last_event_time", ""),
                })
            ext_section += f"### 상위 변경 리소스 목록\n{json.dumps(rows, ensure_ascii=False, indent=2)}\n"

    wk_style = _style_rules(doc_meta)

    system = f"""
당신은 AWS 인프라 활동 보고서 생성 전문가입니다.
canonical JSON 데이터를 분석하여 한국어 HTML 인프라 활동 보고서 콘텐츠를 생성하세요.

{wk_style}

콘텐츠 규칙 — 아래 순서대로 각각 독립된 section-title을 가진 섹션으로 구성하세요. 절대 섹션을 합치지 마세요:

① Overview
  - tbl-info: AWS 계정, 보고 기간
  - tbl-summary (4칸 KPI 카드, 반드시 4칸 유지): 총 비용(cost_explorer_summary.total_cost_usd), 운영 경보(cloudwatch_rollup: ALARM/전체), 보안 Findings(access_analyzer_rollup.total_findings), 리소스 점검(advisor_rollup.total_checks)

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

⑥ CloudTrail 활동 요약 (events_summary 데이터 있을 때)
  - tbl-info: 총 이벤트 수, 기간
  - sub-heading "주요 API 호출": tbl로 event_name, 횟수 — event_name_counts 항목을 생략 없이 모두 표시 (최대 10개)
  - sub-heading "주요 변경 리소스" (resources_summary 데이터 있을 때 반드시 포함):
    tbl로 리소스 ARN/ID(td-risk), 리소스 유형, 이벤트 수 — top_resources를 change_summary.event_count 내림차순으로 상위 10개 표시

⑦ 네트워크 트래픽 분석 (flow_logs 데이터 있을 때)
  이 섹션은 인프라 관리자가 "네트워크가 정상인가?", "보안 위협이 있나?", "어떤 리소스가 트래픽을 많이 쓰나?"를 한눈에 파악할 수 있도록 구성합니다.

  이 섹션의 모든 서브헤딩은 해당 데이터가 있으면 반드시 출력하세요. 절대 생략하지 마세요.

  - sub-heading "트래픽 개요": tbl-info 2×2로 총 허용(건), 총 거부(건), 거부 비율(%), VPC 수, 총 전송량(KB/MB/GB 변환)
    - 거부 비율: 0~1% st-ok, 1~5% st-warn, 5%↑ st-crit

  - sub-heading "일별 트래픽 추이": tbl — 날짜(KST), 총 건수, 허용, 거부, 전송량. 평균 대비 2배 이상 변동 시 주석

  - sub-heading "Top Talkers": tbl — IP, 요청 건수, 전송량. 사설IP 대역이면 서브넷 추정 (예: 10.0.1.x → Private)

  - sub-heading "외부 통신 상위": tbl — 외부 IP, 요청 건수, 전송량. AWS IP(43.x, 52.x 등)면 서비스 추정, 미상 IP는 r-mid

  - sub-heading "포트별 트래픽 분포": tbl — 포트(서비스명 병기: 443/HTTPS 등), 허용, 거부, 전송량. 비표준 포트 r-mid

  - sub-heading "프로토콜 분포": tbl — 프로토콜(TCP/UDP/ICMP), 건수, 전송량, 비율(%). ICMP 과다 시 r-mid

  - sub-heading "거부 트래픽 분석" (거부 0건이면 생략 가능): tbl — 소스IP, 목적지포트, 횟수, 위험도(r-hi≥100/r-mid≥10/r-low)

⑧ 액션 아이템
  - tbl: 구분(td-risk), 조치 사항, 우선순위(r-hi/r-mid/r-low), 근거 데이터
  - advisor/access_analyzer/cloudwatch/events/flow_logs 데이터에서 도출된 우선순위 항목
  - flow_logs에서 도출 가능: 거부 비율 높은 경우 보안그룹 점검 권고, 비정상 외부 통신 IP 차단 검토, 비표준 포트 사용 확인, ICMP 대량 발생 시 스캔 대응 등
  - AWS Well-Architected 가이드 내용 반영

데이터가 없는 섹션은 출력하지 마세요. 영어 텍스트는 자연스러운 한국어로 번역하세요.
모든 날짜/시각은 UTC를 KST(+9시간)로 변환하여 "YYYY.MM.DD HH:mm (KST)" 형식으로 표시하세요.
""".strip()

    from datetime import datetime, timezone, timedelta

    KST = timedelta(hours=9)

    def _to_kst(iso_str: str) -> str:
        if not iso_str:
            return ""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            kst = dt.astimezone(timezone(KST))
            return kst.strftime("%Y.%m.%d %H:%M (KST)")
        except Exception:
            return iso_str

    def _to_kst_date(iso_str: str) -> str:
        if not iso_str:
            return ""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            kst = dt.astimezone(timezone(KST))
            return kst.strftime("%Y.%m.%d")
        except Exception:
            return iso_str

    period_start_kst = _to_kst(period.get("start", ""))
    period_end_kst = _to_kst(period.get("end", ""))

    # 제목: 사용자 입력 제목 우선, 없으면 기본 패턴
    user_title = (meta.get("title") or "").strip()
    if user_title:
        title = user_title
    else:
        p_start = _to_kst_date(period.get("start", ""))
        p_end = _to_kst_date(period.get("end", ""))
        if p_start and p_end:
            title = f"AWS 인프라 활동 보고서({p_start} ~ {p_end})"
        elif p_start:
            title = f"AWS 인프라 활동 보고서({p_start})"
        else:
            title = "AWS 인프라 활동 보고서"

    user = f"""
다음 인프라 활동 보고서 데이터를 분석하여 <div class="doc">...</div> 콘텐츠만 출력하세요.
헤더의 제목(<div class="doc-header-title">)은 반드시 "{title}"로 출력하세요.

보고 기간: {period_start_kst} ~ {period_end_kst}
{ext_section}
{wa_docs_section}
""".strip()

    return _wrap_html(title, call_claude(system, user))


def generate_work_plan(target: str, content: str, context: dict | None = None, *, doc_meta: dict | None = None) -> str:
    """작업계획서 HTML 생성 (MCP AWS 문서 참조)

    Args:
        target: 작업 대상 (리소스명, 서비스명 등)
        content: 작업 내용 설명
        context: ref_doc_ids로 병합된 canonical 컨텍스트 (선택)
        doc_meta: 문서 메타 (doc_num, author_label, company_logo_url)
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
    # AWS 문서: 크면 Haiku로 요약
    aws_docs = _summarize_large_text(aws_docs, "작업계획서 — AWS 문서") if aws_docs else ""
    aws_docs_section = (
        f"\n## AWS 공식 문서 — 작업 절차에 반영하세요\n{aws_docs}\n"
        if aws_docs
        else ""
    )
    # 참조 문서: aws_docs 제외 (이미 별도 섹션) + 크면 Haiku로 요약
    ctx_for_prompt = {k: v for k, v in ctx.items() if k != "aws_docs"}
    context_section = ""
    if ctx_for_prompt:
        ctx_text = json.dumps(ctx_for_prompt, ensure_ascii=False, indent=2)
        ctx_text = _summarize_large_text(ctx_text, "작업계획서 — 참조 문서")
        context_section = f"\n## 참고 컨텍스트 (이전 보고서)\n{ctx_text}\n"

    style = _style_rules(doc_meta)

    system = f"""
당신은 AWS 인프라 작업계획서 생성 전문가입니다.
작업 대상과 내용, 참고 컨텍스트를 분석하여 한국어 HTML 작업계획서 콘텐츠를 생성하세요.

{style}

콘텐츠 규칙:
1. 필수 섹션: 개요(작업명/대상/담당자/예정일), 작업 단계(최대 6단계), 변경 전/후, 위험 분석, 롤백 계획
   — 작업 성격에 따라 필요한 섹션을 자유롭게 추가하세요 (예: 사전 점검 항목, 영향 범위, 승인 이력 등)
2. 작업 단계는 번호 매겨서 간결하게 (CLI 명령어 포함 금지)
""".strip()

    # None → 빈 문자열 정규화
    safe_target = target or ""
    safe_content = content or ""

    def _build_user():
        return f"""
다음 작업 정보를 분석하여 <div class="doc">...</div> 콘텐츠만 출력하세요.
{f"작업 대상: {safe_target}" if safe_target else ""}
{f"작업 내용: {safe_content}" if safe_content else ""}
{context_section}
{aws_docs_section}
""".strip()

    user = _build_user()

    # 최종 안전장치: 프롬프트 초과 시 aws_docs → context 순으로 축소
    total = len(system) + len(user)
    if total > _MAX_PROMPT_CHARS:
        over = total - _MAX_PROMPT_CHARS
        print(f"[WARN] 프롬프트 {total}자 → {_MAX_PROMPT_CHARS}자로 축소")
        # 1차: aws_docs 축소
        if aws_docs_section and over > 0:
            trim = min(len(aws_docs_section), over)
            aws_docs_section = aws_docs_section[: len(aws_docs_section) - trim]
            over -= trim
        # 2차: context 축소
        if context_section and over > 0:
            trim = min(len(context_section), over)
            context_section = context_section[: len(context_section) - trim]
        user = _build_user()

    title = safe_target or "작업계획서"
    return _wrap_html(title, call_claude(system, user))


def generate_health_event_report(canonical: dict, *, doc_meta: dict | None = None) -> str:
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

    health_style = _style_rules(doc_meta)

    system = f"""
당신은 AWS 인프라 운영 전문가입니다.
AWS Health 이벤트 canonical JSON과 AWS 공식 문서를 분석하여 한국어 HTML 이벤트 보고서 콘텐츠를 생성하세요.

{health_style}

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
