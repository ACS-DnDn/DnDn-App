from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from apps.api.src.database import get_db
from apps.api.src.models import User, Document, Approval, DocumentRead
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
    pending_count = (
        db.query(Approval)
        .filter(Approval.user_id == current_user.id, Approval.status == "current")
        .count()
    )
    ongoing_count = (
        db.query(Document)
        .filter(Document.author_id == current_user.id, Document.status == "progress")
        .count()
    )
    read_doc_ids = (
        db.query(DocumentRead.document_id)
        .filter(DocumentRead.user_id == current_user.id)
    )
    new_doc_count = (
        db.query(Document)
        .filter(Document.id.notin_(read_doc_ids))
        .count()
    )

    # 3. 결재 대기 문서 (Pending Docs)
    pending_approvals = (
        db.query(Approval)
        .filter(Approval.user_id == current_user.id, Approval.status == "current")
        .all()
    )
    pending_docs = []
    for app in pending_approvals:
        doc = app.document
        doc_status_for_me = "rejected" if doc.status == "rejected" else "waiting"
        pending_docs.append(
            {
                "id": str(doc.id),
                "docNum": str(doc.id)[:8],
                "title": doc.title,
                "status": doc_status_for_me,
                "type": doc.type if doc.type else "작업 계획서",
                "author": doc.author.name if doc.author else "알수없음",
                "date": doc.created_at.strftime("%Y.%m.%d") if doc.created_at else "",
            }
        )

    # 4. 결재 완료/내 문서 (Completed Docs)
    completed_docs = []
    my_docs = (
        db.query(Document).filter(Document.author_id == current_user.id).limit(5).all()
    )
    for doc in my_docs:
        completed_docs.append(
            {
                "id": str(doc.id),
                "docNum": str(doc.id)[:8],
                "title": doc.title,
                "type": doc.type if doc.type else "작업 계획서",
                "author": current_user.name,
                "date": doc.created_at.strftime("%Y.%m.%d") if doc.created_at else "",
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
