"""HR 관리 전용 스키마."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


# ── 공통 ──────────────────────────────────────────────────

class UserSummary(BaseModel):
    id: str
    employeeNo: str | None
    name: str
    position: str | None
    role: str  # hr | leader | member

    class Config:
        from_attributes = True


# ── 사원 ──────────────────────────────────────────────────

class HrUserResponse(BaseModel):
    id: str
    employeeNo: str | None
    name: str
    email: str
    position: str | None
    role: str
    departmentId: str | None
    departmentName: str | None

    class Config:
        from_attributes = True


class HrUserCreateRequest(BaseModel):
    email: EmailStr
    name: str
    employeeNo: str | None = None
    position: str | None = None
    departmentId: str | None = None
    role: str = "member"          # hr | leader | member


class HrUserUpdateRequest(BaseModel):
    name: str | None = None
    employeeNo: str | None = None
    position: str | None = None
    departmentId: str | None = None
    role: str | None = None       # 역할 변경 시 Cognito 그룹도 변경



# ── 부서 ──────────────────────────────────────────────────

class DepartmentNode(BaseModel):
    id: str
    name: str
    parentId: str | None
    leaderId: str | None
    leaderName: str | None

    class Config:
        from_attributes = True


class DepartmentCreateRequest(BaseModel):
    name: str
    parentId: str | None = None


class DepartmentSetLeaderRequest(BaseModel):
    leaderId: str | None  # None이면 부서장 해제
