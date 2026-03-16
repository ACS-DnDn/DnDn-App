import json
import boto3
import subprocess
import threading
import time
import os
import shutil
import functools

# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")  # Legacy
# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")  # us 전용
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "apac.anthropic.claude-3-5-sonnet-20241022-v2:0")
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
        self._read()
        self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })

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


@functools.lru_cache(maxsize=50)
def _fetch_aws_docs_by_query(query: str) -> str:
    """쿼리 직접 지정해서 AWS Documentation MCP 조회 (lru_cache 캐싱)"""
    if not query:
        return ""
    mcp = AWSDocsMCPClient()
    try:
        mcp.start()
        result = mcp.call_tool("search_documentation", {"search_phrase": query})
        docs = result if result else ""
        print(f"[MCP] AWS 문서 조회 완료: '{query}' ({len(docs)}자)")
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
            data.get("resources", [{}])[0]
            .get("extensions", {})
            .get("aws_health", {})
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
        categories = list(set(i.get("category", "") for i in items if i.get("category")))
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

def generate_event_report(target: str, content: str, context: dict | None = None) -> str:
    """SecurityHub 이벤트 보고서 HTML 생성 (MCP AWS 문서 참조)

    Args:
        target: 이벤트 대상 (리소스명, 서비스명 등)
        content: 이벤트 내용 설명
        context: ref_doc_ids로 병합된 canonical 컨텍스트 (선택)
    """
    ctx = context or {}

    event_code, service = _detect_event_info(ctx)
    aws_docs = _fetch_aws_docs(event_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회)\n{aws_docs}\n" if aws_docs else ""
    )
    context_section = (
        f"\n## 참고 컨텍스트 (이전 보고서)\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n"
        if ctx else ""
    )

    system = """
당신은 AWS 인프라 보안 이벤트 분석 전문가입니다.
이벤트 대상과 내용, 참고 컨텍스트를 분석하여 한국어 HTML 보고서를 생성하세요.

규칙:
1. 완전한 HTML 문서(<html>~</html>)를 반환하세요
2. 인라인 CSS로 깔끔하게 스타일링하세요 (외부 파일 금지)
3. 섹션: 이벤트 개요, 영향 분석, 원인 분석, 권장 조치, 참고 문서
4. 영어 텍스트는 자연스러운 한국어로 번역하세요
5. HTML 외 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
다음 이벤트 정보를 분석하여 HTML 보고서를 생성하세요.

이벤트 대상: {target}
이벤트 내용: {content}
{context_section}
{aws_docs_section}
""".strip()

    return call_claude(system, user)


