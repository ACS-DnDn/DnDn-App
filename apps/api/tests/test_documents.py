"""결재/반려/읽음 처리 단위 테스트 — /api/documents

S3·GitHub·Slack 등 외부 의존이 없는 순수 DB 로직만 대상으로 한다.
- POST /{id}/approve  : 결재 상태 전이 (wait→current→approved→done)
- POST /{id}/reject   : 반려 상태 전이
- PATCH /read         : 특정 문서 읽음 처리
- PATCH /read-all     : 탭 기준 전체 읽음 처리
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from apps.api.src.models import Approval, Document, DocumentRead, User, Workspace

_DOC_ROUTER = "apps.api.src.routers.documents"


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _doc(db, author: User, *, status: str = "progress", title: str = "테스트문서") -> Document:
    d = Document(
        id=str(uuid.uuid4()),
        title=title,
        type="계획서",
        status=status,
        author_id=author.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(d)
    db.flush()
    return d


def _approval(db, doc: Document, user: User, *, seq: int, status: str = "wait") -> Approval:
    a = Approval(document_id=doc.id, user_id=user.id, seq=seq, type="결재", status=status)
    db.add(a)
    db.flush()
    return a


# ── POST /api/documents/{id}/approve ──────────────────────────────────────────


class TestApproveDocument:
    @patch(f"{_DOC_ROUTER}._notify", return_value=None)
    @patch(f"{_DOC_ROUTER}._create_terraform_pr_if_needed", return_value=None)
    def test_approve_advances_to_next_approver(self, _pr, _notify, client_member, db, company, member_user):
        """내 결재 승인 후 다음 결재자 상태가 current로 바뀐다."""
        second = User(id=str(uuid.uuid4()), email="second@test.com", name="2차결재자", role="member", company_id=company.id)
        db.add(second)
        db.flush()

        doc = _doc(db, member_user)
        apv1 = _approval(db, doc, member_user, seq=1, status="current")
        apv2 = _approval(db, doc, second, seq=2, status="wait")

        res = client_member.post(f"/api/documents/{doc.id}/approve", json={"comment": "승인합니다"})
        assert res.status_code == 200
        assert res.json()["data"]["newStatus"] == "progress"

        db.refresh(apv1)
        db.refresh(apv2)
        assert apv1.status == "approved"
        assert apv2.status == "current"

    @patch(f"{_DOC_ROUTER}._notify", return_value=None)
    @patch(f"{_DOC_ROUTER}._create_terraform_pr_if_needed", return_value=None)
    def test_final_approve_sets_doc_done(self, _pr, _notify, client_member, db, member_user):
        """마지막 결재자 승인 시 문서 상태가 done이 된다."""
        doc = _doc(db, member_user)
        _approval(db, doc, member_user, seq=1, status="current")

        res = client_member.post(f"/api/documents/{doc.id}/approve", json={})
        assert res.status_code == 200
        assert res.json()["data"]["newStatus"] == "done"

        db.refresh(doc)
        assert doc.status == "done"

    @patch(f"{_DOC_ROUTER}._notify", return_value=None)
    @patch(f"{_DOC_ROUTER}._create_terraform_pr_if_needed", return_value=None)
    def test_approve_saves_comment_and_date(self, _pr, _notify, client_member, db, member_user):
        """승인 시 코멘트와 approval_date가 기록된다."""
        doc = _doc(db, member_user)
        apv = _approval(db, doc, member_user, seq=1, status="current")

        client_member.post(f"/api/documents/{doc.id}/approve", json={"comment": "좋아요"})

        db.refresh(apv)
        assert apv.comment == "좋아요"
        assert apv.approval_date is not None

    def test_approve_nonexistent_doc_returns_404(self, client_member):
        res = client_member.post("/api/documents/nonexistent/approve", json={})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "DOC_NOT_FOUND"

    def test_approve_not_my_turn_returns_403(self, client_member, db, company, member_user):
        """결재 차례가 아니면 403 NOT_YOUR_TURN."""
        other = User(id=str(uuid.uuid4()), email="other@test.com", name="타인", role="member", company_id=company.id)
        db.add(other)
        db.flush()
        doc = _doc(db, other)
        _approval(db, doc, other, seq=1, status="current")  # 다른 사람 차례

        res = client_member.post(f"/api/documents/{doc.id}/approve", json={})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "NOT_YOUR_TURN"

    def test_approve_when_status_is_wait_returns_403(self, client_member, db, company, member_user):
        """내 결재 상태가 wait이면 403 (아직 내 차례 아님)."""
        other = User(id=str(uuid.uuid4()), email="first@test.com", name="1차결재자", role="member", company_id=company.id)
        db.add(other)
        db.flush()
        doc = _doc(db, member_user)
        _approval(db, doc, other, seq=1, status="current")
        _approval(db, doc, member_user, seq=2, status="wait")

        res = client_member.post(f"/api/documents/{doc.id}/approve", json={})
        assert res.status_code == 403

    @patch(f"{_DOC_ROUTER}._notify", return_value=None)
    @patch(f"{_DOC_ROUTER}._create_terraform_pr_if_needed", return_value=None)
    def test_approve_skips_ref_type_approvals(self, _pr, _notify, client_member, db, company, member_user):
        """'참조' 타입 결재는 결재 흐름에서 제외된다."""
        ref_user = User(id=str(uuid.uuid4()), email="ref@test.com", name="참조자", role="member", company_id=company.id)
        db.add(ref_user)
        db.flush()
        doc = _doc(db, member_user)
        _approval(db, doc, member_user, seq=1, status="current")
        # 참조자는 결재 흐름에 포함되지 않음
        ref_apv = Approval(document_id=doc.id, user_id=ref_user.id, seq=2, type="참조", status="noted")
        db.add(ref_apv)
        db.flush()

        res = client_member.post(f"/api/documents/{doc.id}/approve", json={})
        assert res.status_code == 200
        # 참조자를 건너뛰고 최종 완료
        assert res.json()["data"]["newStatus"] == "done"


# ── POST /api/documents/{id}/reject ───────────────────────────────────────────


class TestRejectDocument:
    @patch(f"{_DOC_ROUTER}._notify", return_value=None)
    def test_reject_sets_doc_status_rejected(self, _notify, client_member, db, member_user):
        """반려 시 문서 상태가 rejected가 된다."""
        doc = _doc(db, member_user)
        _approval(db, doc, member_user, seq=1, status="current")

        res = client_member.post(f"/api/documents/{doc.id}/reject", json={"comment": "수정 필요"})
        assert res.status_code == 200
        assert res.json()["data"]["newStatus"] == "rejected"

        db.refresh(doc)
        assert doc.status == "rejected"

    @patch(f"{_DOC_ROUTER}._notify", return_value=None)
    def test_reject_saves_reason_and_date(self, _notify, client_member, db, member_user):
        """반려 시 사유와 approval_date가 기록된다."""
        doc = _doc(db, member_user)
        apv = _approval(db, doc, member_user, seq=1, status="current")

        client_member.post(f"/api/documents/{doc.id}/reject", json={"comment": "내용 부족"})

        db.refresh(apv)
        assert apv.status == "rejected"
        assert apv.comment == "내용 부족"
        assert apv.approval_date is not None

    def test_reject_without_comment_returns_400(self, client_member, db, member_user):
        """반려 사유 없이 요청 시 400 MISSING_COMMENT."""
        doc = _doc(db, member_user)
        _approval(db, doc, member_user, seq=1, status="current")

        res = client_member.post(f"/api/documents/{doc.id}/reject", json={"comment": "   "})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "MISSING_COMMENT"

    def test_reject_nonexistent_doc_returns_404(self, client_member):
        res = client_member.post("/api/documents/nonexistent/reject", json={"comment": "반려"})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "DOC_NOT_FOUND"

    def test_reject_not_my_turn_returns_403(self, client_member, db, company, member_user):
        """내 차례가 아니면 403 NOT_YOUR_TURN."""
        other = User(id=str(uuid.uuid4()), email="other2@test.com", name="타인", role="member", company_id=company.id)
        db.add(other)
        db.flush()
        doc = _doc(db, other)
        _approval(db, doc, other, seq=1, status="current")

        res = client_member.post(f"/api/documents/{doc.id}/reject", json={"comment": "반려"})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "NOT_YOUR_TURN"


# ── PATCH /api/documents/read ─────────────────────────────────────────────────


class TestMarkDocumentsAsRead:
    def test_mark_single_document_as_read(self, client_member, db, member_user):
        """단일 문서를 읽음 처리한다."""
        doc = _doc(db, member_user)

        res = client_member.patch("/api/documents/read", json={"ids": [doc.id]})
        assert res.status_code == 200
        assert res.json()["data"]["success"] is True

        read_count = db.query(DocumentRead).filter(
            DocumentRead.user_id == member_user.id,
            DocumentRead.document_id == doc.id,
        ).count()
        assert read_count == 1

    def test_mark_multiple_documents_as_read(self, client_member, db, member_user):
        """여러 문서를 한 번에 읽음 처리한다."""
        docs = [_doc(db, member_user, title=f"문서{i}") for i in range(3)]
        ids = [d.id for d in docs]

        res = client_member.patch("/api/documents/read", json={"ids": ids})
        assert res.status_code == 200

        count = db.query(DocumentRead).filter(DocumentRead.user_id == member_user.id).count()
        assert count == 3

    def test_mark_already_read_is_idempotent(self, client_member, db, member_user):
        """이미 읽은 문서를 다시 읽음 처리해도 중복 삽입되지 않는다."""
        doc = _doc(db, member_user)
        db.add(DocumentRead(user_id=member_user.id, document_id=doc.id))
        db.flush()

        res = client_member.patch("/api/documents/read", json={"ids": [doc.id]})
        assert res.status_code == 200

        count = db.query(DocumentRead).filter(
            DocumentRead.user_id == member_user.id,
            DocumentRead.document_id == doc.id,
        ).count()
        assert count == 1  # 중복 없음

    def test_mark_empty_list_returns_success(self, client_member):
        """빈 목록 요청은 에러 없이 성공한다."""
        res = client_member.patch("/api/documents/read", json={"ids": []})
        assert res.status_code == 200
        assert res.json()["data"]["success"] is True

    def test_mark_nonexistent_document_returns_400(self, client_member):
        """존재하지 않는 문서 ID는 400 INVALID_IDS."""
        res = client_member.patch("/api/documents/read", json={"ids": ["nonexistent-id"]})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_IDS"


# ── PATCH /api/documents/read-all ────────────────────────────────────────────


class TestMarkAllDocumentsAsRead:
    def test_read_all_tab_marks_current_approvals(self, client_member, db, company, member_user):
        """action 탭: 내가 결재할 차례인 문서가 읽음 처리된다."""
        doc = _doc(db, member_user)
        _approval(db, doc, member_user, seq=1, status="current")

        res = client_member.patch("/api/documents/read-all", json={"tab": "action"})
        assert res.status_code == 200
        assert res.json()["data"]["success"] is True

        count = db.query(DocumentRead).filter(DocumentRead.user_id == member_user.id).count()
        assert count == 1

    def test_read_all_tab_marks_rejected_docs(self, client_member, db, member_user):
        """action 탭: 내가 쓴 반려 문서가 읽음 처리된다."""
        doc = _doc(db, member_user, status="rejected")

        res = client_member.patch("/api/documents/read-all", json={"tab": "action"})
        assert res.status_code == 200

        count = db.query(DocumentRead).filter(
            DocumentRead.user_id == member_user.id,
            DocumentRead.document_id == doc.id,
        ).count()
        assert count == 1

    def test_read_all_is_idempotent(self, client_member, db, member_user):
        """이미 읽은 문서가 있어도 중복 삽입되지 않는다."""
        doc = _doc(db, member_user, status="rejected")
        db.add(DocumentRead(user_id=member_user.id, document_id=doc.id))
        db.flush()

        res = client_member.patch("/api/documents/read-all", json={"tab": "action"})
        assert res.status_code == 200

        count = db.query(DocumentRead).filter(DocumentRead.user_id == member_user.id).count()
        assert count == 1

    def test_read_all_invalid_tab_returns_400(self, client_member):
        """잘못된 탭 이름은 400 INVALID_TAB."""
        res = client_member.patch("/api/documents/read-all", json={"tab": "invalid_tab"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_TAB"

    def test_read_all_empty_result_returns_success(self, client_member):
        """해당하는 문서가 없어도 성공한다."""
        res = client_member.patch("/api/documents/read-all", json={"tab": "action"})
        assert res.status_code == 200
        assert res.json()["data"]["success"] is True
