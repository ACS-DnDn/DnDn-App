# apps/api/routers/workspaces.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from apps.api.src.database import get_db
from apps.api.src.models import User, Workspace
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.workspaces import (
    WorkspaceListItem,
    WorkspaceListResponse,
    WorkspaceCreateRequest,
    WorkspaceCreateResponse,
    WorkspaceUpdateRequest,
    WorkspaceUpdateResponse,
    OpaSettingsResponse,
    OpaSettingsRequest,
    OpaSettingsSavedResponse,
)
from apps.api.src.schemas.aws import AwsTestRequest, AwsTestResponse
from apps.api.src.security.aws_sts import (
    test_assume_role,
    StsValidationError,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# ---------------------------------------------------------
# 1. 워크스페이스 목록 조회 (GET /workspaces)
# ---------------------------------------------------------
@router.get("", response_model=SuccessResponse[WorkspaceListResponse])
async def get_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    현재 사용자가 접근 가능한 워크스페이스 목록을 조회한다.
    같은 부서의 부서장이 생성한 워크스페이스가 반환된다.
    """
    # 💡 현재는 전체 워크스페이스를 반환합니다.
    # 추후 부서 기반 필터링이 필요하면 여기서 조건을 추가하세요.
    workspaces = db.query(Workspace).order_by(Workspace.created_at.desc()).all()

    items = []
    for ws in workspaces:
        # 생성자(owner) 이름 조회
        owner_name = ws.owner.name if ws.owner else "알수없음"

        items.append(
            WorkspaceListItem(
                id=str(ws.id),
                alias=ws.alias,
                acctId=ws.acct_id,
                owner=owner_name,
                githubOrg=ws.github_org,
                repo=ws.repo,
                path=ws.path,
                branch=ws.branch,
                icon=ws.icon,
                memo=ws.memo,
            )
        )

    return SuccessResponse(data=WorkspaceListResponse(items=items))


# ---------------------------------------------------------
# 2. 워크스페이스 수정 (PATCH /workspaces/{id})
# ---------------------------------------------------------
@router.patch("/{workspace_id}", response_model=SuccessResponse[WorkspaceUpdateResponse])
async def update_workspace(
    workspace_id: str,
    req: WorkspaceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    편집 모달에서 별칭, 메모, 아이콘을 수정한다.
    AWS/GitHub 연동 정보는 수정 불가.
    """
    # 1. 워크스페이스 존재 여부 확인 (404)
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    # 2. 소유자 권한 확인 (403)
    if ws.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # 3. 별칭 필수값 검증 (400)
    if not req.alias or not req.alias.strip():
        raise HTTPException(status_code=400, detail="MISSING_ALIAS")

    # 4. 수정 반영
    ws.alias = req.alias
    ws.icon = req.icon
    ws.memo = req.memo

    db.commit()
    db.refresh(ws)

    return SuccessResponse(
        data=WorkspaceUpdateResponse(
            id=str(ws.id),
            alias=ws.alias,
            icon=ws.icon,
            memo=ws.memo,
        )
    )


# ---------------------------------------------------------
# 3. OPA 정책 조회 (GET /workspaces/{id}/opa-settings)
# ---------------------------------------------------------
@router.get(
    "/{workspace_id}/opa-settings",
    response_model=SuccessResponse[OpaSettingsResponse],
)
async def get_opa_settings(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    워크스페이스에 저장된 인프라 정책(OPA) 설정을 반환한다.
    인프라 정책 탭 진입 시 자동 호출.
    """
    # 1. 워크스페이스 존재 여부 확인 (404)
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    # 2. 소유자 권한 확인 (403)
    if ws.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # 3. OPA 설정이 없으면 빈 배열 반환
    policies = ws.opa_settings if ws.opa_settings else []

    return SuccessResponse(data=OpaSettingsResponse(policies=policies))


# ---------------------------------------------------------
# 4. OPA 정책 저장 (PUT /workspaces/{id}/opa-settings)
# ---------------------------------------------------------
@router.put(
    "/{workspace_id}/opa-settings",
    response_model=SuccessResponse[OpaSettingsSavedResponse],
)
async def save_opa_settings(
    workspace_id: str,
    req: OpaSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    인프라 정책(OPA) 설정 전체를 교체한다.
    저장 버튼 클릭 시 현재 상태 전체를 전송.
    """
    # 1. 워크스페이스 존재 여부 확인 (404)
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    # 2. 소유자 권한 확인 (403)
    if ws.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # 3. policies 구조 검증 (400)
    if req.policies is None:
        raise HTTPException(status_code=400, detail="MISSING_POLICIES")

    # 4. OPA 설정 전체 교체 (Pydantic → dict 변환하여 JSON 컬럼에 저장)
    ws.opa_settings = [cat.model_dump() for cat in req.policies]

    db.commit()

    return SuccessResponse(
        data=OpaSettingsSavedResponse(
            savedAt=datetime.now(timezone.utc).isoformat(),
        )
    )


# ---------------------------------------------------------
# 5. AWS 연동 테스트 (POST /workspaces/test-aws)
# ---------------------------------------------------------
@router.post("/test-aws", response_model=SuccessResponse[AwsTestResponse])
async def test_aws_connection(
    req: AwsTestRequest,
    current_user: User = Depends(get_current_user),
):
    """
    AWS 계정 ID로 STS AssumeRole을 시도하여 연동 상태를 검증한다.
    Step 1 — 테스트 버튼 클릭 시 호출.
    """
    # 1. 계정 ID 형식 검증 (400)
    try:
        result = test_assume_role(req.acctId)
    except StsValidationError:
        raise HTTPException(status_code=400, detail="BAD_REQUEST") from None

    # 2. 결과 반환 (성공/실패 모두 200)
    return SuccessResponse(
        data=AwsTestResponse(
            success=result.success,
            acctId=result.acct_id,
            roleArn=result.role_arn if result.success else None,
            error=result.error,
        )
    )


# ---------------------------------------------------------
# 6. 워크스페이스 생성 (POST /workspaces)
# ---------------------------------------------------------
@router.post(
    "",
    response_model=SuccessResponse[WorkspaceCreateResponse],
    status_code=201,
)
async def create_workspace(
    req: WorkspaceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    AWS 연동 + GitHub 연동 + 기본 정보를 모두 포함하여 워크스페이스를 생성한다.
    Step 3 — 생성 버튼 클릭 시 호출.
    """
    # 1. 필수값 검증 (400)
    if not req.alias or not req.alias.strip():
        raise HTTPException(status_code=400, detail="BAD_REQUEST")

    # 2. 동일 AWS 계정 ID 중복 검사 (409)
    existing = db.query(Workspace).filter(Workspace.acct_id == req.acctId).first()
    if existing:
        raise HTTPException(status_code=409, detail="CONFLICT")

    # 3. 워크스페이스 생성
    ws = Workspace(
        alias=req.alias,
        acct_id=req.acctId,
        github_org=req.githubOrg,
        repo=req.repo,
        path=req.path,
        branch=req.branch,
        icon=req.icon,
        memo=req.memo,
        owner_id=current_user.id,
    )

    db.add(ws)
    db.commit()
    db.refresh(ws)

    return SuccessResponse(
        data=WorkspaceCreateResponse(
            id=str(ws.id),
            alias=ws.alias,
            acctId=ws.acct_id,
            createdAt=ws.created_at.isoformat(),
        )
    )
