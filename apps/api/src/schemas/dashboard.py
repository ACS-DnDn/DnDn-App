from pydantic import BaseModel
from typing import List, Optional


# --- Task (오늘의 업무 추가 응답용) ---
class TaskCreateRequest(BaseModel):
    content: str


class TaskResponse(BaseModel):
    id: str
    content: str
    createdAt: str


# --- Dashboard (대시보드 메인) ---
class DocStats(BaseModel):
    pending: int
    ongoing: int
    newDoc: int


class NoticeItem(BaseModel):
    id: int
    type: str  # notice / update
    title: str
    author: str
    date: str


class DashboardDocItem(BaseModel):
    docNum: str
    title: str
    status: Optional[str] = None  # completedDocs에는 status가 없으므로 옵셔널 처리
    type: str
    author: str
    date: str


class DashboardResponse(BaseModel):
    docStats: DocStats
    notices: List[NoticeItem]
    pendingDocs: List[DashboardDocItem]
    completedDocs: List[DashboardDocItem]
    tasks: List[str]  # 명세서대로 단순 문자열 배열로 처리합니다.
