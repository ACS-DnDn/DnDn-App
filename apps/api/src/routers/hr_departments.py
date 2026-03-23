"""HR 부서 관리 라우터 — /hr/departments"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Department
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.hr import (
    DepartmentNode,
    DepartmentCreateRequest,
    DepartmentSetLeaderRequest,
)
from apps.api.src.routers.auth import get_current_user
from apps.api.src.routers.hr_deps import require_hr
from apps.api.src.security.cognito import admin_set_group, CognitoError

router = APIRouter(prefix="/hr/departments", tags=["HR - Departments"])


def _to_node(dept: Department) -> DepartmentNode:
    return DepartmentNode(
        id=dept.id,
        name=dept.name,
        parentId=dept.parent_id,
        leaderId=dept.leader_id,
        leaderName=dept.leader.name if dept.leader else None,
    )


# ── GET /hr/departments ────────────────────────────────────
@router.get("", response_model=SuccessResponse[list[DepartmentNode]])
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """전체 부서 목록 반환 (트리 구성은 프론트에서)."""
    depts = db.query(Department).filter(
        Department.company_id == current_user.company_id
    ).all()
    return SuccessResponse(data=[_to_node(d) for d in depts])


# ── POST /hr/departments ───────────────────────────────────
@router.post("", response_model=SuccessResponse[DepartmentNode], status_code=201)
def create_department(
    req: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    if req.parentId:
        parent = db.query(Department).filter(
            Department.id == req.parentId,
            Department.company_id == current_user.company_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="PARENT_NOT_FOUND")

    dept = Department(
        name=req.name,
        parent_id=req.parentId,
        leader_id=None,
        company_id=current_user.company_id,
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return SuccessResponse(data=_to_node(dept))


# ── DELETE /hr/departments/{dept_id} ──────────────────────
@router.delete("/{dept_id}", response_model=SuccessResponse[dict])
def delete_department(
    dept_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    dept = db.query(Department).filter(
        Department.id == dept_id,
        Department.company_id == current_user.company_id,
    ).first()
    if not dept:
        raise HTTPException(status_code=404, detail="DEPT_NOT_FOUND")

    has_children = db.query(Department).filter(
        Department.parent_id == dept_id,
        Department.company_id == current_user.company_id,
    ).first()
    if has_children:
        raise HTTPException(status_code=400, detail="HAS_CHILDREN")

    db.delete(dept)
    db.commit()
    return SuccessResponse(data={"message": "부서가 삭제되었습니다."})


# ── PATCH /hr/departments/{dept_id}/leader ─────────────────
@router.patch("/{dept_id}/leader", response_model=SuccessResponse[DepartmentNode])
def set_leader(
    dept_id: str,
    req: DepartmentSetLeaderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    dept = db.query(Department).filter(
        Department.id == dept_id,
        Department.company_id == current_user.company_id,
    ).first()
    if not dept:
        raise HTTPException(status_code=404, detail="DEPT_NOT_FOUND")

    # 기존 부서장 → member로 강등
    if dept.leader_id and dept.leader_id != req.leaderId:
        old_leader = db.query(User).filter(
            User.id == dept.leader_id,
            User.company_id == current_user.company_id,
        ).first()
        if old_leader and old_leader.role == "leader":
            try:
                admin_set_group(old_leader.email, "member", old_group="leader")
            except CognitoError as e:
                raise HTTPException(status_code=e.status, detail=e.code) from e
            old_leader.role = "member"

    # 신규 부서장 → leader로 승격
    if req.leaderId:
        new_leader = db.query(User).filter(
            User.id == req.leaderId,
            User.company_id == current_user.company_id,
        ).first()
        if not new_leader:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
        if new_leader.role != "leader":
            try:
                admin_set_group(new_leader.email, "leader", old_group=new_leader.role)
            except CognitoError as e:
                raise HTTPException(status_code=e.status, detail=e.code) from e
            new_leader.role = "leader"

    dept.leader_id = req.leaderId
    db.commit()
    db.refresh(dept)
    return SuccessResponse(data=_to_node(dept))
