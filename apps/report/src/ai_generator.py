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


def call_claude(system_prompt: str, user_content: str) -> dict:
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
    text = result["content"][0]["text"]

    clean = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답 JSON 파싱 실패: {e}\n원문: {clean[:200]}")


# ─────────────────────────────────────────────────
# 보고서 생성 함수들
# ─────────────────────────────────────────────────

def generate_event_report(canonical: dict) -> dict:
    """SecurityHub 이벤트 보고서 생성 (MCP AWS 문서 참조)"""

    # MCP 문서 조회
    event_code, service = _detect_event_info(canonical)
    aws_docs = _fetch_aws_docs(event_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회)\n{aws_docs}\n" if aws_docs else ""
    )

    system = """
당신은 AWS 인프라 보안 이벤트 분석 전문가입니다.
canonical JSON 데이터와 AWS 공식 문서를 분석하여 보강된 canonical JSON을 반환하세요.

규칙:
1. 입력 canonical 구조를 그대로 유지하세요
2. 영어로 된 description, title 등 텍스트 필드를 자연스러운 한국어로 번역하세요
3. resources[].extensions.security_finding 안의 다음 필드를 보강하세요:
   - description: 한국어로 번역 + 구체적 위험 설명 추가
   - title: 한국어로 번역
   - ai_analysis: 새로 추가 { "cause": "원인 분석", "impact": "영향 분석", "recommendation": "AWS 공식 문서 기반 권장 조치" }
4. 반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
다음 canonical JSON을 분석하고 보강하여 반환하세요.

입력:
{json.dumps(canonical, ensure_ascii=False, indent=2)}
{aws_docs_section}
""".strip()

    result = call_claude(system, user)
    if isinstance(result, dict) and aws_docs:
        result["aws_docs"] = aws_docs
    return result


def generate_weekly_report(canonical: dict) -> dict:
    """주간 보고서 생성 (MCP AWS Well-Architected 문서 참조)"""

    # 주간 보고서는 여러 이벤트 종합 → Well-Architected + 보안 필라 조회
    print("[MCP] 주간 보고서용 AWS Well-Architected 문서 조회 중...")
    wa_docs = _fetch_aws_docs_by_query(
        "AWS Well-Architected Framework security reliability best practices weekly review"
    )
    wa_docs_section = (
        f"\n## AWS Well-Architected 가이드 (MCP 실시간 조회)\n{wa_docs}\n"
        if wa_docs else ""
    )

    system = """
당신은 AWS 인프라 주간 보고서 생성 전문가입니다.
canonical JSON 데이터와 AWS Well-Architected 가이드를 분석하여 보강된 canonical JSON을 반환하세요.

규칙:
1. 입력 canonical 구조를 그대로 유지하세요
2. 영어 텍스트를 한국어로 번역하세요
3. AWS Well-Architected 가이드가 있으면 action_items 작성에 반드시 반영하세요
4. canonical 최상위에 ai_summary 필드를 추가하세요:
   {
     "ai_summary": {
       "weekly_summary": "이번 주 전체 요약 (2~3문장, AWS Well-Architected 관점 포함)",
       "highlights": ["주요 변경사항 1", "주요 변경사항 2"],
       "action_items": [{"category": "Security|Reliability|Cost|Performance", "item": "AWS 공식 권고 기반 조치 항목", "priority": "HIGH|MEDIUM|LOW"}],
       "overall_risk": "HIGH|MEDIUM|LOW"
     }
   }
5. 반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
다음 canonical JSON을 분석하고 보강하여 반환하세요.

입력:
{json.dumps(canonical, ensure_ascii=False, indent=2)}
{wa_docs_section}
""".strip()

    result = call_claude(system, user)
    if isinstance(result, dict) and wa_docs:
        result["aws_docs"] = wa_docs
    return result


def generate_work_plan(canonical: dict) -> dict:
    """작업계획서 생성 (MCP AWS 문서 참조)"""

    # 이미 보고서에 aws_docs가 있으면 재사용 (MCP 조회 스킵)
    aws_docs = canonical.get("aws_docs", "")
    if aws_docs:
        print("[MCP] 작업계획서: aws_docs 재사용 (MCP 조회 스킵)")
    else:
        event_code, service = _detect_event_info(canonical)
        print(f"[MCP] 작업계획서용 AWS 문서 조회 중... (event: {event_code or service or 'unknown'})")
        aws_docs = _fetch_aws_docs(event_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회) — 작업 절차에 반영하세요\n{aws_docs}\n"
        if aws_docs else ""
    )

    system = """
당신은 AWS 인프라 작업계획서 생성 전문가입니다.
이벤트 보고서를 분석하여 간결한 작업계획서 JSON을 생성하세요.

규칙:
1. 작업 단계는 최대 6단계로 제한하세요
2. 각 단계 description은 2줄 이내로 작성하세요 (CLI 명령어 포함 금지)
3. AWS 공식 문서가 있으면 URL만 참고 링크로 표시하세요
4. before_after는 핵심 변경사항 1~3개만 포함하세요
5. 반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
다음 이벤트 데이터를 분석하여 작업계획서를 생성하세요.

입력:
{json.dumps(canonical, ensure_ascii=False, indent=2)}
{aws_docs_section}

다음 JSON 형식으로 반환하세요:
{{
  "title": "작업명 (한국어)",
  "reason": "작업 이유 (한국어, 구체적으로)",
  "resource": "대상 리소스 ID",
  "account_id": "AWS 계정 ID",
  "scheduled_at": "권장 작업 예정일 또는 즉시",
  "assignee": "devops@dndn",
  "before_after": [
    {{"item": "항목명", "before": "변경 전 상태", "after": "변경 후 상태"}}
  ],
  "risks": [
    {{"item": "위험 항목", "level": "HIGH|MEDIUM|LOW", "description": "위험 분석"}}
  ],
  "rollback": {{
    "trigger": "롤백 트리거 조건",
    "method": "롤백 방법",
    "estimated_time": "예상 소요 시간",
    "assignee": "devops@dndn"
  }},
  "steps": [
    {{"name": "단계명", "description": "작업 내용", "executor": "Terraform|수동", "assignee": "자동|devops"}}
  ],
  "pr_url": ""
}}
""".strip()

    return call_claude(system, user)


