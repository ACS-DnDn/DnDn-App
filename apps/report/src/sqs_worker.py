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
import re
import time
import logging
import urllib.parse

import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

from .ai_generator import (
    generate_event_report,
    generate_weekly_report,
    generate_health_event_report,
)
from datetime import datetime, timezone
from sqlalchemy import func as sa_func

from .s3_client import save_report, save_report_html, _client as _s3_client, S3_BUCKET
from .database import SessionLocal, Base, engine
from .models import Document, Attachment

# 테이블 자동 생성 (독립 실행 시에도 Attachment 테이블 보장)
Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
DNDN_API_URL = os.getenv("DNDN_API_URL", "http://dndn-api.dndn-api.svc.cluster.local:8000")


DOC_TYPE_CODE = {
    "계획서": "PLN",
    "이벤트보고서": "EVT",
    "헬스이벤트보고서": "RPT",
    "주간보고서": "RPT",
}

_TITLE_RE = re.compile(r'<div\s+class="doc-header-title">\s*(.+?)\s*</div>', re.DOTALL)


def _extract_title_from_html(html: str, fallback: str) -> str:
    """생성된 HTML에서 doc-header-title 텍스트를 추출."""
    m = _TITLE_RE.search(html)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title:
            return title
    return fallback


def _next_doc_num(db, doc_type: str) -> str:
    """연도-종류-일련번호 형식의 문서번호 채번 (예: 2026-EVT-0001)."""
    from sqlalchemy import cast, Integer

    code = DOC_TYPE_CODE.get(doc_type, "DOC")
    year = datetime.now(timezone.utc).year
    prefix = f"{year}-{code}-"

    suffix_expr = sa_func.substr(Document.doc_num, len(prefix) + 1)
    max_seq = (
        db.query(sa_func.max(cast(suffix_expr, Integer)))
        .filter(Document.doc_num.like(f"{prefix}%"))
        .scalar()
    )
    seq = (max_seq or 0) + 1
    return f"{prefix}{seq:04d}"


def _sqs_client():
    return boto3.client("sqs", region_name=REGION)


# raw 디렉토리 → 첨부파일 표시명 매핑
_EVIDENCE_DIR_LABELS = {
    "cloudtrail": "CloudTrail_이벤트로그",
    "advisor": "TrustedAdvisor_점검결과",
    "access-analyzer": "AccessAnalyzer_분석결과",
    "cost-explorer": "CostExplorer_비용데이터",
    "cloudwatch": "CloudWatch_메트릭",
    "config": "Config_리소스데이터",
}


