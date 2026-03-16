# apps/api/routers/org.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from collections import defaultdict

from apps.api.src.database import get_db
from apps.api.src.models import User
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.org import OrgMembersResponse

router = APIRouter(prefix="/org", tags=["Organization"])


@router.get("/members", response_model=OrgMembersResponse)
async def get_org_members(
    keyword: Optional[str] = Query(None, description="이름 또는 부서명 검색"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 일단 모든 유저를 가져옵니다.
    users = db.query(User).all()

    # 2. 부서별로 사람들을 모아둘 딕셔너리 준비
    dept_groups = defaultdict(list)

    for user in users:
        # 💡 DB에 부서/직급 컬럼이 없다면 기본값으로 처리되도록 유연하게 작성
        dept_name = getattr(user, "department", "클라우드엔지니어링팀")
        rank_name = getattr(user, "rank", "연구원")

        # 3. 검색어(keyword) 필터링 로직 (파이썬 레벨에서 검사)
        if keyword:
            # 이름에도 없고, 부서명에도 검색어가 없으면 이 사람은 건너뜁니다.
            if (keyword.lower() not in user.name.lower()) and (
                keyword.lower() not in dept_name.lower()
            ):
                continue

        # 4. 조건에 맞는 사람을 해당 부서 리스트에 쏙쏙 집어넣습니다.
        dept_groups[dept_name].append(
            {"id": str(user.id), "name": user.name, "rank": rank_name}
        )

    # 5. 명세서의 응답 규격(data 배열)에 맞게 포장합니다.
    result_data = []
    for dept, members in dept_groups.items():
        if members:  # 멤버가 한 명이라도 있는 부서만 추가
            result_data.append({"dept": dept, "members": members})

    return {"data": result_data}
