"""Slack 연동 라우터 — /slack"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.slack import SlackStatusResponse, SlackSettingsRequest
from apps.api.src.security.slack_oauth import (
    get_auth_url,
    exchange_code,
    SlackError,
)

router = APIRouter(prefix="/slack", tags=["Slack"])

# ── TTL 설정 ──────────────────────────────────────────────
_STATE_TTL = timedelta(minutes=10)


class _StateEntry(NamedTuple):
    value: str
    expires_at: datetime


_oauth_states: dict[str, set[_StateEntry]] = {}


def _cleanup_expired() -> None:
    for uid in list(_oauth_states):
        _oauth_states[uid] = {s for s in _oauth_states[uid] if s.expires_at > datetime.now(timezone.utc)}
        if not _oauth_states[uid]:
            del _oauth_states[uid]


def _user_status(user: User) -> SlackStatusResponse:
    connected = bool(user.slack_access_token)
    return SlackStatusResponse(
        connected=connected,
        workspace=user.slack_workspace if connected else None,
        channel=user.slack_channel if connected else None,
        notifyEnabled=user.slack_notify if user.slack_notify is not None else True,
    )


# ── GET /slack/auth ────────────────────────────────────────
@router.get("/auth", response_model=SuccessResponse[dict])
async def slack_auth(current_user: User = Depends(get_current_user)):
    """Slack OAuth 인증 플로우를 시작한다. 응답 URL로 사용자를 리다이렉트한다."""
    _cleanup_expired()
    result = get_auth_url()

    if current_user.id not in _oauth_states:
        _oauth_states[current_user.id] = set()
    _oauth_states[current_user.id].add(
        _StateEntry(value=result.state, expires_at=datetime.now(timezone.utc) + _STATE_TTL)
    )

    return SuccessResponse(data={"authorizeUrl": result.authorize_url, "state": result.state})


# ── GET /slack/callback ────────────────────────────────────
@router.get("/callback", response_model=SuccessResponse[SlackStatusResponse])
async def slack_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Slack 인증 완료 후 프론트에서 호출하는 콜백. code를 토큰으로 교환하고 DB에 저장한다."""
    _cleanup_expired()

    user_states = _oauth_states.get(current_user.id, set())
    matched = next((s for s in user_states if s.value == state), None)
    if not matched:
        raise HTTPException(status_code=400, detail="INVALID_OAUTH_STATE")
    user_states.discard(matched)
    if not user_states:
        _oauth_states.pop(current_user.id, None)

    try:
        result = exchange_code(code)
    except SlackError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    current_user.slack_access_token = result.access_token
    current_user.slack_workspace = result.workspace
    current_user.slack_user_id = result.slack_user_id
    if not current_user.slack_channel:
        current_user.slack_channel = "general"
    if current_user.slack_notify is None:
        current_user.slack_notify = True
    db.commit()
    db.refresh(current_user)

    return SuccessResponse(data=_user_status(current_user))


# ── GET /slack/status ──────────────────────────────────────
@router.get("/status", response_model=SuccessResponse[SlackStatusResponse])
async def slack_status(current_user: User = Depends(get_current_user)):
    """현재 Slack 연동 상태 반환."""
    return SuccessResponse(data=_user_status(current_user))


# ── PATCH /slack/settings ──────────────────────────────────
@router.patch("/settings", response_model=SuccessResponse[SlackStatusResponse])
async def slack_update_settings(
    req: SlackSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """알림 채널 및 알림 활성화 여부 업데이트."""
    if not current_user.slack_access_token:
        raise HTTPException(status_code=400, detail="SLACK_NOT_CONNECTED")

    if req.channel is not None:
        current_user.slack_channel = req.channel
    if req.notifyEnabled is not None:
        current_user.slack_notify = req.notifyEnabled
    db.commit()
    db.refresh(current_user)

    return SuccessResponse(data=_user_status(current_user))


# ── DELETE /slack/disconnect ───────────────────────────────
@router.delete("/disconnect", response_model=SuccessResponse[dict])
async def slack_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Slack 연동 해제."""
    current_user.slack_access_token = None
    current_user.slack_workspace = None
    current_user.slack_user_id = None
    current_user.slack_channel = None
    current_user.slack_notify = None
    db.commit()

    return SuccessResponse(data={"message": "Slack 연동이 해제되었습니다."})
