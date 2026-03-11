# apps/api/routers/report_settings.py

import re

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Workspace, ReportSettings, ReportSchedule
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.report_settings import (
    ScheduleItem,
    SummarySettings,
    ReportSettingsResponse,
    SummaryUpdateRequest,
    SummaryUpdateResponse,
    ScheduleCreateRequest,
    ScheduleCreateResponse,
    EventSettingsRequest,
    EventSettingsResponse,
)

router = APIRouter(prefix="/report-settings", tags=["ReportSettings"])


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
        if req.dayOfWeek is None or not (0 <= req.dayOfWeek <= 6):
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
async def get_report_settings(
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

    # 스케줄 목록 조회
    schedules = db.query(ReportSchedule).filter(
        ReportSchedule.workspace_id == workspaceId
    ).all()

    return SuccessResponse(
        data=ReportSettingsResponse(
            summary=SummarySettings(
                repeatEnabled=settings.repeat_enabled,
                intervalHours=settings.interval_hours,
                lastRun=settings.last_run.isoformat() if settings.last_run else None,
            ),
            schedules=[
                ScheduleItem(
                    id=s.id,
                    title=s.title,
                    preset=s.preset,
                    dayOfWeek=s.day_of_week,
                    dayOfMonth=s.day_of_month,
                    time=s.time,
                    includeRange=s.include_range,
                )
                for s in schedules
            ],
            eventSettings=settings.event_settings or {},
        )
    )


# ---------------------------------------------------------
# 2. 현황 보고서 설정 저장 (PATCH /report-settings/summary)
# ---------------------------------------------------------
@router.patch("/summary", response_model=SuccessResponse[SummaryUpdateResponse])
async def update_summary(
    req: SummaryUpdateRequest,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    현황 보고서 자동 반복 ON/OFF 및 주기를 저장한다.
    """
    _get_workspace(db, workspaceId, current_user)
    settings = _get_or_create_settings(db, workspaceId)

    # intervalHours 유효성 검증
    if req.intervalHours not in (24, 168, 720):
        raise HTTPException(status_code=400, detail="BAD_REQUEST")

    settings.repeat_enabled = req.repeatEnabled
    settings.interval_hours = req.intervalHours

    db.commit()

    return SuccessResponse(
        data=SummaryUpdateResponse(
            repeatEnabled=settings.repeat_enabled,
            intervalHours=settings.interval_hours,
        )
    )


# ---------------------------------------------------------
# 3. 스케줄 추가 (POST /report-settings/schedules)
# ---------------------------------------------------------
@router.post(
    "/schedules",
    response_model=SuccessResponse[ScheduleCreateResponse],
    status_code=201,
)
async def create_schedule(
    req: ScheduleCreateRequest,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    새로운 보고서 생성 스케줄을 추가한다.
    """
    _get_workspace(db, workspaceId, current_user)
    _validate_schedule(req)

    schedule = ReportSchedule(
        workspace_id=workspaceId,
        title=req.title,
        preset=req.preset,
        day_of_week=req.dayOfWeek,
        day_of_month=req.dayOfMonth,
        time=req.time,
        include_range=req.includeRange,
    )

    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    return SuccessResponse(
        data=ScheduleCreateResponse(id=schedule.id)
    )


# ---------------------------------------------------------
# 4. 스케줄 수정 (PATCH /report-settings/schedules/{id})
# ---------------------------------------------------------
@router.patch("/schedules/{schedule_id}", response_model=SuccessResponse[ScheduleCreateResponse])
async def update_schedule(
    schedule_id: int,
    req: ScheduleCreateRequest,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    기존 스케줄을 수정한다.
    """
    _get_workspace(db, workspaceId, current_user)

    schedule = db.query(ReportSchedule).filter(
        ReportSchedule.id == schedule_id,
        ReportSchedule.workspace_id == workspaceId,
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="SCHEDULE_NOT_FOUND")

    _validate_schedule(req)

    schedule.title = req.title
    schedule.preset = req.preset
    schedule.day_of_week = req.dayOfWeek
    schedule.day_of_month = req.dayOfMonth
    schedule.time = req.time
    schedule.include_range = req.includeRange

    db.commit()

    return SuccessResponse(
        data=ScheduleCreateResponse(id=schedule.id)
    )


# ---------------------------------------------------------
# 5. 스케줄 삭제 (DELETE /report-settings/schedules/{id})
# ---------------------------------------------------------
@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int,
    workspaceId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    스케줄을 삭제한다. 응답 본문 없음 (204).
    """
    _get_workspace(db, workspaceId, current_user)

    schedule = db.query(ReportSchedule).filter(
        ReportSchedule.id == schedule_id,
        ReportSchedule.workspace_id == workspaceId,
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="SCHEDULE_NOT_FOUND")

    db.delete(schedule)
    db.commit()

    return Response(status_code=204)


# ---------------------------------------------------------
# 6. 이벤트 설정 저장 (PATCH /report-settings/events)
# ---------------------------------------------------------
@router.patch("/events", response_model=SuccessResponse[EventSettingsResponse])
async def update_event_settings(
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
