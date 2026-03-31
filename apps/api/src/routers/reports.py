# apps/api/routers/reports.py

import json
import os
import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Header, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Workspace
from apps.api.src.routers.auth import get_current_user
from apps.api.src.routers.workspace_auth import _check_ws_member
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.report_settings import (
    SummaryCreateRequest,
    SummaryCreateResponse,
)

router = APIRouter(prefix="/reports", tags=["Reports"])

_REPORT_QUEUE_URL = os.environ.get("REPORT_REQUEST_QUEUE_URL", "")
_INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY", "")
_AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_S3_BUCKET = os.environ.get("S3_BUCKET", "")
_STS_ROLE_NAME = os.environ.get("STS_ROLE_NAME", "DnDnOpsAgentRole")
_STS_EXTERNAL_ID = os.environ.get("STS_EXTERNAL_ID", "")

# auto_error=False — X-Internal-Key 경로에서 Authorization 없어도 403 대신 None 반환
_security_optional = HTTPBearer(auto_error=False)


async def _get_caller(
    x_internal_key: Optional[str] = Header(default=None, alias="X-Internal-Key"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_security_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    두 가지 인증 경로 지원:
    - X-Internal-Key 헤더: Lambda(VPC 내부) 호출 → None 반환 (사용자 불필요)
    - Authorization Bearer: 일반 사용자 JWT 인증 → User 반환
    """
    if x_internal_key is not None:
        if not _INTERNAL_KEY or x_internal_key != _INTERNAL_KEY:
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        return None  # 내부 호출 신뢰 — 사용자 객체 불필요

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await get_current_user(credentials=credentials, db=db)


# ---------------------------------------------------------
# 현황 보고서 즉시 생성 (POST /reports/summary)
# ---------------------------------------------------------
@router.post(
    "/summary",
    response_model=SuccessResponse[SummaryCreateResponse],
    status_code=202,
)
def create_summary_report(
    req: SummaryCreateRequest,
    workspaceId: str,
    caller: Optional[User] = Depends(_get_caller),
    db: Session = Depends(get_db),
):
    """
    현황 보고서를 즉시 생성 요청한다.
    - 일반 사용자: JWT 인증 + 워크스페이스 소유자 확인
    - 내부 Lambda(스케줄 트리거): X-Internal-Key 인증, 소유자 확인 생략
    Worker가 SQS 메시지를 수신하여 비동기로 보고서를 생성한다.
    """
    # 일반 사용자: 같은 부서 구성원이면 보고서 생성 가능
    # 내부 Lambda: caller=None → 소속 확인 생략
    if caller is not None:
        ws = _check_ws_member(db, workspaceId, caller)
    else:
        ws = db.query(Workspace).filter(Workspace.id == workspaceId).first()
        if not ws:
            raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    if not req.title or not req.title.strip():
        raise HTTPException(status_code=400, detail="BAD_REQUEST")

    if not _REPORT_QUEUE_URL:
        raise HTTPException(status_code=503, detail="QUEUE_NOT_CONFIGURED")

    run_id = str(uuid.uuid4())

    # Worker 스키마(contracts/payload/job_payload.schema.json) 준수 payload 조립
    job_payload = {
        "type": "WEEKLY",
        "run_id": run_id,
        "account_id": ws.acct_id,
        "regions": [_AWS_REGION],
        "assume_role": {
            "role_arn": f"arn:aws:iam::{ws.acct_id}:role/{_STS_ROLE_NAME}",
            "external_id": _STS_EXTERNAL_ID,
        },
        "s3": {
            "bucket": _S3_BUCKET,
            "prefix": f"account_id={ws.acct_id}/type=WEEKLY/run_id={run_id}",
        },
        "time_range": {
            "start": req.startDate.isoformat(),
            "end": req.endDate.isoformat(),
            "timezone": "Asia/Seoul",
        },
        "trigger": {
            "source": "API",
            "title": req.title,
            "workspace_id": workspaceId,
        },
    }

    # SQS에 보고서 생성 작업 전달
    try:
        sqs = boto3.client("sqs", region_name=_AWS_REGION)
        sqs.send_message(
            QueueUrl=_REPORT_QUEUE_URL,
            MessageBody=json.dumps(job_payload),
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail="QUEUE_ERROR") from e

    return SuccessResponse(
        data=SummaryCreateResponse(
            reportId=0,
            runId=run_id,
            workspaceId=workspaceId,
        )
    )


# ---------------------------------------------------------
# 보고서 생성 완료 여부 폴링 (GET /reports/status/{runId})
# ---------------------------------------------------------
@router.get("/status/{runId}")
def check_report_status(
    runId: str,
    workspaceId: str,
    current_user: User = Depends(get_current_user),
):
    """S3에 보고서 HTML이 존재하는지 확인 (프론트 폴링용)"""
    if not _S3_BUCKET:
        raise HTTPException(status_code=503, detail="S3_NOT_CONFIGURED")

    html_key = f"{workspaceId}/reports/{runId}.html"
    try:
        s3 = boto3.client("s3", region_name=_AWS_REGION)
        s3.head_object(Bucket=_S3_BUCKET, Key=html_key)
        return {"success": True, "data": {"ready": True, "runId": runId}}
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return {"success": True, "data": {"ready": False, "runId": runId}}
        raise HTTPException(status_code=500, detail="S3_ERROR") from e
