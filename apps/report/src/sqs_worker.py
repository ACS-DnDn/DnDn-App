"""SQS Worker — S3 canonical 이벤트 알림 수신 → HTML 자동 생성 → S3 저장

실행:
    python -m src.sqs_worker

환경변수:
    SQS_QUEUE_URL   - SQS 큐 URL (필수)
    AWS_REGION      - 리전 (기본: ap-northeast-2)
    S3_BUCKET       - S3 버킷명 (기본: dndn-reports)
    POLL_INTERVAL   - 폴링 대기 없을 때 sleep 초 (기본: 5)

S3 canonical 경로 규칙:
    canonical/{workspace_id}/findings/{YYYY/MM/DD}/{id}.json  — SecurityHub Finding
    canonical/{workspace_id}/health/{YYYY/MM/DD}/{id}.json    — AWS Health Event
    canonical/{workspace_id}/weekly/{job_id}.json             — 주간 보고서 (Worker)
"""

import json
import os
import time
import logging
import urllib.parse

import boto3
from dotenv import load_dotenv

load_dotenv()

from .ai_generator import (
    generate_event_report,
    generate_weekly_report,
    generate_health_event_report,
)
from .s3_client import save_report, save_report_html, _client as _s3_client, S3_BUCKET
from .database import SessionLocal
from .models import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))


def _sqs_client():
    return boto3.client("sqs", region_name=REGION)


def _html_exists(doc_id: str, workspace_id: str) -> bool:
    """이미 HTML이 S3에 존재하면 스킵"""
    key = f"{workspace_id}/reports/{doc_id}.html"
    try:
        _s3_client().head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except Exception:
        return False


def _parse_s3_event(body: str) -> list[tuple[str, str, str]]:
    """SQS 메시지 body에서 (workspace_id, event_type, s3_key) 목록 추출.

    S3 이벤트 알림 포맷:
    {
      "Records": [{
        "s3": {
          "bucket": {"name": "dndn-prod-s3"},
          "object": {"key": "canonical/{workspace_id}/{type}/{YYYY/MM/DD}/{id}.json"}
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
            key = urllib.parse.unquote_plus(
                record.get("s3", {}).get("object", {}).get("key", "")
            )
            if not key.endswith(".json"):
                continue
            # 형식: canonical/{workspace_id}/{type}/{YYYY}/{MM}/{DD}/{id}.json
            parts = key.split("/")
            if len(parts) < 3 or parts[0] != "canonical":
                logger.warning("canonical prefix 아님, 스킵: %s", key)
                continue
            workspace_id = parts[1]
            event_type = parts[2] if len(parts) > 2 else "unknown"
            results.append((workspace_id, event_type, key))
    except Exception as e:
        logger.warning("S3 이벤트 파싱 실패: %s", e)
    return results


def _read_canonical_from_s3(s3_key: str) -> dict:
    """S3 key에서 직접 canonical JSON 읽기"""
    resp = _s3_client().get_object(Bucket=S3_BUCKET, Key=s3_key)
    return json.loads(resp["Body"].read())


def _doc_id_from_key(s3_key: str) -> str:
    """S3 key에서 doc_id 추출 (파일명에서 .json 제거)"""
    filename = s3_key.split("/")[-1]
    return filename[:-5] if filename.endswith(".json") else filename


def _process(workspace_id: str, event_type: str, s3_key: str):
    doc_id = _doc_id_from_key(s3_key)

    if _html_exists(doc_id, workspace_id):
        logger.info("스킵 (HTML 이미 존재): %s", doc_id)
        return

    logger.info("HTML 생성 시작: %s (workspace: %s, type: %s)", doc_id, workspace_id, event_type)

    # S3에서 canonical JSON 직접 읽기
    canonical = _read_canonical_from_s3(s3_key)

    # canonical JSON을 reports/ 경로에도 저장 (API에서 조회용)
    save_report(doc_id, canonical, workspace_id)

    # meta.type 기반으로 HTML 생성
    meta_type = canonical.get("meta", {}).get("type", "EVENT").upper()
    if meta_type == "WEEKLY":
        html = generate_weekly_report(canonical)
    elif meta_type == "HEALTH":
        html = generate_health_event_report(canonical)
    else:
        html = generate_event_report(canonical)

    # HTML 저장 → {workspace_id}/reports/{doc_id}.html
    html_key = save_report_html(doc_id, html, workspace_id)

    # DB에 Document 레코드 생성
    doc_type = {
        "findings": "이벤트보고서",
        "health": "헬스이벤트보고서",
        "weekly": "주간보고서",
    }.get(event_type, "이벤트보고서")

    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.id == doc_id).first()
        if not existing:
            title = canonical.get("meta", {}).get("title", doc_id)
            doc = Document(
                id=doc_id,
                title=title,
                type=doc_type,
                html_key=html_key,
                json_key=f"{workspace_id}/reports/{doc_id}.json",
                workspace_id=workspace_id,
                status="done",
            )
            db.add(doc)
            db.commit()
    except Exception as e:
        logger.error("Document DB 저장 실패 (%s): %s", doc_id, e, exc_info=True)
        db.rollback()
    finally:
        db.close()

    logger.info("HTML 저장 완료: %s → %s", doc_id, html_key)


def run():
    if not SQS_QUEUE_URL:
        raise RuntimeError("SQS_QUEUE_URL 환경변수가 설정되지 않았습니다.")

    sqs = _sqs_client()
    logger.info("SQS Worker 시작 — queue: %s", SQS_QUEUE_URL)

    while True:
        resp = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,  # long polling
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
                for workspace_id, event_type, s3_key in records:
                    try:
                        _process(workspace_id, event_type, s3_key)
                    except Exception as e:
                        logger.error(
                            "문서 처리 실패 (%s): %s", s3_key, e, exc_info=True
                        )
                sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt)
            except Exception as e:
                logger.error("메시지 처리 실패: %s", e, exc_info=True)
                # 삭제 안 하면 visibility timeout 후 재처리


if __name__ == "__main__":
    run()
