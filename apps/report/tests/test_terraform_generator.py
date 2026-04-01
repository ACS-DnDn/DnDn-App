from src.terraform_generator import _build_deploy_log_section, _build_user_prompt, _extract_resource_hints, _summarize_tf_code


def test_extract_resource_hints_deduplicates_and_limits_results():
    hints = _extract_resource_hints(
        {
            "title": "EC2 와 S3 보안 그룹 점검",
            "steps": [
                {"description": "EC2 인스턴스와 보안그룹을 점검합니다."},
                {"description": "S3 버킷과 IAM 권한을 검토합니다."},
                {"description": "CloudTrail, VPC, Lambda, RDS 설정도 확인합니다."},
            ],
        }
    )

    assert len(hints) == 5
    assert len(set(hints)) == len(hints)
    assert "aws_instance" in hints
    assert "aws_s3_bucket" in hints
    assert "aws_vpc" in hints


def test_build_deploy_log_section_only_includes_failures():
    section = _build_deploy_log_section(
        [
            {
                "event": "checks_failed",
                "status": "failure",
                "description": "tflint 실패",
                "context": "lint",
            },
            {
                "event": "apply_failed",
                "status": "failure",
                "description": "권한 부족",
            },
            {
                "event": "merged",
                "status": "success",
                "description": "머지 완료",
            },
        ]
    )

    assert "이전 배포 실패 이력" in section
    assert "- [PR 검증 실패] (lint): tflint 실패" in section
    assert "- [Terraform Apply 실패]: 권한 부족" in section
    assert "머지 완료" not in section


def test_build_deploy_log_section_returns_empty_when_no_failure():
    assert _build_deploy_log_section([]) == ""
    assert _build_deploy_log_section([{"event": "merged", "status": "success"}]) == ""


def test_build_user_prompt_includes_all_sections():
    prompt = _build_user_prompt(
        '{"title":"보안그룹 수정"}',
        'resource "aws_security_group" "main" {}',
        "\n## AWS docs\nsg docs\n",
        "\n## Best practices\nbp\n",
        "\n## OPA\nopa rules\n",
        "\n## Deploy log\nfailed before\n",
    )

    assert "## 작업계획서" in prompt
    assert '{"title":"보안그룹 수정"}' in prompt
    assert 'resource "aws_security_group" "main" {}' in prompt
    assert "## AWS docs" in prompt
    assert "## Best practices" in prompt
    assert "## OPA" in prompt
    assert "## Deploy log" in prompt
    assert '"files"' in prompt
    assert '"summary"' in prompt


def test_summarize_tf_code_returns_small_input_unchanged():
    tf_text = 'resource "aws_s3_bucket" "main" {}'

    assert _summarize_tf_code(tf_text) == tf_text
