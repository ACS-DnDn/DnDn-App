\
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError

from dndn_worker.run_job import assume_role_session


def main() -> None:
    p = argparse.ArgumentParser(description="Smoke test CloudTrail lookup_events using assumed session.")
    p.add_argument("--role-arn", required=True, help="Role ARN to assume, or SELF")
    p.add_argument("--external-id", default="dndn-dev", help="ExternalId used in AssumeRole")
    p.add_argument("--region", default="ap-northeast-2")
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--max", type=int, default=20)
    args = p.parse_args()

    s = assume_role_session(args.role_arn, args.external_id)
    ct = s.client("cloudtrail", region_name=args.region)

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=args.hours)

    events = []
    token = None
    try:
        while True:
            kwargs = {"StartTime": start, "EndTime": end, "MaxResults": 50}
            if token:
                kwargs["NextToken"] = token
            resp = ct.lookup_events(**kwargs)
            events.extend(resp.get("Events", []))
            token = resp.get("NextToken")
            if not token or len(events) >= args.max:
                break
    except ClientError as e:
        print("❌ CloudTrail lookup failed:", e)
        raise

    print(f"✅ CloudTrail OK. fetched {len(events[:args.max])} events (last {args.hours}h)")
    for e in events[: min(args.max, 5)]:
        print("-", e.get("EventTime"), e.get("EventSource"), e.get("EventName"), "id=", e.get("EventId"))


if __name__ == "__main__":
    main()
