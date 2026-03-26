"""HR 라우터 공통 의존성."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from apps.api.src.models import User
from apps.api.src.routers.auth import get_current_user


def require_hr(current_user: User = Depends(get_current_user)) -> User:
    """HR 관리자 전용 접근 제한."""
    if current_user.role != "hr":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="HR_ONLY")
    return current_user


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    """슈퍼어드민 전용 접근 제한."""
    if current_user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SUPERADMIN_ONLY")
    return current_user
