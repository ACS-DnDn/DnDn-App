# apps/api/schemas/report_settings.py

from pydantic import BaseModel
from typing import Dict, List, Optional


# --- 스케줄 항목 (공통) ---
class ScheduleItem(BaseModel):
    id: int
    title: str
    preset: str  # daily / weekly / monthly
    dayOfWeek: Optional[int] = None  # 1=월 ~ 7=일 (weekly 시)
    dayOfMonth: Optional[int] = None  # 1-31 (monthly 시)
    time: str  # HH:mm
    includeRange: bool


# --- 1. 전체 설정 조회 (GET /report-settings) ---
class ReportSettingsResponse(BaseModel):
    schedules: List[ScheduleItem]
    eventSettings: Dict[str, bool]


# --- 2. 현황 보고서 즉시 생성 (POST /reports/summary) ---
class SummaryCreateRequest(BaseModel):
    title: str  # 보고서 제목 (프론트에서 자동 생성)
    startDate: str  # 수집 시작 일시 (ISO 8601)
    endDate: str  # 수집 종료 일시 (ISO 8601)


class SummaryCreateResponse(BaseModel):
    reportId: int  # 생성된 보고서 ID
    runId: str  # Worker 실행 ID (상태 조회용)


# --- 3/4. 스케줄 추가/수정 (POST·PATCH /report-settings/schedules) ---
class ScheduleCreateRequest(BaseModel):
    title: str
    preset: str  # daily / weekly / monthly
    dayOfWeek: Optional[int] = None
    dayOfMonth: Optional[int] = None
    time: str  # HH:mm
    includeRange: bool


class ScheduleCreateResponse(BaseModel):
    id: int  # 생성된 스케줄 ID


# --- 6. 이벤트 설정 저장 (PATCH /report-settings/events) ---
class EventSettingsRequest(BaseModel):
    settings: Dict[str, bool]  # {"sh-malicious-network": true, ...}


class EventSettingsResponse(BaseModel):
    eventSettings: Dict[str, bool]
