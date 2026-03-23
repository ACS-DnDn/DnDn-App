# apps/api/routers/report_settings.py

import json
import os
import re
import uuid

import boto3
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Workspace, ReportSettings
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.report_settings import (
    EventSettingsRequest,
    EventSettingsResponse,
    ReportSettingsResponse,
    ScheduleCreateRequest,
    ScheduleCreateResponse,
    ScheduleItem,
)

router = APIRouter(prefix="/report-settings", tags=["ReportSettings"])

# --- EventBridge Scheduler 설정 (환경변수) ---
_SCHEDULER_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_SCHEDULER_GROUP = os.environ.get("SCHEDULER_GROUP_NAME", "dndn-schedules")
_SCHEDULER_ROLE_ARN = os.environ.get("SCHEDULER_ROLE_ARN", "")
_SCHEDULER_TARGET_ARN = os.environ.get("SCHEDULER_TARGET_ARN", "")


def _scheduler_client():
    return boto3.client("scheduler", region_name=_SCHEDULER_REGION)


def _check_scheduler_config() -> None:
    """필수 환경변수 미설정 시 503."""
    if not _SCHEDULER_ROLE_ARN or not _SCHEDULER_TARGET_ARN:
        raise HTTPException(status_code=503, detail="SCHEDULER_NOT_CONFIGURED")


def _schedule_name(workspace_id: str, schedule_id: str) -> str:
    """EventBridge Scheduler 이름: dndn-{workspaceId}-{scheduleId}"""
    return f"dndn-{workspace_id}-{schedule_id}"


def _kst_to_cron(
    preset: str,
    day_of_week: int | None,
    day_of_month: int | None,
    time_kst: str,
) -> str:
    """KST HH:mm + preset → EventBridge Scheduler cron expression (Asia/Seoul 기준)"""
    hh, mm = map(int, time_kst.split(":"))

    if preset == "daily":
        return f"cron({mm} {hh} * * ? *)"

    if preset == "weekly":
        # 입력: 1=월 ~ 7=일 / AWS cron: SUN=1, MON=2, ..., SAT=7
        aws_map = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 1}
        aws_dow = aws_map[day_of_week]
        return f"cron({mm} {hh} ? * {aws_dow} *)"

    # monthly
    return f"cron({mm} {hh} {day_of_month} * ? *)"


# ---------------------------------------------------------
# 헬퍼: 워크스페이스 확인
# ---------------------------------------------------------
def _get_workspace(db: Session, workspace_id: str, current_user: User) -> Workspace:
    """워크스페이스 존재 여부 확인 (404) + 소유자 권한 확인 (403)."""
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")
    if ws.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return ws


def _get_or_create_settings(db: Session, workspace_id: str) -> ReportSettings:
    """보고서 설정을 조회하고, 없으면 기본값으로 생성."""
    settings = db.query(ReportSettings).filter(
        ReportSettings.workspace_id == workspace_id
    ).first()
    if settings:
        return settings

    settings = ReportSettings(
        workspace_id=workspace_id,
        repeat_enabled=False,
        interval_hours=168,
        event_settings={},
    )
    db.add(settings)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        settings = db.query(ReportSettings).filter(
            ReportSettings.workspace_id == workspace_id
        ).first()
        if not settings:
            raise
    else:
        db.refresh(settings)
    return settings


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_schedule(req: ScheduleCreateRequest) -> None:
    """preset별 필드 범위 및 time 형식 검증 (400)."""
    if req.preset not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="BAD_REQUEST")

    if not _TIME_RE.match(req.time):
        raise HTTPException(status_code=400, detail="BAD_REQUEST")

    if req.preset == "daily":
        if req.dayOfWeek is not None or req.dayOfMonth is not None:
            raise HTTPException(status_code=400, detail="BAD_REQUEST")
    elif req.preset == "weekly":
        if req.dayOfWeek is None or not (1 <= req.dayOfWeek <= 7):
            raise HTTPException(status_code=400, detail="BAD_REQUEST")
        if req.dayOfMonth is not None:
            raise HTTPException(status_code=400, detail="BAD_REQUEST")
    elif req.preset == "monthly":
        if req.dayOfMonth is None or not (1 <= req.dayOfMonth <= 31):
            raise HTTPException(status_code=400, detail="BAD_REQUEST")
        if req.dayOfWeek is not None:
            raise HTTPException(status_code=400, detail="BAD_REQUEST")


