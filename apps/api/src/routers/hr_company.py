"""HR 회사 관리 라우터 — /hr/company"""

from __future__ import annotations

import os
import time

import boto3
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Company, Department
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.hr import CompanyResponse, CompanyUpdateRequest
from apps.api.src.routers.hr_deps import require_hr

router = APIRouter(prefix="/hr/company", tags=["HR - Company"])

S3_BUCKET = os.getenv("S3_PUBLIC_BUCKET", "dndn-public")
S3_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
MAX_SIZE = 2 * 1024 * 1024  # 2MB


def _to_response(company: Company) -> CompanyResponse:
    return CompanyResponse(
        id=company.id,
        name=company.name,
        logoUrl=company.logo_url,
    )


# ── GET /hr/company ───────────────────────────────────────
@router.get("", response_model=SuccessResponse[CompanyResponse])
def get_company(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    """현재 HR 유저의 소속 회사 정보 반환."""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="COMPANY_NOT_FOUND")
    return SuccessResponse(data=_to_response(company))


# ── PATCH /hr/company ─────────────────────────────────────
@router.patch("", response_model=SuccessResponse[CompanyResponse])
def update_company(
    req: CompanyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    """회사명 변경."""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="COMPANY_NOT_FOUND")

    if req.name is not None:
        new_name = req.name.strip()
        company.name = new_name
        # 루트 부서(parent_id=NULL)명도 회사명과 동기화
        root_dept = db.query(Department).filter(
            Department.company_id == company.id,
            Department.parent_id.is_(None),
        ).first()
        if root_dept:
            root_dept.name = new_name

    db.commit()
    db.refresh(company)
    return SuccessResponse(data=_to_response(company))


# ── POST /hr/company/logo ────────────────────────────────
@router.post("/logo", response_model=SuccessResponse[CompanyResponse])
def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    """회사 로고 이미지 업로드 (S3)."""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="COMPANY_NOT_FOUND")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="INVALID_FILE_TYPE")

    data = file.file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="FILE_TOO_LARGE")

    # 확장자 결정
    ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/webp": "webp"}
    ext = ext_map.get(file.content_type, "png")
    s3_key = f"logos/{company.id}/logo.{ext}"

    s3 = boto3.client("s3", region_name=S3_REGION)
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=data,
        ContentType=file.content_type,
    )

    logo_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}?v={int(time.time())}"
    company.logo_url = logo_url
    db.commit()
    db.refresh(company)
    return SuccessResponse(data=_to_response(company))
