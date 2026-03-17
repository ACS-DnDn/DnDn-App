"""generate_* 함수 단위 테스트

Bedrock / S3 / MCP를 모두 mock하여 실제 AWS 호출 없이 검증.

실행:
    cd apps/report
    uv run pytest tests/test_generators.py -v
"""

import json
from unittest.mock import MagicMock, patch


# ── 공통 픽스처 ───────────────────────────────────────────


def _mock_bedrock_response(html_body: str):
    """invoke_model 응답 mock 생성"""
    payload = {"content": [{"text": html_body}]}
    mock_resp = MagicMock()
    mock_resp["body"].read.return_value = json.dumps(payload).encode()
    return mock_resp


FAKE_HTML_BODY = '<div class="doc"><div class="doc-header-title">테스트</div></div>'


# ── EVENT 보고서 ──────────────────────────────────────────


EVENT_CANONICAL = {
    "meta": {
        "type": "EVENT",
        "run_id": "evt-001",
        "title": "EC2 예약 점검",
        "account_id": "123456789012",
    },
    "content": "EC2 인스턴스 예약 점검 이벤트",
    "resources": [
        {
            "resource_id": "i-0abc123",
            "extensions": {
                "aws_health": {
                    "event_type_code": "AWS_EC2_INSTANCE_STOP_SCHEDULED",
                    "service": "EC2",
                    "start_time": "2026-03-20T00:00:00Z",
                    "end_time": "2026-03-20T04:00:00Z",
                    "description": "예약된 하드웨어 유지 보수",
                },
                "actionability": {
                    "priority": "high",
                    "recommended_actions": ["인스턴스 중지 계획 수립", "EIP 재연결 확인"],
                },
            },
        }
    ],
}


def test_generate_event_report_returns_html():
    from src.ai_generator import generate_event_report

    with (
        patch("src.ai_generator.get_bedrock_client") as mock_bc,
        patch("src.ai_generator._fetch_aws_docs", return_value=""),
    ):
        mock_bc.return_value.invoke_model.return_value = _mock_bedrock_response(
            FAKE_HTML_BODY
        )
        result = generate_event_report(EVENT_CANONICAL)

    assert "<!DOCTYPE html>" in result
    assert "<style>" in result
    assert FAKE_HTML_BODY in result


def test_generate_event_report_extracts_event_type():
    """aws_health.event_type_code가 MCP 조회에 전달되는지 확인"""
    from src.ai_generator import generate_event_report

    with (
        patch("src.ai_generator.get_bedrock_client") as mock_bc,
        patch("src.ai_generator._fetch_aws_docs", return_value="") as mock_docs,
    ):
        mock_bc.return_value.invoke_model.return_value = _mock_bedrock_response(
            FAKE_HTML_BODY
        )
        generate_event_report(EVENT_CANONICAL)

    mock_docs.assert_called_once_with("AWS_EC2_INSTANCE_STOP_SCHEDULED", "EC2")


# ── WEEKLY 보고서 ─────────────────────────────────────────


WEEKLY_CANONICAL = {
    "meta": {
        "type": "WEEKLY",
        "run_id": "weekly-20260310",
        "title": "2026년 3월 2주차 주간 보고서",
        "account_id": "123456789012",
        "period": {"start": "2026-03-10", "end": "2026-03-16"},
    },
    "content": "주간 인프라 변경 내역",
    "extensions": {
        "advisor_rollup": {"critical": 1, "warning": 4, "ok": 23},
        "advisor_checks": [
            {"name": "S3 버킷 퍼블릭 접근", "status": "warning", "affected": 2}
        ],
        "access_analyzer_rollup": {"active": 3, "archived": 1},
        "access_analyzer_findings": [
            {"id": "af-001", "resource": "arn:aws:s3:::my-bucket", "status": "active"}
        ],
        "cost_explorer_summary": {
            "total_usd": 1234.56,
            "prev_total_usd": 1100.00,
            "delta_pct": 12.2,
        },
        "cost_explorer_groups": [
            {"service": "Amazon EC2", "usd": 600.0, "prev_usd": 550.0}
        ],
        "cloudwatch_rollup": {"alarm": 2, "ok": 18, "insufficient_data": 1},
        "cloudwatch_alarms": [
            {"name": "CPU-High", "state": "ALARM", "metric": "CPUUtilization"}
        ],
    },
}


