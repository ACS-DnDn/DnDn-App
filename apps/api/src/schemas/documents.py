# app/schemas/documents.py

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from datetime import date


# --- 결재자 정보 ---
class ApproverItem(BaseModel):
    userId: str
    seq: int
    type: str  # 결재 / 협조 / 참조


# --- 문서 저장/상신 요청 ---
class DocumentSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    documentId: str
    workspaceId: str
    work_date: Optional[date] = Field(None, alias="workDate")
    terraform: Optional[Dict[str, Any]] = None
    refDocIds: List[str] = Field(default_factory=list)
    approvers: List[ApproverItem]
    isDraft: bool


# --- 문서 저장/상신 응답 ---
class DocumentSubmitResponse(BaseModel):
    id: str
    docNum: str
    status: str


# --- 문서 보관함 목록 조회용 ---
class DocumentArchiveItem(BaseModel):
    id: str  # 명세는 number지만 UUID이므로 str
    docNum: str
    name: str
    author: str
    date: str
    type: str
    status: str
    action: Optional[str] = None
    isRead: bool  # TODO: 향후 읽음 테이블 연동 필요


class DocumentArchiveResponse(BaseModel):
    total: int
    page: int
    pageSize: int
    items: List[DocumentArchiveItem]


class DocumentApproveRequest(BaseModel):
    comment: Optional[str] = None


class DocumentStatusResponse(BaseModel):
    newStatus: str


class DocumentRejectRequest(BaseModel):
    comment: str


class DocumentReadRequest(BaseModel):
    ids: List[str]  # 💡 UUID를 받기 위해 str 배열로 설정합니다.


class DocumentReadResponse(BaseModel):
    success: bool


class DocumentReadAllRequest(BaseModel):
    tab: str


class RefDocMetaItem(BaseModel):
    label: str
    value: str


class RefDocumentDetailResponse(BaseModel):
    id: str
    title: str
    meta: List[RefDocMetaItem]
    content: str
