"""슈퍼어드민 회사 관리 라우터 — /admin/companies"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Company
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.hr import AdminCompanyCreateRequest, AdminCompanyResponse
from apps.api.src.routers.hr_deps import require_superadmin
from apps.api.src.security.cognito import (
    admin_create_user,
    admin_set_group,
    CognitoError,
)

router = APIRouter(prefix="/admin/companies", tags=["Admin - Companies"])


def _to_response(company: Company) -> AdminCompanyResponse:
    # HR 계정 찾기
    hr_user = None
    for u in company.users:
        if u.role == "hr":
            hr_user = u
            break
    return AdminCompanyResponse(
        id=company.id,
        name=company.name,
        logoUrl=company.logo_url,
        hrEmail=hr_user.email if hr_user else None,
        createdAt=company.created_at.isoformat() if company.created_at else None,
    )


# ── GET /admin/companies ──────────────────────────────────
@router.get("", response_model=SuccessResponse[list[AdminCompanyResponse]])
def list_companies(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    companies = db.query(Company).order_by(Company.id).all()
    return SuccessResponse(data=[_to_response(c) for c in companies])


# ── POST /admin/companies ─────────────────────────────────
@router.post("", response_model=SuccessResponse[AdminCompanyResponse], status_code=201)
def create_company(
    req: AdminCompanyCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    # 이메일 중복 확인
    if db.query(User).filter(User.email == req.hrEmail).first():
        raise HTTPException(status_code=409, detail="EMAIL_ALREADY_EXISTS")

    # 1. 회사 생성 (이름 미설정 — HR이 직접 설정)
    company = Company(name="미설정")
    db.add(company)
    db.flush()  # company.id 확보

    # 2. Cognito 계정 생성
    try:
        username, cognito_sub = admin_create_user(req.hrEmail, req.hrName)
        admin_set_group(username, "hr")
    except CognitoError as e:
        db.rollback()
        raise HTTPException(status_code=e.status, detail=e.code) from e

    # 3. DB 유저 생성
    user = User(
        id=str(uuid.uuid4()),
        cognito_sub=cognito_sub or None,
        email=req.hrEmail,
        name=req.hrName,
        role="hr",
        company_id=company.id,
    )
    db.add(user)
    db.commit()
    db.refresh(company)

    return SuccessResponse(data=_to_response(company))


# ── DELETE /admin/companies/{company_id} ──────────────────
@router.delete("/{company_id}", response_model=SuccessResponse[dict])
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="COMPANY_NOT_FOUND")

    # 소속 사용자가 있으면 삭제 차단
    user_count = db.query(User).filter(User.company_id == company_id).count()
    if user_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"이 회사에 {user_count}명의 사용자가 소속되어 있어 삭제할 수 없습니다.",
        )

    db.delete(company)
    db.commit()
    return SuccessResponse(data={"message": "회사가 삭제되었습니다."})
