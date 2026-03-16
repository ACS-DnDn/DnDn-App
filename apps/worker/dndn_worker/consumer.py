from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import boto3

from dndn_worker.run_job import (
    WorkerExecutionError,
    WorkerExecutionResult,
    run_job_from_payload,
    validate_with_schema,
)


@dataclass(frozen=True)
class ConsumerConfig:
    queue_url: str
    repo_root: Path
    out_root: Path
    max_cloudtrail_events: int = 500
    wait_time_seconds: int = 20
    max_messages: int = 1
    visibility_timeout: Optional[int] = None


def _payload_schema_path(repo_root: Path) -> Path:
    return repo_root / "contracts" / "payload" / "job_payload.schema.json"


def _parse_payload(body: str) -> Dict[str, Any]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("SQS message body must be a JSON object payload.")
    return payload


def _delete_message(sqs_client: Any, queue_url: str, receipt_handle: str) -> None:
    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def process_message_body(body: str, config: ConsumerConfig) -> WorkerExecutionResult:
    payload = _parse_payload(body)
    try:
        validate_with_schema(payload, _payload_schema_path(config.repo_root))
    except ValueError as exc:
        raise WorkerExecutionError("INVALID_PAYLOAD", str(exc), retryable=False) from exc
    return run_job_from_payload(
        payload=payload,
        repo_root=config.repo_root,
        out_root=config.out_root,
        max_cloudtrail_events=config.max_cloudtrail_events,
    )


def process_sqs_message(sqs_client: Any, message: Dict[str, Any], config: ConsumerConfig) -> Optional[WorkerExecutionResult]:
    message_id = message.get("MessageId", "<unknown>")
    receipt_handle = message.get("ReceiptHandle")
    body = message.get("Body", "")

    if not receipt_handle:
        raise ValueError(f"SQS message {message_id} is missing ReceiptHandle.")

    try:
        result = process_message_body(body, config)
    except json.JSONDecodeError as exc:
        print(f"[consumer] dropping non-retryable message {message_id}: INVALID_PAYLOAD: {exc}")
        _delete_message(sqs_client, config.queue_url, receipt_handle)
        return None
    except WorkerExecutionError as exc:
        if exc.retryable:
            print(f"[consumer] leaving message {message_id} in queue for retry: {exc}")
            raise
        print(f"[consumer] dropping non-retryable message {message_id}: {exc}")
        _delete_message(sqs_client, config.queue_url, receipt_handle)
        return None
    except Exception as exc:
        print(f"[consumer] leaving message {message_id} in queue for retry: {exc}")
        raise

    _delete_message(sqs_client, config.queue_url, receipt_handle)
    outcome = "already processed" if result.already_processed else "processed"
    print(
        f"[consumer] {outcome} message {message_id}: "
        f"{result.result_path} (retryable={result.retryable}, error_code={result.error_code})"
    )
    return result


def poll_once(sqs_client: Any, config: ConsumerConfig) -> int:
    receive_kwargs: Dict[str, Any] = {
        "QueueUrl": config.queue_url,
        "MaxNumberOfMessages": config.max_messages,
        "WaitTimeSeconds": config.wait_time_seconds,
    }
    if config.visibility_timeout is not None:
        receive_kwargs["VisibilityTimeout"] = config.visibility_timeout

    response = sqs_client.receive_message(**receive_kwargs)
    messages = response.get("Messages", [])
    for message in messages:
        process_sqs_message(sqs_client, message, config)
    return len(messages)


def run_consumer_loop(sqs_client: Any, config: ConsumerConfig) -> None:
    while True:
        poll_once(sqs_client, config)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    return int(raw_value) if raw_value is not None else default


def _build_config(args: argparse.Namespace) -> ConsumerConfig:
    queue_url = args.queue_url or os.getenv("DNDN_WORKER_QUEUE_URL")
    if not queue_url:
        raise ValueError("queue URL is required via --queue-url or DNDN_WORKER_QUEUE_URL")

    repo_root = Path(args.repo_root)
    out_root = Path(args.out)
    return ConsumerConfig(
        queue_url=queue_url,
        repo_root=repo_root,
        out_root=out_root,
        max_cloudtrail_events=args.max_events,
        wait_time_seconds=args.wait_time_seconds,
        max_messages=args.max_messages,
        visibility_timeout=args.visibility_timeout,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Consume worker payload jobs from SQS.")
    parser.add_argument("--queue-url", default=None, help="SQS queue URL. Falls back to DNDN_WORKER_QUEUE_URL.")
    parser.add_argument("--repo-root", default=".", help="Repository root path (must contain contracts/).")
    parser.add_argument("--out", default="out", help="Local output directory for worker artifacts.")
    parser.add_argument("--max-events", type=int, default=_env_int("DNDN_WORKER_MAX_EVENTS", 500), help="Max CloudTrail events to pull per job.")
    parser.add_argument("--wait-time-seconds", type=int, default=_env_int("DNDN_WORKER_WAIT_TIME_SECONDS", 20), help="SQS long poll wait time.")
    parser.add_argument("--max-messages", type=int, default=_env_int("DNDN_WORKER_MAX_MESSAGES", 1), help="Max messages to receive per poll.")
    parser.add_argument("--visibility-timeout", type=int, default=None, help="Optional SQS visibility timeout override.")
    parser.add_argument("--once", action="store_true", help="Process at most one receive cycle and exit.")
    args = parser.parse_args()

    config = _build_config(args)
    sqs_client = boto3.client("sqs")

    if args.once:
        processed = poll_once(sqs_client, config)
        print(f"[consumer] receive cycle completed: {processed} message(s)")
        return

    run_consumer_loop(sqs_client, config)


if __name__ == "__main__":
    main()
