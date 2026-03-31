from src.opa_engine import _REGO_HEADER, generate_rego, parse_tf_files


def test_parse_tf_files_merges_valid_resources_and_skips_invalid_files():
    merged = parse_tf_files(
        {
            "main.tf": """
resource "aws_s3_bucket" "first" {
  bucket = "bucket-a"
}
""",
            "extra.tf": """
resource "aws_s3_bucket" "second" {
  bucket = "bucket-b"
}
""",
            "broken.tf": 'resource "aws_s3_bucket" "broken" {',
        }
    )

    assert "resource" in merged
    assert len(merged["resource"]) == 2
    buckets = {
        name: conf["bucket"]
        for block in merged["resource"]
        for _, resources in block.items()
        for name, conf in resources.items()
    }
    assert buckets["first"] == "bucket-a"
    assert buckets["second"] == "bucket-b"


def test_generate_rego_returns_header_when_no_policy_is_enabled():
    rego = generate_rego(
        [
            {
                "items": [
                    {
                        "key": "net-sg-open",
                        "label": "보안그룹 과다 개방",
                        "severity": "high",
                        "on": False,
                    }
                ]
            }
        ]
    )

    assert rego == _REGO_HEADER


def test_generate_rego_includes_custom_values_and_exceptions():
    rego = generate_rego(
        [
            {
                "items": [
                    {
                        "key": "net-sg-open",
                        "label": "보안그룹 과다 개방",
                        "severity": "high",
                        "on": True,
                        "params": {"values": ["10.0.0.0/8", "192.168.0.0/16"]},
                        "exceptions": ["trusted_sg"],
                    }
                ]
            }
        ]
    )

    assert '# 보안그룹 과다 개방' in rego
    assert '"severity": "high"' in rego
    assert 'not cidr in {"10.0.0.0/8", "192.168.0.0/16"}' in rego
    assert 'not name in {"trusted_sg"}' in rego
