# apps/api/routers/reports.py

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Workspace
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.report_settings import (
    SummaryCreateRequest,
    SummaryCreateResponse,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


# ---------------------------------------------------------
# 현황 보고서 즉시 생성 (POST /reports/summary)
# ---------------------------------------------------------
@router.post(
    "/summary",
    response_model=SuccessResponse[SummaryCreateResponse],
    status_code=202,
)
async def create_summary_report(
    req: SummaryCreateRequest,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    현황 보고서를 즉시 생성 요청한다.
    Worker가 비동기로 수집·생성하며, runId로 진행 상태를 조회할 수 있다.
    """
    # 1. 워크스페이스 존재 여부 확인 (404)
    ws = db.query(Workspace).filter(Workspace.id == workspaceId).first()
    if not ws:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    # 2. 소유자 권한 확인 (403)
    if ws.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # 3. 필수값 검증 (400) — startDate/endDate는 Pydantic datetime으로 자동 검증
    if not req.title or not req.title.strip():
        raise HTTPException(status_code=400, detail="BAD_REQUEST")

    # 4. TODO: Worker 큐에 보고서 생성 작업 전달
    #    현재는 stub — reportId와 runId만 반환
    run_id = str(uuid.uuid4())

    return SuccessResponse(
        data=SummaryCreateResponse(
            reportId=0,  # Worker 연동 후 실제 ID로 교체
            runId=run_id,
        )
    )
