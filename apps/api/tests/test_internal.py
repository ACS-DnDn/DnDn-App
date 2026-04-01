"""내부 서비스 통신 API 단위 테스트 — /internal/notify-new-document

외부 노출이 없는 내부 전용 엔드포인트:
- X-Internal-Key 헤더 인증 검증
- 워크스페이스/오너 조회 로직
- Slack 알림 조건 분기 (토글 OFF, 미연동, 정상 전송)
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.api.src.models import User, Workspace

_SLACK = "apps.api.src.routers.internal"
_VALID_KEY = "test-internal-secret"
_HEADERS = {"X-Internal-Key": _VALID_KEY}


# ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────


def _workspace(db, owner: User) -> Workspace:
    ws = Workspace(
        id=str(uuid.uuid4()),
        alias="테스트WS",
        acct_id="123456789012",
        github_org="test-org",
        repo="test-repo",
        branch="main",
        owner_id=owner.id,
    )
    db.add(ws)
    db.flush()
    return ws


def _slack_user(db, company_id: int) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email="slack@test.com",
        name="슬랙유저",
        role="member",
        company_id=company_id,
        slack_access_token="xoxp-token",
        slack_channel="C12345",
        slack_user_id="U12345",
        slack_notify=True,
    )
    db.add(u)
    db.flush()
    return u


def _payload(ws_id: str) -> dict:
    return {
        "documentId": str(uuid.uuid4()),
        "workspaceId": ws_id,
        "title": "테스트 보고서",
        "docType": "주간보고서",
    }


# ── X-Internal-Key 인증 ───────────────────────────────────────────────────────


class TestInternalKeyAuth:
    def test_missing_key_returns_403(self, client_member, db, company, member_user):
        ws = _workspace(db, member_user)
        res = client_member.post("/internal/notify-new-document", json=_payload(ws.id))
        assert res.status_code == 403

    def test_wrong_key_returns_403(self, client_member, db, company, member_user):
        ws = _workspace(db, member_user)
        res = client_member.post(
            "/internal/notify-new-document",
            json=_payload(ws.id),
            headers={"X-Internal-Key": "wrong-key"},
        )
        assert res.status_code == 403

    def test_correct_key_passes_auth(self, client_member, db, company, member_user):
        """올바른 키면 인증을 통과하고 비즈니스 로직으로 진입한다."""
        ws = _workspace(db, member_user)
        with patch(f"{_SLACK}._INTERNAL_KEY", _VALID_KEY):
            res = client_member.post(
                "/internal/notify-new-document",
                json=_payload(ws.id),
                headers=_HEADERS,
            )
        # 인증 통과 → 비즈니스 로직 실행 (200 또는 Slack 관련 응답)
        assert res.status_code == 200


# ── 워크스페이스/오너 조회 ────────────────────────────────────────────────────


class TestNotifyNewDocument:
    def _post(self, client, ws_id: str) -> dict:
        with patch(f"{_SLACK}._INTERNAL_KEY", _VALID_KEY):
            res = client.post(
                "/internal/notify-new-document",
                json=_payload(ws_id),
                headers=_HEADERS,
            )
        assert res.status_code == 200
        return res.json()

    def test_workspace_not_found(self, client_member):
        """존재하지 않는 워크스페이스 → ok=False, WORKSPACE_NOT_FOUND."""
        data = self._post(client_member, "nonexistent-ws-id")
        assert data["ok"] is False
        assert data["reason"] == "WORKSPACE_NOT_FOUND"

    def test_owner_not_found(self, client_member, db):
        """오너가 없는 워크스페이스 → ok=False, OWNER_NOT_FOUND."""
        ghost_user_id = str(uuid.uuid4())
        ws = Workspace(
            id=str(uuid.uuid4()),
            alias="고스트WS",
            acct_id="000000000001",
            github_org="org",
            repo="repo",
            branch="main",
            owner_id=ghost_user_id,  # DB에 없는 유저
        )
        db.add(ws)
        db.flush()

        data = self._post(client_member, ws.id)
        assert data["ok"] is False
        assert data["reason"] == "OWNER_NOT_FOUND"

    def test_slack_notify_disabled(self, client_member, db, company):
        """오너의 Slack 알림이 OFF → ok=True, skipped=True."""
        owner = User(
            id=str(uuid.uuid4()),
            email="nonotify@test.com",
            name="알림끔",
            role="member",
            company_id=company.id,
            slack_access_token="xoxp-token",
            slack_channel="C99999",
            slack_notify=False,  # 알림 OFF
        )
        db.add(owner)
        db.flush()
        ws = _workspace(db, owner)

        data = self._post(client_member, ws.id)
        assert data["ok"] is True
        assert data["skipped"] is True
        assert data["reason"] == "NOTIFY_DISABLED"

    def test_slack_not_connected(self, client_member, db, company):
        """Slack 미연동 오너 → ok=True, skipped=True, SLACK_NOT_CONNECTED."""
        owner = User(
            id=str(uuid.uuid4()),
            email="noslack@test.com",
            name="슬랙없음",
            role="member",
            company_id=company.id,
            slack_access_token=None,  # 미연동
            slack_channel=None,
        )
        db.add(owner)
        db.flush()
        ws = _workspace(db, owner)

        data = self._post(client_member, ws.id)
        assert data["ok"] is True
        assert data["skipped"] is True
        assert data["reason"] == "SLACK_NOT_CONNECTED"

    @patch(f"{_SLACK}.join_channel", return_value=None)
    @patch(f"{_SLACK}.send_message", return_value=None)
    def test_slack_notification_sent(self, mock_send, mock_join, client_member, db, company):
        """Slack 연동된 오너에게 정상적으로 알림을 전송한다."""
        owner = _slack_user(db, company.id)
        ws = _workspace(db, owner)

        data = self._post(client_member, ws.id)
        assert data["ok"] is True
        mock_join.assert_called_once_with("xoxp-token", "C12345")
        mock_send.assert_called_once()
        # 메시지에 문서 제목 포함 확인
        sent_text = mock_send.call_args[0][2]
        assert "테스트 보고서" in sent_text

    @patch(f"{_SLACK}.join_channel", return_value=None)
    @patch(f"{_SLACK}.send_message", return_value=None)
    def test_doc_type_label_mapping(self, mock_send, mock_join, client_member, db, company):
        """docType에 따라 표시명이 다르게 매핑된다."""
        owner = _slack_user(db, company.id)
        ws = _workspace(db, owner)

        with patch(f"{_SLACK}._INTERNAL_KEY", _VALID_KEY):
            client_member.post(
                "/internal/notify-new-document",
                json={"documentId": str(uuid.uuid4()), "workspaceId": ws.id,
                      "title": "주간현황", "docType": "주간보고서"},
                headers=_HEADERS,
            )
        sent_text = mock_send.call_args[0][2]
        assert "인프라 현황 보고서" in sent_text

    @patch(f"{_SLACK}.join_channel", return_value=None)
    @patch(f"{_SLACK}.send_message", side_effect=__import__("apps.api.src.security.slack_oauth", fromlist=["SlackError"]).SlackError(500, "SLACK_ERROR", "전송 실패"))
    def test_slack_send_failure_returns_ok_false(self, mock_send, mock_join, client_member, db, company):
        """Slack 전송 실패 시 ok=False, SLACK_SEND_FAILED를 반환하고 예외를 전파하지 않는다."""
        owner = _slack_user(db, company.id)
        ws = _workspace(db, owner)

        data = self._post(client_member, ws.id)
        assert data["ok"] is False
        assert data["reason"] == "SLACK_SEND_FAILED"
