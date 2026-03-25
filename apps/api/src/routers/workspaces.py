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
from apps.api.src.schemas.aws import AwsTestRequest, AwsTestResponse, CfnLinkRequest, CfnLinkResponse
from apps.api.src.security.aws_sts import (
    test_assume_role,
    get_cfn_link,
    StsValidationError,
)
from apps.api.src.security.github_oauth import (
    register_webhook,
    GITHUB_WEBHOOK_SECRET,
)

import logging
_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])

# 워크스페이스 생성 시 기본 OPA 인프라 정책
DEFAULT_OPA_SETTINGS = [
    {"category": "네트워크 보안", "items": [
        {"key": "net-sg-open", "label": "보안그룹 전체 개방(0.0.0.0/0) 차단", "on": True, "severity": "block", "params": {"type": "list", "label": "허용 CIDR", "values": ["10.0.0.0/8", "172.16.0.0/12"]}, "exceptions": []},
        {"key": "net-rds-public", "label": "RDS 퍼블릭 접근 차단", "on": True, "severity": "block", "params": None, "exceptions": []},
        {"key": "net-flow-log", "label": "VPC Flow Log 활성화 필수", "on": False, "severity": "warn", "params": None, "exceptions": []},
    ]},
    {"category": "IAM 보안", "items": [
        {"key": "iam-wildcard", "label": "와일드카드(*) 권한 사용 금지", "on": True, "severity": "block", "params": None, "exceptions": []},
        {"key": "iam-admin-attach", "label": "AdministratorAccess 정책 직접 연결 금지", "on": True, "severity": "block", "params": None, "exceptions": []},
        {"key": "iam-boundary", "label": "Permission Boundary 적용 필수", "on": False, "severity": "warn", "params": {"type": "list", "label": "허용 Boundary ARN 패턴", "values": []}, "exceptions": []},
    ]},
    {"category": "스토리지 보안", "items": [
        {"key": "stor-s3-public", "label": "S3 퍼블릭 접근 금지", "on": True, "severity": "block", "params": None, "exceptions": []},
        {"key": "stor-s3-encrypt", "label": "S3 버킷 암호화 필수", "on": True, "severity": "warn", "params": None, "exceptions": []},
        {"key": "stor-rds-encrypt", "label": "RDS 스토리지 암호화 필수", "on": True, "severity": "block", "params": None, "exceptions": []},
        {"key": "stor-ebs-encrypt", "label": "EBS 볼륨 암호화 필수", "on": False, "severity": "warn", "params": None, "exceptions": []},
    ]},
    {"category": "컴퓨팅 제어", "items": [
        {"key": "comp-ec2-public-ip", "label": "EC2 퍼블릭 IP 자동 할당 금지", "on": True, "severity": "block", "params": None, "exceptions": []},
        {"key": "comp-instance", "label": "허용 인스턴스 타입 제한", "on": False, "severity": "warn", "params": {"type": "list", "label": "허용 타입", "values": ["t3.micro", "t3.small", "t3.medium"]}, "exceptions": []},
        {"key": "comp-tag", "label": "필수 태그 정책 강제", "on": True, "severity": "warn", "params": {"type": "list", "label": "필수 태그 키", "values": ["Environment", "Team", "Service"]}, "exceptions": []},
    ]},
    {"category": "로깅 / 모니터링", "items": [
        {"key": "log-cloudtrail", "label": "CloudTrail 활성화 필수", "on": True, "severity": "block", "params": None, "exceptions": []},
    ]},
    {"category": "비용 관리", "items": [
        {"key": "cost-region", "label": "허용 리전 제한", "on": False, "severity": "warn", "params": {"type": "list", "label": "허용 리전", "values": ["us-east-1", "ap-northeast-2"]}, "exceptions": []},
    ]},
    {"category": "가용성", "items": [
        {"key": "avail-multi-az", "label": "Multi-AZ 배포 필수", "on": True, "severity": "warn", "params": {"type": "services", "label": "적용 서비스", "values": ["RDS"], "options": ["RDS", "ElastiCache", "Aurora"]}, "exceptions": []},
        {"key": "avail-backup", "label": "백업 보존 기간 최소값", "on": True, "severity": "warn", "params": {"type": "number", "label": "최소 보존일", "value": 7, "unit": "일"}, "exceptions": []},
    ]},
]


# ---------------------------------------------------------
# 1. 워크스페이스 목록 조회 (GET /workspaces)
# ---------------------------------------------------------
@router.get("", response_model=SuccessResponse[WorkspaceListResponse])
def get_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    현재 사용자가 접근 가능한 워크스페이스 목록을 조회한다.
    같은 부서의 부서장이 생성한 워크스페이스만 반환된다.
    """
    if not current_user.department_id:
        return SuccessResponse(data=WorkspaceListResponse(items=[]))

    workspaces = (
        db.query(Workspace)
        .join(User, Workspace.owner_id == User.id)
        .filter(
            User.company_id == current_user.company_id,
            User.department_id == current_user.department_id,
        )
        .order_by(Workspace.created_at.desc())
        .all()
    )

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
def update_workspace(
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
def get_opa_settings(
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
def save_opa_settings(
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
# 5. CFN Quick-create URL 생성 (POST /workspaces/cfn-link)
# ---------------------------------------------------------
@router.post("/cfn-link", response_model=SuccessResponse[CfnLinkResponse])
def get_cfn_quick_link(
    req: CfnLinkRequest,
    current_user: User = Depends(get_current_user),
):
    """
    고객이 자신의 AWS 계정에 OpsAgent 스택을 설치할 수 있는
    CloudFormation Quick-create URL을 반환한다.
    Step 1 — 역할 생성 버튼 클릭 시 호출.
    """
    try:
        result = get_cfn_link(req.acctId)
    except StsValidationError:
        raise HTTPException(status_code=400, detail="BAD_REQUEST") from None

    return SuccessResponse(
        data=CfnLinkResponse(url=result.url, acctId=result.acct_id)
    )


# ---------------------------------------------------------
# 7. AWS 연동 테스트 (POST /workspaces/test-aws)
# ---------------------------------------------------------
@router.post("/test-aws", response_model=SuccessResponse[AwsTestResponse])
def test_aws_connection(
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
# 8. 워크스페이스 생성 (POST /workspaces)
# ---------------------------------------------------------
@router.post(
    "",
    response_model=SuccessResponse[WorkspaceCreateResponse],
    status_code=201,
)
def create_workspace(
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

    # 3. 워크스페이스 생성 (기본 OPA 정책 포함)
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
        opa_settings=DEFAULT_OPA_SETTINGS,
    )

    db.add(ws)
    db.commit()
    db.refresh(ws)

    # GitHub webhook 자동 등록 (best-effort)
    if current_user.github_access_token and GITHUB_WEBHOOK_SECRET:
        try:
            hook_id = register_webhook(
                token=current_user.github_access_token,
                owner=req.githubOrg,
                repo=req.repo,
            )
            ws.github_webhook_id = hook_id
            db.commit()
        except Exception as e:
            db.rollback()
            _logger.warning("GitHub webhook 등록 실패 (workspace=%s): %s", ws.id, e)

    return SuccessResponse(
        data=WorkspaceCreateResponse(
            id=str(ws.id),
            alias=ws.alias,
            acctId=ws.acct_id,
            createdAt=ws.created_at.isoformat(),
        )
    )
