"""내부 서비스 간 통신 전용 엔드포인트.

report-worker / report-api 등 같은 클러스터 내 서비스가 호출한다.
외부 노출 없음 — ALB Ingress path(/api)에 포함되지 않도록 별도 prefix 사용.
"""

import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Workspace
from apps.api.src.security.slack_oauth import send_message, SlackError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["Internal"])

_INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY", "")


def _verify_internal_key(x_internal_key: str | None = Header(None, alias="X-Internal-Key")):
    """내부 서비스 간 호출 인증 — INTERNAL_API_KEY 헤더 검증."""
    if not _INTERNAL_KEY or x_internal_key != _INTERNAL_KEY:
        raise HTTPException(status_code=403, detail="FORBIDDEN")


class NotifyNewDocRequest(BaseModel):
    documentId: str
    workspaceId: str
    title: str
    docType: str


@router.post("/notify-new-document", dependencies=[Depends(_verify_internal_key)])
def notify_new_document(req: NotifyNewDocRequest, db: Session = Depends(get_db)):
    """새 문서 생성 시 workspace owner의 Slack 채널로 알림 전송."""

    ws = db.query(Workspace).filter(Workspace.id == req.workspaceId).first()
    if not ws:
        return {"ok": False, "reason": "WORKSPACE_NOT_FOUND"}

    owner = db.query(User).filter(User.id == ws.owner_id).first()
    if not owner:
        return {"ok": False, "reason": "OWNER_NOT_FOUND"}

    # 알림 토글 OFF이면 스킵 (None은 기본값=활성으로 처리)
    if owner.slack_notify is False:
        return {"ok": True, "skipped": True, "reason": "NOTIFY_DISABLED"}

    # Slack 연동 안 됐으면 스킵
    if not owner.slack_access_token or not owner.slack_channel:
        return {"ok": True, "skipped": True, "reason": "SLACK_NOT_CONNECTED"}

    text = f"\U0001f4c4 새 {req.docType}이 생성되었습니다: {req.title}"

    try:
        send_message(owner.slack_access_token, owner.slack_channel, text)
    except SlackError as e:
        logger.warning("Slack 알림 전송 실패 (owner=%s): %s", owner.id, e.message)
        return {"ok": False, "reason": "SLACK_SEND_FAILED"}

    return {"ok": True}