def _register_weekly_evidence(db, doc_id: str, canonical: dict, json_key: str, canonical_size_kb: int):
    """활동보고서의 Worker raw evidence 파일들을 첨부파일로 등록."""
    # 1) 정제된 canonical 데이터
    db.add(Attachment(
        id=f"{doc_id}-canonical",
        document_id=doc_id,
        original_name="활동보고_정제데이터.json",
        file_path=json_key,
        size_kb=canonical_size_kb,
    ))

    # 2) raw evidence 파일들 (Worker가 S3에 업로드한 수집 데이터)
    raw_prefix_uri = (
        canonical.get("meta", {}).get("evidence", {}).get("raw_prefix_s3_uri", "")
    )
    if not raw_prefix_uri:
        return

    # s3://bucket/prefix/raw/ → bucket, key_prefix
    stripped = raw_prefix_uri.replace("s3://", "")
    slash_idx = stripped.find("/")
    if slash_idx < 0:
        return
    bucket = stripped[:slash_idx]
    key_prefix = stripped[slash_idx + 1:]

    try:
        attachments = []
        paginator = _s3_client().get_paginator("list_objects_v2")
        idx = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                size_kb = max(1, obj["Size"] // 1024)
                filename = key.split("/")[-1]

                # raw/ 이후 첫 디렉토리로 카테고리 판별
                relative = key[len(key_prefix):]
                category = relative.split("/")[0] if "/" in relative else ""

                if category == "meta":
                    continue  # job_payload 등 메타데이터는 스킵

                label = _EVIDENCE_DIR_LABELS.get(category, category)
                display_name = f"{label}_{filename}" if label else filename

                attachments.append(Attachment(
                    id=f"{doc_id}-evidence-{idx}",
                    document_id=doc_id,
                    original_name=display_name,
                    file_path=key,
                    size_kb=size_kb,
                ))
                idx += 1
        db.add_all(attachments)
    except Exception as e:
        logger.warning("활동보고서 evidence 파일 목록 조회 실패: %s", e)
        raise


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


def _get_company_logo(db, workspace_id: str) -> str:
    """workspace → owner → company → logo_url 조회"""
    try:
        from sqlalchemy import text
        row = db.execute(
            text(
                "SELECT c.logo_url FROM workspaces w "
                "JOIN users u ON w.owner_id = u.id "
                "JOIN companies c ON u.company_id = c.id "
                "WHERE w.id = :ws_id LIMIT 1"
            ),
            {"ws_id": workspace_id},
        ).fetchone()
        return (row[0] or "") if row else ""
    except Exception:
        return ""


def _process(workspace_id: str, event_type: str, s3_key: str):
    doc_id = _doc_id_from_key(s3_key)

    if _html_exists(doc_id, workspace_id):
        logger.info("스킵 (HTML 이미 존재): %s", doc_id)
        return

    logger.info("HTML 생성 시작: %s (workspace: %s, type: %s)", doc_id, workspace_id, event_type)

    # S3에서 canonical JSON 직접 읽기
    canonical = _read_canonical_from_s3(s3_key)

    # canonical JSON을 reports/ 경로에도 저장 (API에서 조회용)
    json_key = save_report(doc_id, canonical, workspace_id)

    # DB에 Document 레코드 생성 전 문서번호 채번 (HTML 생성에 필요)
    doc_type = {
        "findings": "이벤트보고서",
        "health": "헬스이벤트보고서",
        "weekly": "주간보고서",
    }.get(event_type, "이벤트보고서")

    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.id == doc_id).first()
        if existing:
            logger.info("스킵 (Document 이미 존재): %s", doc_id)
            db.close()
            return
        doc_num = _next_doc_num(db, doc_type)
        logo_url = _get_company_logo(db, workspace_id)
    finally:
        db.close()

    doc_meta = {
        "doc_num": doc_num,
        "author_label": "DnDn Agent",
        "company_logo_url": logo_url,
    }

    # meta.type 기반으로 HTML 생성
    meta_type = canonical.get("meta", {}).get("type", "EVENT").upper()
    if meta_type == "WEEKLY":
        html = generate_weekly_report(canonical, doc_meta=doc_meta)
    elif meta_type == "HEALTH":
        html = generate_health_event_report(canonical, doc_meta=doc_meta)
    else:
        html = generate_event_report(canonical, doc_meta=doc_meta)

    # HTML 저장 → {workspace_id}/reports/{doc_id}.html
    html_key = save_report_html(doc_id, html, workspace_id)

    # HTML에서 제목 추출
    title = _extract_title_from_html(html, doc_id)

    created = False
    db = SessionLocal()
    try:
        doc = Document(
            id=doc_id,
            doc_num=doc_num,
            title=title,
            type=doc_type,
            html_key=html_key,
            json_key=json_key,
            workspace_id=workspace_id,
            status="done",
        )
        db.add(doc)

        # 근거자료 첨부 (indent=2로 저장되므로 동일 옵션으로 크기 계산)
        canonical_json_bytes = json.dumps(canonical, ensure_ascii=False, indent=2).encode("utf-8")
        canonical_size_kb = max(1, len(canonical_json_bytes) // 1024)

        if event_type == "weekly":
            # 활동보고서: Worker가 수집한 raw evidence 파일들 등록
            _register_weekly_evidence(db, doc_id, canonical, json_key, canonical_size_kb)
        else:
            # 이벤트/헬스 보고서: 원본 + 정제 데이터
            raw_name_map = {
                "findings": "SecurityHub_Finding_원본.json",
                "health": "AWS_Health_Event_원본.json",
            }
            raw_name = raw_name_map.get(event_type, "원본_이벤트데이터.json")
            try:
                raw_size_bytes = _s3_client().head_object(Bucket=S3_BUCKET, Key=s3_key)["ContentLength"]
                raw_size_kb = max(1, raw_size_bytes // 1024)
            except Exception:
                raw_size_kb = canonical_size_kb
            db.add(Attachment(
                id=f"{doc_id}-raw",
                document_id=doc_id,
                original_name=raw_name,
                file_path=s3_key,
                size_kb=raw_size_kb,
            ))
            db.add(Attachment(
                id=f"{doc_id}-canonical",
                document_id=doc_id,
                original_name="보고서_정제데이터.json",
                file_path=json_key,
                size_kb=canonical_size_kb,
            ))

        db.commit()
        created = True
    except Exception as e:
        logger.error("Document DB 저장 실패 (%s): %s", doc_id, e, exc_info=True)
        db.rollback()
    finally:
        db.close()

    # dndn-api에 새 문서 알림 요청 (Slack) — 새 Document 생성 시에만
    if created:
        try:
            notify_resp = requests.post(
                f"{DNDN_API_URL}/internal/notify-new-document",
                json={
                    "documentId": doc_id,
                    "workspaceId": workspace_id,
                    "title": title,
                    "docType": doc_type,
                },
                headers={"X-Internal-Key": os.getenv("INTERNAL_API_KEY", "")},
                timeout=5,
            )
            payload = notify_resp.json()
            if not notify_resp.ok or not payload.get("ok"):
                logger.warning("Slack 알림 요청 실패 (HTTP %s): %s", notify_resp.status_code, payload)
        except (requests.RequestException, ValueError) as e:
            logger.warning("Slack 알림 요청 실패: %s", e)

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
