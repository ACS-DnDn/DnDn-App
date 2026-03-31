from src.ai_generator import _detect_event_info, _style_rules, _wrap_html


def test_detect_event_info_prefers_health_event_payload():
    code, service = _detect_event_info(
        {
            "source": "aws.health",
            "detail": {
                "eventTypeCode": "AWS_EC2_MAINTENANCE_SCHEDULED",
                "service": "EC2",
            },
        }
    )

    assert code == "AWS_EC2_MAINTENANCE_SCHEDULED"
    assert service == "EC2"


def test_detect_event_info_falls_back_to_securityhub_marker():
    code, service = _detect_event_info(
        {
            "resources": [
                {
                    "extensions": {
                        "security_finding": {
                            "Title": "취약점 탐지",
                        }
                    }
                }
            ]
        }
    )

    assert code == "SOFTWARE_VULNERABILITY"
    assert service == "SecurityHub"


def test_wrap_html_removes_leading_plain_text_before_doc_root():
    html = _wrap_html(
        "테스트 문서",
        """
설명 문구는 제거되어야 합니다.
<div class="doc"><div class="doc-header-title">본문</div></div>
""",
    )

    assert html.startswith("<!DOCTYPE html>")
    assert "설명 문구는 제거되어야 합니다." not in html
    assert '<div class="doc"><div class="doc-header-title">본문</div></div>' in html


def test_style_rules_includes_doc_meta_values():
    rules = _style_rules(
        {
            "company_logo_url": "https://example.com/logo.png",
            "doc_num": "2026-WS-PLN-0001",
            "author_label": "홍길동 팀장",
        }
    )

    assert 'src="https://example.com/logo.png"' in rules
    assert "문서번호: 2026-WS-PLN-0001" in rules
    assert "작업 담당자" in rules
    assert "홍길동 팀장" in rules