def generate_weekly_report(target: str, content: str, context: dict | None = None) -> str:
    """주간 보고서 HTML 생성 (MCP AWS Well-Architected 문서 참조)

    Args:
        target: 보고 대상 (기간, 서비스명 등)
        content: 보고 내용 설명
        context: ref_doc_ids로 병합된 canonical 컨텍스트 (선택)
    """
    ctx = context or {}

    print("[MCP] 주간 보고서용 AWS Well-Architected 문서 조회 중...")
    wa_docs = _fetch_aws_docs_by_query(
        "AWS Well-Architected Framework security reliability best practices weekly review"
    )
    wa_docs_section = (
        f"\n## AWS Well-Architected 가이드 (MCP 실시간 조회)\n{wa_docs}\n"
        if wa_docs else ""
    )
    context_section = (
        f"\n## 참고 컨텍스트 (이전 보고서)\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n"
        if ctx else ""
    )

    system = """
당신은 AWS 인프라 주간 보고서 생성 전문가입니다.
보고 대상과 내용, 참고 컨텍스트를 분석하여 한국어 HTML 주간 보고서를 생성하세요.

규칙:
1. 완전한 HTML 문서(<html>~</html>)를 반환하세요
2. 인라인 CSS로 깔끔하게 스타일링하세요 (외부 파일 금지)
3. 섹션: 주간 요약, 주요 변경사항, 조치 항목(우선순위별), 전체 위험도, 참고 문서
4. AWS Well-Architected 가이드 내용을 조치 항목에 반영하세요
5. HTML 외 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
다음 정보를 분석하여 주간 보고서 HTML을 생성하세요.

보고 대상: {target}
보고 내용: {content}
{context_section}
{wa_docs_section}
""".strip()

    return call_claude(system, user)


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
        print(f"[MCP] 작업계획서용 AWS 문서 조회 중... (event: {event_code or service or 'unknown'})")
        aws_docs = _fetch_aws_docs(event_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회) — 작업 절차에 반영하세요\n{aws_docs}\n"
        if aws_docs else ""
    )
    context_section = (
        f"\n## 참고 컨텍스트 (이전 보고서)\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n"
        if ctx else ""
    )

    system = """
당신은 AWS 인프라 작업계획서 생성 전문가입니다.
작업 대상과 내용, 참고 컨텍스트를 분석하여 한국어 HTML 작업계획서를 생성하세요.

규칙:
1. 완전한 HTML 문서(<html>~</html>)를 반환하세요
2. 인라인 CSS로 깔끔하게 스타일링하세요 (외부 파일 금지)
3. 섹션: 개요(작업명/대상/담당자/예정일), 작업 단계(최대 6단계), 변경 전/후, 위험 분석, 롤백 계획
4. 작업 단계는 번호 매겨서 간결하게 (CLI 명령어 포함 금지)
5. HTML 외 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
다음 작업 정보를 분석하여 작업계획서 HTML을 생성하세요.

작업 대상: {target}
작업 내용: {content}
{context_section}
{aws_docs_section}
""".strip()

    return call_claude(system, user)


def generate_health_event_report(target: str, content: str, context: dict | None = None) -> str:
    """AWS Health 이벤트 보고서 HTML 생성 (MCP AWS 문서 참조)

    Args:
        target: 이벤트 대상 (서비스명, 리소스명 등)
        content: 이벤트 내용 (AWS Health raw JSON 또는 설명)
        context: ref_doc_ids로 병합된 canonical 컨텍스트 (선택)
    """
    ctx = context or {}

    # content가 JSON 문자열이면 파싱하여 eventTypeCode/service 추출
    raw: dict = {}
    if isinstance(content, str):
        try:
            raw = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass

    event_type_code = raw.get("detail", {}).get("eventTypeCode", "")
    service = raw.get("detail", {}).get("service", "") or target

    print(f"[MCP] Health 이벤트 보고서용 AWS 문서 조회 중... ({event_type_code or service})")
    aws_docs = _fetch_aws_docs(event_type_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회) — 권장 조치 작성에 반영하세요\n{aws_docs}\n"
        if aws_docs else ""
    )

    context_section = (
        f"\n## 참고 컨텍스트 (이전 보고서)\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n"
        if ctx else ""
    )

    system = """
당신은 AWS 인프라 운영 전문가입니다.
AWS Health 이벤트 정보와 AWS 공식 문서를 분석하여 한국어 HTML 이벤트 보고서를 생성하세요.

규칙:
1. 완전한 HTML 문서(<html>~</html>)를 반환하세요
2. 인라인 CSS로 깔끔하게 스타일링하세요 (외부 파일 금지)
3. 섹션: 이벤트 개요(문서번호/제목/감지일시), 타임라인, 이벤트 상세, 권장 조치(최소 3단계)
4. UTC 시각은 KST(+9시간)로 변환하세요
5. HTML 외 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
다음 AWS Health 이벤트 정보를 분석하여 이벤트 보고서 HTML을 생성하세요.

이벤트 대상: {target}
이벤트 내용: {content}
{context_section}
{aws_docs_section}
""".strip()

    return call_claude(system, user)


if __name__ == "__main__":
    from pathlib import Path
    sample_path = Path(__file__).parent.parent / "ui/src/data/health-eks-version-eol.json"
    raw_json = json.loads(sample_path.read_text())
    print("=== Health 이벤트 보고서 생성 테스트 (MCP) ===")
    result = generate_health_event_report("EKS", json.dumps(raw_json))
    print(result)
