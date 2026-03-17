"""SQS Worker — S3 이벤트 알림 수신 → HTML 자동 생성 → S3 저장

실행:
    python -m src.sqs_worker

환경변수:
    SQS_QUEUE_URL   - SQS 큐 URL (필수)
    AWS_REGION      - 리전 (기본: ap-northeast-2)
    S3_BUCKET       - S3 버킷명 (기본: dndn-reports)
    POLL_INTERVAL   - 폴링 대기 없을 때 sleep 초 (기본: 5)
"""
import json
import os
import time
import logging
import urllib.parse

import boto3
from dotenv import load_dotenv

load_dotenv()

from .ai_generator import generate_event_report, generate_weekly_report, generate_health_event_report
from .s3_client import get_report, save_report_html, _client as _s3_client, S3_BUCKET

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))


def _sqs_client():
    return boto3.client("sqs", region_name=REGION)


def _html_exists(doc_id: str, account_id: str) -> bool:
    """이미 HTML이 S3에 존재하면 스킵"""
    key = f"{account_id}/reports/{doc_id}.html"
    try:
        _s3_client().head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except Exception:
        return False


def _parse_s3_event(body: str) -> list[tuple[str, str]]:
    """SQS 메시지 body에서 (account_id, doc_id) 목록 추출.

    S3 이벤트 알림 포맷:
    {
      "Records": [{
        "s3": {
          "bucket": {"name": "dndn-reports"},
          "object": {"key": "default/reports/doc-123.json"}
        }
      }]
    }
    """
    results = []
    try:
        msg = json.loads(body)
        # SNS 래핑된 경우
        if "Message" in msg:
            msg = json.loads(msg["Message"])
        for record in msg.get("Records", []):
            key = urllib.parse.unquote_plus(record.get("s3", {}).get("object", {}).get("key", ""))
            # 형식: {account_id}/reports/{doc_id}.json
            parts = key.split("/")
            if len(parts) < 3:
                continue
            if parts[1] != "reports":
                continue
            filename = parts[-1]
            if not filename.endswith(".json"):
                continue
            account_id = parts[0]
            doc_id = filename[:-5]
            if doc_id:
                results.append((account_id, doc_id))
    except Exception as e:
        logger.warning("S3 이벤트 파싱 실패: %s", e)
    return results


def _process(account_id: str, doc_id: str):
    if _html_exists(doc_id, account_id):
        logger.info("스킵 (HTML 이미 존재): %s", doc_id)
        return

    logger.info("HTML 생성 시작: %s (account: %s)", doc_id, account_id)
    canonical = get_report(doc_id, account_id)

    meta_type = canonical.get("meta", {}).get("type", "EVENT").upper()
    if meta_type == "WEEKLY":
        html = generate_weekly_report("", "", canonical)
    elif meta_type == "HEALTH":
        html = generate_health_event_report("", "", canonical)
    else:
        html = generate_event_report("", "", canonical)

    save_report_html(doc_id, html, account_id)
    logger.info("HTML 저장 완료: %s", doc_id)


def run():
    if not SQS_QUEUE_URL:
        raise RuntimeError("SQS_QUEUE_URL 환경변수가 설정되지 않았습니다.")

    sqs = _sqs_client()
    logger.info("SQS Worker 시작 — queue: %s", SQS_QUEUE_URL)

    while True:
        resp = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,   # long polling
            VisibilityTimeout=300,
        )
        messages = resp.get("Messages", [])
        if not messages:
            time.sleep(POLL_INTERVAL)
            continue

        for msg in messages:
            receipt = msg["ReceiptHandle"]
            try:
                records = _parse_s3_event(msg["Body"])
                for account_id, doc_id in records:
                    try:
                        _process(account_id, doc_id)
                    except Exception as e:
                        logger.error("문서 처리 실패 (%s): %s", doc_id, e, exc_info=True)
                        # 개별 문서 실패는 메시지 삭제 (재처리 없음)
                sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt)
            except Exception as e:
                logger.error("메시지 처리 실패: %s", e, exc_info=True)
                # 삭제 안 하면 visibility timeout 후 재처리


if __name__ == "__main__":
    run()
