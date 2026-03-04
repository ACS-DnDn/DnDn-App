# app/schemas/documents.py

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


# 결재자 정보 규격 (재사용을 위해 분리)
class ApproverSchema(BaseModel):
    userId: str
    seq: int = Field(..., description="결재 순서 (1, 2, 3...)")


# 1. AI 계획서 생성 요청 (POST /documents/generate/plan)
class PlanGenerateRequest(BaseModel):
    title: str
    workDate: date
    refDocIds: List[str]
    memo: Optional[str] = None


# 2. 계획서 최종 저장 및 결재 상신 (POST /documents)
class DocumentCreateRequest(BaseModel):
    title: str
    workDate: date
    content: str  # HTML 본문
    terraform: dict  # {"main.tf": "..."}
    refDocIds: List[str]
    approvers: List[ApproverSchema]  # 상세 규격 적용!
    isDraft: bool