# ---------------------------------------------------------
# 1. 전체 설정 조회 (GET /report-settings?workspaceId=xxx)
# ---------------------------------------------------------
@router.get("", response_model=SuccessResponse[ReportSettingsResponse])
def get_report_settings(
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    현황 보고서 · 스케줄 목록 · 이벤트 설정을 한 번에 반환한다.
    페이지 최초 진입 시 자동 호출.
    """
    _get_workspace(db, workspaceId, current_user)
    settings = _get_or_create_settings(db, workspaceId)

    # EventBridge Scheduler에서 이 워크스페이스의 스케줄 목록 조회
    schedule_items: list[ScheduleItem] = []
    try:
        client = _scheduler_client()
        paginator = client.get_paginator("list_schedules")
        pages = paginator.paginate(
            GroupName=_SCHEDULER_GROUP,
            NamePrefix=f"dndn-{workspaceId}-",
        )
        for page in pages:
            for item in page.get("Schedules", []):
                detail = client.get_schedule(
                    GroupName=_SCHEDULER_GROUP,
                    Name=item["Name"],
                )
                payload = json.loads(detail.get("Target", {}).get("Input", "{}"))
                schedule_items.append(
                    ScheduleItem(
                        id=payload.get("scheduleId", ""),
                        title=payload.get("title", ""),
                        preset=payload.get("preset", ""),
                        dayOfWeek=payload.get("dayOfWeek"),
                        dayOfMonth=payload.get("dayOfMonth"),
                        time=payload.get("time", ""),
                        includeRange=payload.get("includeRange", True),
                    )
                )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise HTTPException(status_code=500, detail="SCHEDULER_ERROR")

    return SuccessResponse(
        data=ReportSettingsResponse(
            schedules=schedule_items,
            eventSettings=settings.event_settings or {},
        )
    )


# ---------------------------------------------------------
# 2. 스케줄 추가 (POST /report-settings/schedules)
# ---------------------------------------------------------
@router.post(
    "/schedules",
    response_model=SuccessResponse[ScheduleCreateResponse],
    status_code=201,
)
def create_schedule(
    req: ScheduleCreateRequest,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    새로운 보고서 생성 스케줄을 EventBridge Scheduler에 추가한다.
    """
    _get_workspace(db, workspaceId, current_user)
    _check_scheduler_config()
    _validate_schedule(req)

    schedule_id = uuid.uuid4().hex[:8]  # 8자리 hex ID
    name = _schedule_name(workspaceId, schedule_id)
    cron_expr = _kst_to_cron(req.preset, req.dayOfWeek, req.dayOfMonth, req.time)

    payload = json.dumps({
        "workspaceId": workspaceId,
        "scheduleId": schedule_id,
        "title": req.title,
        "preset": req.preset,
        "dayOfWeek": req.dayOfWeek,
        "dayOfMonth": req.dayOfMonth,
        "time": req.time,
        "includeRange": req.includeRange,
    })

    try:
        _scheduler_client().create_schedule(
            GroupName=_SCHEDULER_GROUP,
            Name=name,
            ScheduleExpression=cron_expr,
            ScheduleExpressionTimezone="Asia/Seoul",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": _SCHEDULER_TARGET_ARN,
                "RoleArn": _SCHEDULER_ROLE_ARN,
                "Input": payload,
            },
            State="ENABLED",
        )
    except (ClientError, ParamValidationError):
        raise HTTPException(status_code=500, detail="SCHEDULER_ERROR")

    return SuccessResponse(data=ScheduleCreateResponse(id=schedule_id))


# ---------------------------------------------------------
# 3. 스케줄 수정 (PATCH /report-settings/schedules/{id})
# ---------------------------------------------------------
@router.patch("/schedules/{schedule_id}", response_model=SuccessResponse[ScheduleCreateResponse])
def update_schedule(
    schedule_id: str,
    req: ScheduleCreateRequest,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    기존 스케줄을 수정한다.
    """
    _get_workspace(db, workspaceId, current_user)
    _check_scheduler_config()
    _validate_schedule(req)

    name = _schedule_name(workspaceId, schedule_id)
    cron_expr = _kst_to_cron(req.preset, req.dayOfWeek, req.dayOfMonth, req.time)

    payload = json.dumps({
        "workspaceId": workspaceId,
        "scheduleId": schedule_id,
        "title": req.title,
        "preset": req.preset,
        "dayOfWeek": req.dayOfWeek,
        "dayOfMonth": req.dayOfMonth,
        "time": req.time,
        "includeRange": req.includeRange,
    })

    try:
        _scheduler_client().update_schedule(
            GroupName=_SCHEDULER_GROUP,
            Name=name,
            ScheduleExpression=cron_expr,
            ScheduleExpressionTimezone="Asia/Seoul",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": _SCHEDULER_TARGET_ARN,
                "RoleArn": _SCHEDULER_ROLE_ARN,
                "Input": payload,
            },
            State="ENABLED",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise HTTPException(status_code=404, detail="SCHEDULE_NOT_FOUND")
        raise HTTPException(status_code=500, detail="SCHEDULER_ERROR")
    except ParamValidationError:
        raise HTTPException(status_code=500, detail="SCHEDULER_ERROR")

    return SuccessResponse(data=ScheduleCreateResponse(id=schedule_id))


# ---------------------------------------------------------
# 4. 스케줄 삭제 (DELETE /report-settings/schedules/{id})
# ---------------------------------------------------------
@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: str,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    스케줄을 삭제한다. 응답 본문 없음 (204).
    """
    _get_workspace(db, workspaceId, current_user)

    name = _schedule_name(workspaceId, schedule_id)
    try:
        _scheduler_client().delete_schedule(
            GroupName=_SCHEDULER_GROUP,
            Name=name,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise HTTPException(status_code=404, detail="SCHEDULE_NOT_FOUND")
        raise HTTPException(status_code=500, detail="SCHEDULER_ERROR")

    return Response(status_code=204)


# ---------------------------------------------------------
# 5. 이벤트 설정 저장 (PATCH /report-settings/events)
# ---------------------------------------------------------
@router.patch("/events", response_model=SuccessResponse[EventSettingsResponse])
def update_event_settings(
    req: EventSettingsRequest,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    이벤트 보고서 유형별 ON/OFF 설정을 저장한다.
    변경된 항목만 포함해도 기존 설정과 병합된다.
    """
    _get_workspace(db, workspaceId, current_user)
    settings = _get_or_create_settings(db, workspaceId)

    # 기존 설정과 병합 (새 dict 할당으로 SQLAlchemy 변경 감지 보장)
    merged = {**(settings.event_settings or {}), **req.settings}
    settings.event_settings = merged

    db.commit()
    db.refresh(settings)

    return SuccessResponse(
        data=EventSettingsResponse(eventSettings=settings.event_settings or {})
    )
