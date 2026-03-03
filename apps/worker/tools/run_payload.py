\
from __future__ import annotations

import argparse
from pathlib import Path

from dndn_worker.run_job import run_job_from_payload_file


def main() -> None:
    p = argparse.ArgumentParser(description="Run DnDn worker job locally from a payload JSON file.")
    p.add_argument("--payload", required=True, help="Path to payload JSON (see contracts/payload/*.sample.json)")
    p.add_argument("--repo-root", default=".", help="Repository root path (must contain contracts/)")
    p.add_argument("--out", default="out", help="Local output directory (raw/normalized will be created inside)")
    p.add_argument("--max-events", type=int, default=500, help="Max CloudTrail events to pull (MVP safeguard)")
    args = p.parse_args()

    payload_path = Path(args.payload)
    repo_root = Path(args.repo_root)
    out_root = Path(args.out)

    result_path = run_job_from_payload_file(
        payload_path=payload_path,
        repo_root=repo_root,
        out_root=out_root,
        max_cloudtrail_events=args.max_events,
    )
    print(f"✅ Done. normalized file: {result_path}")


if __name__ == "__main__":
    main()
