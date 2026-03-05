from __future__ import annotations

import argparse
import boto3
from botocore.exceptions import ClientError

from dndn_worker.run_job import assume_role_session


def main() -> None:
    """
    Run a command-line smoke test that attempts to assume the given AWS role and reports the caller identity.
    
    Parses command-line arguments (--role-arn, --external-id, --run-id), attempts to assume the specified role using assume_role_session, calls STS GetCallerIdentity on the resulting session, and prints success information (Account and Arn) or a failure message.
    
    Raises:
        botocore.exceptions.ClientError: If the STS AssumeRole or GetCallerIdentity call fails; the exception is re-raised after printing an error message.
    """
    p = argparse.ArgumentParser(description="Smoke test STS AssumeRole (or SELF).")
    p.add_argument("--role-arn", required=True, help="Role ARN to assume, or SELF")
    p.add_argument("--external-id", default="dndn-dev", help="ExternalId used in AssumeRole")
    p.add_argument("--run-id", default="smoke-assume", help="Run id used for RoleSessionName")
    args = p.parse_args()

    try:
        s = assume_role_session(
            role_arn=args.role_arn,
            external_id=args.external_id,
            run_id=args.run_id,
        )
        me = s.client("sts").get_caller_identity()
        print("✅ ASSUME ROLE OK")
        print("Account:", me.get("Account"))
        print("Arn:", me.get("Arn"))
    except ClientError as e:
        print("❌ ASSUME ROLE FAILED:", e)
        raise


if __name__ == "__main__":
    main()
