"""
Slack OAuth 연동 서비스 모듈.

Slack OAuth 2.0 플로우와 메시지 전송 기능을 제공한다.
FastAPI·DB 의존 없음 — 라우터에서 import하여 사용.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

import requests

# ── 환경 변수 ──────────────────────────────────────────────
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")
SLACK_REDIRECT_URI = os.getenv(
    "SLACK_REDIRECT_URI", "http://localhost:5173/auth/slack/callback"
)

_SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
_SLACK_API = "https://slack.com/api"

# OAuth 스코프: 채널 메시지 전송 + 사용자 DM
_SCOPES = "chat:write,channels:read"
_USER_SCOPES = "identity.basic,identity.team"


# ── 응답 데이터 클래스 ────────────────────────────────────
@dataclass
class AuthUrlResult:
    authorize_url: str
    state: str


@dataclass
class CallbackResult:
    connected: bool
    workspace: str
    slack_user_id: str
    access_token: str  # 서버에서만 보관, 프론트에 노출 X


# ── 에러 ──────────────────────────────────────────────────
class SlackError(Exception):
    """Slack API 호출 에러."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _slack_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 1. OAuth 인증 URL 생성 ────────────────────────────────
def get_auth_url() -> AuthUrlResult:
    """Slack OAuth 인증 페이지 URL과 CSRF state 반환."""
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": SLACK_CLIENT_ID,
        "scope": _SCOPES,
        "user_scope": _USER_SCOPES,
        "redirect_uri": SLACK_REDIRECT_URI,
        "state": state,
    }
    url = requests.Request("GET", _SLACK_AUTHORIZE_URL, params=params).prepare().url
    return AuthUrlResult(authorize_url=url or "", state=state)


# ── 2. OAuth 콜백 (code → access_token) ───────────────────
def exchange_code(code: str) -> CallbackResult:
    """Slack 인증 코드를 access token으로 교환."""
    try:
        resp = requests.post(
            _SLACK_TOKEN_URL,
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": SLACK_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        raise SlackError(502, "BAD_GATEWAY", "Slack 서버에 연결할 수 없습니다.") from e

    if not resp.ok:
        raise SlackError(resp.status_code, "SLACK_HTTP_ERROR", f"Slack 토큰 요청 실패: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        raise SlackError(502, "BAD_GATEWAY", "Slack 토큰 응답을 파싱할 수 없습니다.")

    if not data.get("ok"):
        raise SlackError(400, "SLACK_OAUTH_ERROR", data.get("error", "Unknown Slack error"))

    access_token = data.get("access_token", "")
    workspace = data.get("team", {}).get("name", "")
    slack_user_id = data.get("authed_user", {}).get("id", "")

    return CallbackResult(
        connected=True,
        workspace=workspace,
        slack_user_id=slack_user_id,
        access_token=access_token,
    )


# ── 3. 메시지 전송 ────────────────────────────────────────
def send_message(token: str, channel: str, text: str) -> None:
    """Slack 채널에 메시지 전송."""
    try:
        resp = requests.post(
            f"{_SLACK_API}/chat.postMessage",
            json={"channel": channel, "text": text},
            headers=_slack_headers(token),
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        raise SlackError(502, "SLACK_SEND_ERROR", "Slack 서버에 연결할 수 없습니다.") from e

    if not resp.ok:
        raise SlackError(resp.status_code, "SLACK_SEND_ERROR", f"메시지 전송 실패: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        raise SlackError(502, "SLACK_SEND_ERROR", "Slack 응답을 파싱할 수 없습니다.")

    if not data.get("ok"):
        raise SlackError(502, "SLACK_SEND_ERROR", data.get("error", "메시지 전송 실패"))
