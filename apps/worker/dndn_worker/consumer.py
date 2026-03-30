from __future__ import annotations

import argparse
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import boto3
from prometheus_client import Counter, Histogram, start_http_server

from dndn_worker.run_job import (
    WorkerExecutionError,
    WorkerExecutionResult,
    run_job_from_payload,
    validate_with_schema,
)


# 메트릭 정의
SQS_MESSAGES_TOTAL = Counter(
    "sqs_messages_total",
    "Total SQS messages received",
    ["outcome"],  # outcome: processed, dropped, retried
)
SQS_MESSAGE_DURATION = Histogram(
    "sqs_message_duration_seconds",
    "SQS message processing duration in seconds",
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
    heartbeat_interval_seconds: int = 0


def _payload_schema_path(repo_root: Path) -> Path:
    return repo_root / "contracts" / "payload" / "job_payload.schema.json"


def _parse_payload(body: str) -> Dict[str, Any]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("SQS message body must be a JSON object payload.")
    return payload


def _delete_message(sqs_client: Any, queue_url: str, receipt_handle: str) -> None:
    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def _change_message_visibility(sqs_client: Any, queue_url: str, receipt_handle: str, timeout_seconds: int) -> None:
    sqs_client.change_message_visibility(
        QueueUrl=queue_url,
        ReceiptHandle=receipt_handle,
        VisibilityTimeout=timeout_seconds,
    )


def _resolve_heartbeat_interval_seconds(config: ConsumerConfig) -> int:
    if config.visibility_timeout is None or config.visibility_timeout <= 0:
        return 0
    if config.visibility_timeout <= 1:
        raise ValueError("visibility_timeout must be greater than 1 when heartbeat is enabled")
    if config.heartbeat_interval_seconds > 0:
        if config.heartbeat_interval_seconds >= config.visibility_timeout:
            raise ValueError("heartbeat interval must be smaller than visibility timeout")
        return config.heartbeat_interval_seconds
    return min(
        max(1, config.visibility_timeout // 3),
        config.visibility_timeout - 1,
    )


def _start_message_heartbeat(
    sqs_client: Any,
    config: ConsumerConfig,
    message_id: str,
    receipt_handle: str,
) -> Optional[tuple[threading.Event, threading.Thread]]:
    visibility_timeout = config.visibility_timeout
    if visibility_timeout is None or visibility_timeout <= 0:
        return None

    interval_seconds = _resolve_heartbeat_interval_seconds(config)
    if interval_seconds <= 0:
        return None

    stop_event = threading.Event()

    def _heartbeat_loop() -> None:
        while not stop_event.wait(interval_seconds):
            try:
                _change_message_visibility(
                    sqs_client=sqs_client,
                    queue_url=config.queue_url,
                    receipt_handle=receipt_handle,
                    timeout_seconds=visibility_timeout,
                )
                print(
                    f"[consumer] heartbeat extended visibility for {message_id} "
                    f"by {visibility_timeout}s"
                )
            except Exception as exc:
                print(f"[consumer] heartbeat failed for {message_id}: {exc}")
                return

    thread = threading.Thread(
        target=_heartbeat_loop,
        name=f"dndn-sqs-heartbeat-{message_id}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _stop_message_heartbeat(heartbeat: Optional[tuple[threading.Event, threading.Thread]]) -> None:
    if heartbeat is None:
        return
    stop_event, thread = heartbeat
    stop_event.set()
    thread.join(timeout=1.0)


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

    heartbeat = _start_message_heartbeat(
        sqs_client=sqs_client,
        config=config,
        message_id=message_id,
        receipt_handle=receipt_handle,
    )
    start = time.perf_counter()
    try:
        try:
            result = process_message_body(body, config)
        except json.JSONDecodeError as exc:
            print(f"[consumer] dropping non-retryable message {message_id}: INVALID_PAYLOAD: {exc}")
            _delete_message(sqs_client, config.queue_url, receipt_handle)
            SQS_MESSAGES_TOTAL.labels(outcome="dropped").inc()
            return None
        except WorkerExecutionError as exc:
            if exc.retryable:
                print(f"[consumer] leaving message {message_id} in queue for retry: {exc}")
                SQS_MESSAGES_TOTAL.labels(outcome="retried").inc()
                return None
            print(f"[consumer] dropping non-retryable message {message_id}: {exc}")
            _delete_message(sqs_client, config.queue_url, receipt_handle)
            SQS_MESSAGES_TOTAL.labels(outcome="dropped").inc()
            return None
        except Exception as exc:
            print(f"[consumer] leaving message {message_id} in queue for retry: {type(exc).__name__}: {exc}")
            SQS_MESSAGES_TOTAL.labels(outcome="retried").inc()
            return None

        _delete_message(sqs_client, config.queue_url, receipt_handle)
        SQS_MESSAGES_TOTAL.labels(outcome="processed").inc()
        outcome = "already processed" if result.already_processed else "processed"
        print(
            f"[consumer] {outcome} message {message_id}: "
            f"{result.result_path} (retryable={result.retryable}, error_code={result.error_code})"
        )
        return result
    finally:
        SQS_MESSAGE_DURATION.observe(time.perf_counter() - start)
        _stop_message_heartbeat(heartbeat)


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
    config = ConsumerConfig(
        queue_url=queue_url,
        repo_root=repo_root,
        out_root=out_root,
        max_cloudtrail_events=args.max_events,
        wait_time_seconds=args.wait_time_seconds,
        max_messages=args.max_messages,
        visibility_timeout=args.visibility_timeout,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
    )
    # Validate heartbeat configuration early.
    _ = _resolve_heartbeat_interval_seconds(config)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Consume worker payload jobs from SQS.")
    parser.add_argument("--queue-url", default=None, help="SQS queue URL. Falls back to DNDN_WORKER_QUEUE_URL.")
    parser.add_argument("--repo-root", default=".", help="Repository root path (must contain contracts/).")
    parser.add_argument("--out", default="out", help="Local output directory for worker artifacts.")
    parser.add_argument("--max-events", type=int, default=_env_int("DNDN_WORKER_MAX_EVENTS", 500), help="Max CloudTrail events to pull per job.")
    parser.add_argument("--wait-time-seconds", type=int, default=_env_int("DNDN_WORKER_WAIT_TIME_SECONDS", 20), help="SQS long poll wait time.")
    parser.add_argument("--max-messages", type=int, default=_env_int("DNDN_WORKER_MAX_MESSAGES", 1), help="Max messages to receive per poll.")
    parser.add_argument("--visibility-timeout", type=int, default=None, help="Optional SQS visibility timeout override.")
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=_env_int("DNDN_WORKER_HEARTBEAT_INTERVAL_SECONDS", 0),
        help="Optional SQS heartbeat interval. 0 means auto-calculate from visibility timeout or disable when no timeout is set.",
    )
    parser.add_argument("--once", action="store_true", help="Process at most one receive cycle and exit.")
    args = parser.parse_args()

    config = _build_config(args)
    metrics_port = _env_int("DNDN_WORKER_METRICS_PORT", 9090)
    start_http_server(metrics_port)
    print(f"[consumer] Prometheus metrics server started on :{metrics_port}")
    sqs_client = boto3.client("sqs")

    if args.once:
        processed = poll_once(sqs_client, config)
        print(f"[consumer] receive cycle completed: {processed} message(s)")
        return

    run_consumer_loop(sqs_client, config)


if __name__ == "__main__":
    main()
