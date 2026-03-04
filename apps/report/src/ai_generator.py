import json
import boto3
from typing import Any

MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
REGION = "ap-northeast-2"


def get_bedrock_client():
    return boto3.client("bedrock-runtime", region_name=REGION)


def call_claude(system_prompt: str, user_content: str) -> dict:
    client = get_bedrock_client()

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
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

    # JSON 파싱
    clean = text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(clean)


def generate_event_report(canonical: dict) -> dict:
    system = """
당신은 AWS 인프라 변경 관리 자동화 플랫폼 DnDn의 보고서 생성 AI입니다.
canonical.json 데이터를 분석해서 이벤트 보고서 섹션 데이터를 JSON으로 반환하세요.
반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요.
""".strip()

    user = f"""
다음 canonical.json을 분석해서 이벤트 보고서 데이터를 생성해주세요.

canonical.json:
{json.dumps(canonical, ensure_ascii=False, indent=2)}

다음 JSON 형식으로 반환하세요:
{{
  "summary": "이벤트 한 줄 요약",
  "impact": "영향 범위 설명",
  "cause": "발생 원인 분석",
  "recommendation": "권장 조치 사항",
  "risk_level": "HIGH | MEDIUM | LOW",
  "risks": [
    {{"item": "위험 항목", "level": "HIGH | MEDIUM | LOW", "description": "분석 내용"}}
  ]
}}
""".strip()

    return call_claude(system, user)


def generate_weekly_report(canonical: dict) -> dict:
    system = """
당신은 AWS 인프라 변경 관리 자동화 플랫폼 DnDn의 보고서 생성 AI입니다.
canonical.json 데이터를 분석해서 주간 보고서 요약 데이터를 JSON으로 반환하세요.
반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요.
""".strip()

    user = f"""
다음 canonical.json을 분석해서 주간 보고서 요약을 생성해주세요.

canonical.json:
{json.dumps(canonical, ensure_ascii=False, indent=2)}

다음 JSON 형식으로 반환하세요:
{{
  "summary": "이번 주 전체 요약 (2~3문장)",
  "highlights": ["주요 변경사항 1", "주요 변경사항 2"],
  "action_items": [
    {{"category": "카테고리", "item": "조치 항목", "priority": "HIGH | MEDIUM | LOW"}}
  ],
  "overall_risk": "HIGH | MEDIUM | LOW"
}}
""".strip()

    return call_claude(system, user)


def generate_work_plan(canonical: dict) -> dict:
    system = """
당신은 AWS 인프라 변경 관리 자동화 플랫폼 DnDn의 보고서 생성 AI입니다.
canonical.json 데이터를 분석해서 작업계획서 초안을 JSON으로 반환하세요.
반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요.
""".strip()

    user = f"""
다음 canonical.json을 분석해서 작업계획서 초안을 생성해주세요.

canonical.json:
{json.dumps(canonical, ensure_ascii=False, indent=2)}

다음 JSON 형식으로 반환하세요:
{{
  "title": "작업명",
  "reason": "작업 이유",
  "resource": "대상 리소스 ID",
  "account_id": "AWS 계정 ID",
  "scheduled_at": "작업 예정일 (권장 일정)",
  "assignee": "devops@dndn",
  "before_after": [
    {{"item": "항목명", "before": "변경 전", "after": "변경 후"}}
  ],
  "risks": [
    {{"item": "위험 항목", "level": "HIGH | MEDIUM | LOW", "description": "분석"}}
  ],
  "rollback": {{
    "trigger": "롤백 트리거 조건",
    "method": "롤백 방법",
    "estimated_time": "예상 시간",
    "assignee": "devops@dndn"
  }},
  "steps": [
    {{"name": "작업명", "description": "작업 내용", "executor": "Terraform | 수동", "assignee": "devops | 자동"}}
  ],
  "pr_url": ""
}}
""".strip()

    return call_claude(system, user)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # 경로 수정
    sample_path = Path(__file__).parent.parent.parent.parent / "contracts" / "samples" / "event.sample.json"
    print(f"경로 확인: {sample_path}")
    canonical = json.loads(sample_path.read_text())

    print("=== 이벤트 보고서 생성 테스트 ===")
    result = generate_event_report(canonical)
    print(json.dumps(result, ensure_ascii=False, indent=2))