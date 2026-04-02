"""HR 사원 관리 라우터 — /hr/users"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Department, Document, Approval, Workspace, ReportSettings, Attachment, DocumentRead
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.hr import (
    HrUserResponse,
    HrUserCreateRequest,
    HrUserUpdateRequest,
)
import uuid

from apps.api.src.routers.hr_deps import require_hr

from apps.api.src.security.cognito import (
    admin_create_user,
    admin_delete_user,
    admin_reset_user_password,
    admin_set_group,
    CognitoError,
)

router = APIRouter(prefix="/hr/users", tags=["HR - Users"])

VALID_ROLES = {"hr", "member"}  # leader는 부서관리에서만 지정


def _to_response(user: User) -> HrUserResponse:
    return HrUserResponse(
        id=user.id,
        employeeNo=user.employee_no,
        name=user.name,
        email=user.email,
        position=user.position,
        role=user.role,
        departmentId=user.department_id,
        departmentName=user.department.name if user.department else None,
    )


# ── GET /hr/users ──────────────────────────────────────────
@router.get("", response_model=SuccessResponse[list[HrUserResponse]])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    users = db.query(User).filter(User.company_id == current_user.company_id).order_by(User.name).all()
    return SuccessResponse(data=[_to_response(u) for u in users])


# ── GET /hr/users/{user_id} ────────────────────────────────
@router.get("/{user_id}", response_model=SuccessResponse[HrUserResponse])
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return SuccessResponse(data=_to_response(user))


# ── POST /hr/users ─────────────────────────────────────────
@router.post("", response_model=SuccessResponse[HrUserResponse], status_code=201)
def create_user(
    req: HrUserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="INVALID_ROLE")

    # 0. DB 중복 선검사
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="EMAIL_ALREADY_EXISTS")

    # 1. Cognito 사용자 생성
    try:
        username, cognito_sub = admin_create_user(req.email, req.name)
        admin_set_group(username, req.role)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    # 2. DB 저장 (cognito_sub를 즉시 매핑 — 첫 로그인 시 ghost user 생성 방지)
    user = User(
        id=str(uuid.uuid4()),
        cognito_sub=cognito_sub or None,
        email=req.email,
        name=req.name,
        role=req.role,
        employee_no=req.employeeNo,
        position=req.position,
        department_id=req.departmentId,
        company_id=current_user.company_id,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        try:
            admin_delete_user(req.email)
        except CognitoError:
            pass  # best-effort cleanup
        raise HTTPException(status_code=409, detail="EMAIL_ALREADY_EXISTS")

    return SuccessResponse(data=_to_response(user))


# ── PATCH /hr/users/{user_id} ──────────────────────────────
@router.patch("/{user_id}", response_model=SuccessResponse[HrUserResponse])
def update_user(
    user_id: str,
    req: HrUserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    # 역할 변경 시 Cognito 그룹도 변경 (leader는 부서관리에서만 지정)
    if req.role and req.role != user.role:
        if req.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="INVALID_ROLE")
        if user.role == "leader":
            raise HTTPException(status_code=400, detail="LEADER_MANAGED_BY_DEPT")
        try:
            admin_set_group(user.email, req.role, old_group=user.role)
        except CognitoError as e:
            raise HTTPException(status_code=e.status, detail=e.code) from e
        user.role = req.role

    if req.name is not None:
        user.name = req.name
    if req.employeeNo is not None:
        user.employee_no = req.employeeNo
    if req.position is not None:
        user.position = req.position
    if req.departmentId is not None:
        user.department_id = req.departmentId or None

    db.commit()
    db.refresh(user)
    return SuccessResponse(data=_to_response(user))


# ── DELETE /hr/users/{user_id} ─────────────────────────────
@router.delete("/{user_id}", response_model=SuccessResponse[dict])
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    # 소유한 워크스페이스도 함께 삭제 (하위 테이블 순서대로 정리)
    owned_workspaces = db.query(Workspace).filter(Workspace.owner_id == user_id).all()
    for ws in owned_workspaces:
        doc_ids = [d.id for d in db.query(Document.id).filter(Document.workspace_id == ws.id).all()]
        if doc_ids:
            db.query(Attachment).filter(Attachment.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(DocumentRead).filter(DocumentRead.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Approval).filter(Approval.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Document).filter(Document.workspace_id == ws.id).delete(synchronize_session=False)
        db.query(ReportSettings).filter(ReportSettings.workspace_id == ws.id).delete(synchronize_session=False)
        db.delete(ws)

    try:
        admin_delete_user(user.email)
    except CognitoError as e:
        # Cognito에 없는 사용자(수동 DB 삽입 등)면 무시하고 DB만 삭제
        if e.exception_name != "UserNotFoundException":
            raise HTTPException(status_code=e.status, detail=e.code) from e

    # FK 참조 정리
    db.query(Department).filter(Department.leader_id == user_id).update({"leader_id": None})
    db.query(Document).filter(Document.author_id == user_id).update({"author_id": None})
    db.query(Approval).filter(Approval.user_id == user_id).delete()

    db.delete(user)
    db.commit()
    return SuccessResponse(data={"message": "계정이 삭제되었습니다."})


# ── POST /hr/users/{user_id}/reset-password ────────────────
@router.post("/{user_id}/reset-password", response_model=SuccessResponse[dict])
def reset_password(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    try:
        admin_reset_user_password(user.email)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(data={"message": "임시 비밀번호가 발급되었습니다."})
