# apps/api/schemas/workspaces.py

from pydantic import BaseModel
from typing import List, Literal, Optional, Any


# --- 워크스페이스 목록 조회 (GET /workspaces) ---
class WorkspaceListItem(BaseModel):
    id: str
    alias: str
    acctId: str
    owner: str
    githubOrg: str
    repo: str
    path: Optional[str] = None
    branch: str
    icon: str
    memo: Optional[str] = None


class WorkspaceListResponse(BaseModel):
    items: List[WorkspaceListItem]


# --- 워크스페이스 수정 (PATCH /workspaces/{id}) ---
class WorkspaceUpdateRequest(BaseModel):
    alias: str
    icon: str
    memo: Optional[str] = None


class WorkspaceUpdateResponse(BaseModel):
    id: str
    alias: str
    icon: str
    memo: Optional[str] = None


# --- OPA 정책 (GET/PUT /workspaces/{id}/opa-settings) ---
class OpaPolicyParam(BaseModel):
    key: str
    label: str
    on: bool
    severity: Literal["block", "warn"]
    params: Optional[Any] = None
    exceptions: List[str] = []


class OpaCategoryItem(BaseModel):
    category: str
    items: List[OpaPolicyParam]


class OpaSettingsResponse(BaseModel):
    policies: List[OpaCategoryItem]


class OpaSettingsRequest(BaseModel):
    policies: List[OpaCategoryItem]


class OpaSettingsSavedResponse(BaseModel):
    savedAt: str


# --- 워크스페이스 생성 (POST /workspaces) ---
class WorkspaceCreateRequest(BaseModel):
    alias: str  # 별칭
    acctId: str  # AWS 계정 ID (12자리)
    githubOrg: str  # GitHub 조직명
    repo: str  # 레포지토리명
    path: Optional[str] = None  # 레포 내 경로 (선택)
    branch: str  # 브랜치명
    icon: str  # 아이콘 키
    memo: Optional[str] = None  # 메모 (선택)


class WorkspaceCreateResponse(BaseModel):
    id: str  # 생성된 워크스페이스 ID
    alias: str  # 별칭
    acctId: str  # AWS 계정 ID
    createdAt: str  # 생성 일시
