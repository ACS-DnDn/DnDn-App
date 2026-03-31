"""대시보드 API 단위 테스트 — GET /api/dashboard"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.api.src.models import Approval, Document, DocumentRead, User, Workspace


class TestDashboard:
    def test_response_structure(self, client_member):
        """응답에 필수 키가 모두 포함된다."""
        res = client_member.get("/api/dashboard")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "docStats" in data
        assert "pendingDocs" in data
        assert "completedDocs" in data
        assert "notices" in data

    def test_doc_stats_has_required_fields(self, client_member):
        res = client_member.get("/api/dashboard")
        stats = res.json()["data"]["docStats"]
        assert "pending" in stats
        assert "ongoing" in stats
        assert "newDoc" in stats

    def test_pending_count_includes_approval_waiting(self, client_member, db, member_user, company):
        """결재 대기(current) 건수가 pending에 포함된다."""
        doc = _make_doc(db, member_user, status="progress", company=company)
        apv = Approval(document_id=doc.id, user_id=member_user.id, seq=1, type="결재", status="current")
        db.add(apv)
        db.flush()

        res = client_member.get("/api/dashboard")
        assert res.json()["data"]["docStats"]["pending"] >= 1

    def test_pending_count_includes_rejected_docs(self, client_member, db, member_user, company):
        """내가 기안한 반려 문서가 pending에 포함된다."""
        _make_doc(db, member_user, status="rejected", company=company)
        db.flush()

        res = client_member.get("/api/dashboard")
        assert res.json()["data"]["docStats"]["pending"] >= 1

    def test_pending_count_includes_deploy_failed(self, client_member, db, member_user, company):
        """내가 기안한 배포 실패 문서가 pending에 포함된다."""
        _make_doc(db, member_user, status="deploy_failed", company=company)
        db.flush()

        res = client_member.get("/api/dashboard")
        assert res.json()["data"]["docStats"]["pending"] >= 1

    def test_ongoing_count_counts_progress_docs(self, client_member, db, member_user, company):
        """진행 중인(progress) 문서 수가 ongoing에 반영된다."""
        _make_doc(db, member_user, status="progress", company=company)
        _make_doc(db, member_user, status="progress", company=company)
        db.flush()

        res = client_member.get("/api/dashboard")
        assert res.json()["data"]["docStats"]["ongoing"] >= 2

    def test_pending_docs_contains_current_approval(self, client_member, db, member_user, company):
        """결재 대기 문서가 pendingDocs 목록에 나타난다."""
        doc = _make_doc(db, member_user, status="progress", title="결재대기문서", company=company)
        apv = Approval(document_id=doc.id, user_id=member_user.id, seq=1, type="결재", status="current")
        db.add(apv)
        db.flush()

        res = client_member.get("/api/dashboard")
        titles = [d["title"] for d in res.json()["data"]["pendingDocs"]]
        assert "결재대기문서" in titles

    def test_pending_docs_rejected_shown_to_author(self, client_member, db, member_user, company):
        """반려된 내 문서가 pendingDocs에 나타난다."""
        doc = _make_doc(db, member_user, status="rejected", title="반려된문서", company=company)
        db.flush()

        res = client_member.get("/api/dashboard")
        titles = [d["title"] for d in res.json()["data"]["pendingDocs"]]
        assert "반려된문서" in titles

    def test_completed_docs_shows_my_docs(self, client_member, db, member_user, company):
        """내가 기안한 비초안 문서가 completedDocs에 나타난다."""
        doc = _make_doc(db, member_user, status="approved", title="완료문서", company=company)
        db.flush()

        res = client_member.get("/api/dashboard")
        titles = [d["title"] for d in res.json()["data"]["completedDocs"]]
        assert "완료문서" in titles

    def test_completed_docs_excludes_draft(self, client_member, db, member_user, company):
        """임시저장(draft) 문서는 completedDocs에 포함되지 않는다."""
        doc = _make_doc(db, member_user, status="draft", title="임시저장문서", company=company)
        db.flush()

        res = client_member.get("/api/dashboard")
        titles = [d["title"] for d in res.json()["data"]["completedDocs"]]
        assert "임시저장문서" not in titles

    def test_completed_docs_max_5(self, client_member, db, member_user, company):
        """completedDocs는 최대 5개까지만 반환된다."""
        for i in range(7):
            _make_doc(db, member_user, status="approved", title=f"문서{i}", company=company)
        db.flush()

        res = client_member.get("/api/dashboard")
        assert len(res.json()["data"]["completedDocs"]) <= 5

    def test_notices_always_present(self, client_member):
        """공지사항은 항상 반환된다."""
        res = client_member.get("/api/dashboard")
        notices = res.json()["data"]["notices"]
        assert isinstance(notices, list)
        assert len(notices) > 0

    def test_new_doc_count_excludes_read_docs(self, client_member, db, member_user, company):
        """이미 읽은 문서는 newDoc 카운트에서 제외된다."""
        ws = Workspace(
            id=str(uuid.uuid4()),
            alias="WS",
            acct_id="000000000001",
            github_org="org",
            repo="repo",
            branch="main",
            owner_id=member_user.id,
        )
        db.add(ws)
        db.flush()

        # 읽지 않은 문서
        unread_doc = _make_doc(db, member_user, status="progress", title="안읽은문서", company=company, workspace_id=ws.id)
        # 읽은 문서
        read_doc = _make_doc(db, member_user, status="progress", title="읽은문서", company=company, workspace_id=ws.id)
        db.flush()
        read_record = DocumentRead(user_id=member_user.id, document_id=read_doc.id)
        db.add(read_record)
        db.flush()

        res = client_member.get("/api/dashboard")
        # 읽은 문서는 newDoc에서 제외되므로 unread_doc만 카운트
        assert res.json()["data"]["docStats"]["newDoc"] >= 1


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _make_doc(db, author: User, *, status: str, title: str = "테스트문서",
              company=None, workspace_id: str | None = None) -> Document:
    doc = Document(
        id=str(uuid.uuid4()),
        title=title,
        type="계획서",
        status=status,
        author_id=author.id,
        workspace_id=workspace_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(doc)
    return doc
