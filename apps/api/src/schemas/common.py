# apps/api/schemas/common.py
from pydantic import BaseModel
from typing import TypeVar, Generic, Optional

# T는 어떤 타입의 데이터든 들어올 수 있다는 뜻의 제네릭 변수입니다.
T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