def test_generate_weekly_report_returns_html():
    from src.ai_generator import generate_weekly_report

    with (
        patch("src.ai_generator.get_bedrock_client") as mock_bc,
        patch("src.ai_generator._fetch_aws_docs_by_query", return_value=""),
    ):
        mock_bc.return_value.invoke_model.return_value = _mock_bedrock_response(
            FAKE_HTML_BODY
        )
        result = generate_weekly_report(WEEKLY_CANONICAL)

    assert "<!DOCTYPE html>" in result
    assert FAKE_HTML_BODY in result


def test_generate_weekly_report_includes_extension_data():
    """extension 데이터가 Claude에 전달되는지 user 프롬프트로 검증"""
    from src.ai_generator import generate_weekly_report

    captured_user = []

    def fake_invoke(system_prompt, user_content):
        captured_user.append(user_content)
        return FAKE_HTML_BODY

    with (
        patch("src.ai_generator._invoke_claude", side_effect=fake_invoke),
        patch("src.ai_generator._fetch_aws_docs_by_query", return_value=""),
    ):
        generate_weekly_report(WEEKLY_CANONICAL)

    user_prompt = captured_user[0]
    assert "advisor_rollup" in user_prompt or "Trusted Advisor" in user_prompt
    assert "cost_explorer_summary" in user_prompt or "비용" in user_prompt
    assert "cloudwatch_rollup" in user_prompt or "CloudWatch" in user_prompt


# ── HEALTH 보고서 ─────────────────────────────────────────


HEALTH_CANONICAL = {
    "meta": {
        "type": "HEALTH",
        "run_id": "health-eks-001",
        "title": "EKS 버전 EOL",
        "account_id": "123456789012",
    },
    "resources": [
        {
            "resource_id": "arn:aws:eks:ap-northeast-2:123456789012:cluster/my-cluster",
            "extensions": {
                "aws_health": {
                    "event_type_code": "AWS_EKS_PLANNED_LIFECYCLE_EVENT",
                    "service": "EKS",
                    "start_time": "2026-04-01T00:00:00Z",
                    "description": "EKS 1.25 버전 지원 종료 예정",
                },
                "actionability": {
                    "priority": "critical",
                    "deadline": "2026-04-01",
                    "recommended_actions": ["EKS 1.28로 업그레이드"],
                },
            },
        }
    ],
}


def test_generate_health_event_report_returns_html():
    from src.ai_generator import generate_health_event_report

    with (
        patch("src.ai_generator.get_bedrock_client") as mock_bc,
        patch("src.ai_generator._fetch_aws_docs", return_value=""),
    ):
        mock_bc.return_value.invoke_model.return_value = _mock_bedrock_response(
            FAKE_HTML_BODY
        )
        result = generate_health_event_report(HEALTH_CANONICAL)

    assert "<!DOCTYPE html>" in result
    assert FAKE_HTML_BODY in result


def test_generate_health_event_report_title():
    """제목이 service 이름을 포함하는지 확인"""
    from src.ai_generator import generate_health_event_report

    with (
        patch("src.ai_generator.get_bedrock_client") as mock_bc,
        patch("src.ai_generator._fetch_aws_docs", return_value=""),
    ):
        mock_bc.return_value.invoke_model.return_value = _mock_bedrock_response(
            FAKE_HTML_BODY
        )
        result = generate_health_event_report(HEALTH_CANONICAL)

    assert "EKS" in result or "Health" in result


# ── _wrap_html ────────────────────────────────────────────


def test_wrap_html_structure():
    from src.ai_generator import _wrap_html, _BASE_CSS

    html = _wrap_html("테스트 문서", '<div class="doc">내용</div>')
    assert "<!DOCTYPE html>" in html
    assert "<title>테스트 문서</title>" in html
    assert _BASE_CSS in html
    assert '<div class="doc">내용</div>' in html
