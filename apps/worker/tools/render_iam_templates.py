from __future__ import annotations

import argparse
from pathlib import Path


def render(template: str, mapping: dict[str, str]) -> str:
    out = template
    for k, v in mapping.items():
        out = out.replace(f"{{{{{k}}}}}", v)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Render DnDn IAM onboarding templates for a customer account.")
    p.add_argument("--dndn-principal-arn", required=True, help="DnDn worker IAM role ARN in DnDn account")
    p.add_argument("--external-id", required=True, help="ExternalId shared with the customer")
    p.add_argument("--out-dir", default="out/iam_rendered", help="Directory to write rendered JSON files")
    args = p.parse_args()

    repo_root = Path(".")
    tmpl_dir = repo_root / "apps" / "worker" / "iam_templates"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mapping = {
        "DNDN_PRINCIPAL_ARN": args.dndn_principal_arn,
        "EXTERNAL_ID": args.external_id,
    }

    trust = (tmpl_dir / "customer_trust_policy.json").read_text(encoding="utf-8")
    perm = (tmpl_dir / "customer_permissions_policy.json").read_text(encoding="utf-8")

    trust_out = out_dir / "customer_trust_policy.rendered.json"
    perm_out = out_dir / "customer_permissions_policy.rendered.json"

    trust_out.write_text(render(trust, mapping), encoding="utf-8")
    perm_out.write_text(render(perm, mapping), encoding="utf-8")

    print("written:", trust_out)
    print("written:", perm_out)


if __name__ == "__main__":
    main()
