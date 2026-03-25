from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def _to_kst_str(dt: datetime | None) -> str:
    """UTC datetime → KST 'YYYY.MM.DD HH:MM' 문자열"""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y.%m.%d %H:%M")

from apps.api.src.database import get_db
from apps.api.src.models import User, Document, Approval, DocumentRead, Workspace
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.dashboard import DashboardResponse

router = APIRouter(tags=["Dashboard"])


# ---------------------------------------------------------
# 1. 대시보드 데이터 조회 (GET /dashboard)
# ---------------------------------------------------------
@router.get("/dashboard", response_model=SuccessResponse[DashboardResponse])
def get_dashboard(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    # 1. 문서 통계
    approval_pending = (
        db.query(Approval)
        .filter(Approval.user_id == current_user.id, Approval.status == "current")
        .count()
    )
    rejected_pending = (
        db.query(Document)
        .filter(Document.author_id == current_user.id, Document.status == "rejected")
        .count()
    )
    pending_count = approval_pending + rejected_pending
    ongoing_count = (
        db.query(Document)
        .filter(Document.author_id == current_user.id, Document.status == "progress")
        .count()
    )
    # 내 워크스페이스(같은 회사·부서) 문서 중 안 읽은 것만 카운트
    my_ws_ids = (
        db.query(Workspace.id)
        .join(User, Workspace.owner_id == User.id)
        .filter(
            User.company_id == current_user.company_id,
            User.department_id == current_user.department_id,
        )
    )
    read_doc_ids = (
        db.query(DocumentRead.document_id)
        .filter(DocumentRead.user_id == current_user.id)
    )
    new_doc_count = (
        db.query(Document)
        .filter(
            Document.workspace_id.in_(my_ws_ids),
            Document.id.notin_(read_doc_ids),
            Document.status != "draft",
        )
        .count()
    )

    # 3. 결재 대기 문서 (Pending Docs)
    pending_approvals = (
        db.query(Approval)
        .join(Document, Approval.document_id == Document.id)
        .filter(Approval.user_id == current_user.id, Approval.status == "current")
        .order_by(Document.created_at.desc())
        .all()
    )
    pending_docs = []
    for app in pending_approvals:
        doc = app.document
        doc_status_for_me = "rejected" if doc.status == "rejected" else "waiting"
        pending_docs.append(
            {
                "id": str(doc.id),
                "docNum": doc.doc_num or str(doc.id)[:8],
                "title": doc.title,
                "status": doc_status_for_me,
                "type": doc.type if doc.type else "작업 계획서",
                "author": doc.author.name if doc.author else "DnDn Agent",
                "date": _to_kst_str(doc.created_at),
            }
        )

    # 3-1. 반려된 문서 — 기안자에게도 대시보드에 노출
    rejected_docs = (
        db.query(Document)
        .filter(
            Document.author_id == current_user.id,
            Document.status == "rejected",
        )
        .order_by(Document.created_at.desc())
        .all()
    )
    seen_ids = {d["id"] for d in pending_docs}
    for doc in rejected_docs:
        if str(doc.id) not in seen_ids:
            pending_docs.append(
                {
                    "id": str(doc.id),
                    "docNum": doc.doc_num or str(doc.id)[:8],
                    "title": doc.title,
                    "status": "rejected",
                    "type": doc.type if doc.type else "작업 계획서",
                    "author": doc.author.name if doc.author else "DnDn Agent",
                    "date": _to_kst_str(doc.created_at),
                }
            )

    # 4. 결재 완료/내 문서 (Completed Docs)
    completed_docs = []
    my_docs = (
        db.query(Document).filter(
            Document.author_id == current_user.id,
            Document.status != "draft",
        ).order_by(Document.created_at.desc()).limit(5).all()
    )
    for doc in my_docs:
        completed_docs.append(
            {
                "id": str(doc.id),
                "docNum": doc.doc_num or str(doc.id)[:8],
                "title": doc.title,
                "type": doc.type if doc.type else "작업 계획서",
                "author": current_user.name,
                "date": _to_kst_str(doc.created_at),
            }
        )

    # 5. 공지사항 (더미 데이터)
    notices = [
        {
            "id": 1,
            "type": "notice",
            "title": "[공지] 시스템 점검 안내",
            "author": "관리자",
            "date": "2026.03.04",
        },
        {
            "id": 2,
            "type": "update",
            "title": "[업데이트] 신규 기능 배포",
            "author": "운영팀",
            "date": "2026.03.01",
        },
    ]

    dashboard_data = {
        "docStats": {
            "pending": pending_count,
            "ongoing": ongoing_count,
            "newDoc": new_doc_count,
        },
        "notices": notices,
        "pendingDocs": pending_docs,
        "completedDocs": completed_docs,
        "tasks": [],
    }

    return SuccessResponse(data=dashboard_data)
