import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "render_iam_templates.py"
_SPEC = importlib.util.spec_from_file_location("render_iam_templates", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
render = _MODULE.render


def test_render_replaces_all_template_placeholders():
    template = """
{
  "Principal": "{{DNDN_PRINCIPAL_ARN}}",
  "Condition": {
    "StringEquals": {
      "sts:ExternalId": "{{EXTERNAL_ID}}"
    }
  }
}
"""

    rendered = render(
        template,
        {
            "DNDN_PRINCIPAL_ARN": "arn:aws:iam::123456789012:role/dndn-worker",
            "EXTERNAL_ID": "ext-1234",
        },
    )

    assert "{{DNDN_PRINCIPAL_ARN}}" not in rendered
    assert "{{EXTERNAL_ID}}" not in rendered
    assert "arn:aws:iam::123456789012:role/dndn-worker" in rendered
    assert "ext-1234" in rendered
