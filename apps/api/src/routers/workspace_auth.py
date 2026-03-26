# apps/api/routers/workspace_auth.py
"""워크스페이스 접근 권한 헬퍼.

- _check_ws_member : 같은 부서 구성원이면 통과 (조회 용도)
- _check_ws_leader : 같은 부서 + leader/admin 역할이어야 통과 (설정 변경 용도)
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from apps.api.src.models import User, Workspace


def _check_ws_member(db: Session, workspace_id: str, current_user: User) -> Workspace:
    """워크스페이스 존재 확인 + 같은 부서 소속 여부 확인 (조회 권한)."""
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    # 워크스페이스 소유자의 부서와 현재 사용자의 부서가 동일한지 확인
    owner = db.query(User).filter(User.id == ws.owner_id).first()
    if (
        not owner
        or owner.company_id != current_user.company_id
        or owner.department_id != current_user.department_id
    ):
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    return ws


def _check_ws_leader(db: Session, workspace_id: str, current_user: User) -> Workspace:
    """워크스페이스 존재 확인 + 같은 부서 + leader/admin 역할 확인 (설정 변경 권한)."""
    ws = _check_ws_member(db, workspace_id, current_user)

    if current_user.role not in ("leader", "admin"):
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    return ws
