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
class SummarySettings(BaseModel):
    repeatEnabled: bool
    intervalHours: int
    lastRun: Optional[str] = None  # ISO 8601


class ReportSettingsResponse(BaseModel):
    summary: SummarySettings
    schedules: List[ScheduleItem]
    eventSettings: Dict[str, bool]


# --- 2. 현황 보고서 설정 저장 (PATCH /report-settings/summary) ---
class SummaryUpdateRequest(BaseModel):
    repeatEnabled: bool
    intervalHours: int


class SummaryUpdateResponse(BaseModel):
    repeatEnabled: bool
    intervalHours: int


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