def generate_health_event_report(raw: dict) -> dict:
    """AWS Health raw JSON → 이벤트 보고서 (MCP AWS 문서 참조)"""

    event_type_code = raw.get("detail", {}).get("eventTypeCode", "")
    service = raw.get("detail", {}).get("service", "")

    print(f"[MCP] Health 이벤트 보고서용 AWS 문서 조회 중... ({event_type_code})")
    aws_docs = _fetch_aws_docs(event_type_code, service)
    aws_docs_section = (
        f"\n## AWS 공식 문서 (MCP 실시간 조회) — 권장 조치 작성에 반영하세요\n{aws_docs}\n"
        if aws_docs else ""
    )

    system = """
당신은 AWS 인프라 운영 전문가입니다.
AWS Health EventBridge 이벤트 JSON과 AWS 공식 문서를 분석하여 이벤트 보고서 데이터를 생성하세요.

규칙:
1. 모든 텍스트는 자연스러운 한국어로 작성하세요
2. UTC 시각은 KST(+9시간)로 변환하세요
3. 문서번호 형식: DOC-HEALTH-{YYYYMMDD}-{서비스코드}
4. 권장 조치는 AWS 공식 문서 기반으로 구체적이고 실행 가능하게 작성하세요 (최소 3단계)
5. 반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요

반환할 JSON 구조:
{
  "문서번호": "DOC-HEALTH-YYYYMMDD-XXX",
  "작성일": "YYYY.MM.DD HH:MM",
  "이벤트_제목": "한 줄 제목",
  "overview": {
    "이벤트_한줄_설명": "무엇이 어떻게 되는지 한 줄 요약",
    "대상_리소스": "리소스명 또는 ID",
    "리전": "ap-northeast-2",
    "AWS_계정_ID": "계정 ID",
    "이벤트_카테고리": "scheduledChange | issue | accountNotification",
    "감지_일시": "YYYY.MM.DD HH:MM:SS"
  },
  "이벤트_개요": {
    "감지_출처": "AWS Health — {eventTypeCode}",
    "이벤트_ARN": "arn:aws:health:...",
    "이벤트_상태": "upcoming | open | closed",
    "감지_일시": "YYYY.MM.DD HH:MM:SS"
  },
  "타임라인": [
    { "시각": "HH:MM:SS", "구분": "AWS Health", "내용": "이벤트 발생 내용" },
    { "시각": "HH:MM:SS", "구분": "EventBridge", "내용": "DnDn Worker 트리거 → canonical.json 생성" }
  ],
  "이벤트_상세": {
    "이벤트_유형_코드": "AWS_EKS_PLANNED_LIFECYCLE_EVENT",
    "이벤트_카테고리": "scheduledChange",
    "이벤트_상태": "upcoming",
    "이벤트_상세_설명": "원문 영어 설명을 한국어로 번역한 전체 내용"
  },
  "권장_조치": [
    { "조치_구분": "사전 준비", "순서": "①", "조치_내용": "구체적 조치 내용" },
    { "조치_구분": "실행", "순서": "②", "조치_내용": "구체적 조치 내용" },
    { "조치_구분": "검증", "순서": "③", "조치_내용": "구체적 조치 내용" }
  ]
}
""".strip()

    user = f"""
다음 AWS Health EventBridge JSON을 분석하여 이벤트 보고서 데이터를 생성하세요.

입력:
{json.dumps(raw, ensure_ascii=False, indent=2)}
{aws_docs_section}
""".strip()

    return call_claude(system, user)


if __name__ == "__main__":
    from pathlib import Path
    sample_path = Path(__file__).parent.parent / "ui/src/data/health-eks-version-eol.json"
    raw = json.loads(sample_path.read_text())
    print("=== Health 이벤트 보고서 생성 테스트 (MCP) ===")
    result = generate_health_event_report(raw)
    print(json.dumps(result, ensure_ascii=False, indent=2))
