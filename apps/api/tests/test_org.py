"""GET /api/org/members 단위 테스트."""
from __future__ import annotations

import uuid

from apps.api.src.models import Company, Department, User


class TestGetOrgMembers:
    def test_returns_own_company_users(self, client_member, member_user):
        """같은 회사 직원이 목록에 포함된다."""
        res = client_member.get("/api/org/members")
        assert res.status_code == 200
        assert res.json()["success"] is True
        all_members = _flatten_members(res)
        assert any(m["id"] == member_user.id for m in all_members)

    def test_excludes_other_company_users(self, client_member, db):
        """다른 회사 직원은 목록에 포함되지 않는다."""
        other_co = Company(name="다른회사")
        db.add(other_co)
        db.flush()
        other_user = User(
            id=str(uuid.uuid4()),
            email="other@other.com",
            name="타회사직원",
            role="member",
            company_id=other_co.id,
        )
        db.add(other_user)
        db.flush()

        res = client_member.get("/api/org/members")
        assert res.status_code == 200
        all_members = _flatten_members(res)
        assert not any(m["id"] == other_user.id for m in all_members)

    def test_keyword_filter_by_name(self, client_member, db, company):
        """이름으로 검색하면 일치하는 사람만 반환된다."""
        alice = User(id=str(uuid.uuid4()), email="alice@test.com", name="Alice", role="member", company_id=company.id)
        bob = User(id=str(uuid.uuid4()), email="bob@test.com", name="Bob", role="member", company_id=company.id)
        db.add_all([alice, bob])
        db.flush()

        res = client_member.get("/api/org/members?keyword=Alice")
        assert res.status_code == 200
        names = [m["name"] for m in _flatten_members(res)]
        assert "Alice" in names
        assert "Bob" not in names

    def test_keyword_filter_by_department(self, client_member, db, company):
        """부서명으로 검색하면 해당 부서 사람만 반환된다."""
        dept = Department(id=str(uuid.uuid4()), name="개발팀", company_id=company.id)
        db.add(dept)
        db.flush()
        dev = User(id=str(uuid.uuid4()), email="dev@test.com", name="개발자", role="member", company_id=company.id, department_id=dept.id)
        sales = User(id=str(uuid.uuid4()), email="sales@test.com", name="영업자", role="member", company_id=company.id)
        db.add_all([dev, sales])
        db.flush()

        res = client_member.get("/api/org/members?keyword=개발팀")
        assert res.status_code == 200
        names = [m["name"] for m in _flatten_members(res)]
        assert "개발자" in names
        assert "영업자" not in names

    def test_users_grouped_by_department(self, client_member, db, company):
        """부서가 있는 직원은 해당 부서 그룹에 속한다."""
        dept = Department(id=str(uuid.uuid4()), name="인프라팀", company_id=company.id)
        db.add(dept)
        db.flush()
        u = User(id=str(uuid.uuid4()), email="infra@test.com", name="인프라담당", role="member", company_id=company.id, department_id=dept.id)
        db.add(u)
        db.flush()

        res = client_member.get("/api/org/members")
        assert res.status_code == 200
        dept_names = [item["dept"] for item in res.json()["data"]["items"]]
        assert "인프라팀" in dept_names

    def test_no_department_falls_back_to_default(self, client_member, member_user):
        """부서가 없는 직원은 기본 부서명 그룹에 속한다."""
        # member_user는 department_id=None
        res = client_member.get("/api/org/members")
        assert res.status_code == 200
        dept_names = [item["dept"] for item in res.json()["data"]["items"]]
        assert "클라우드엔지니어링팀" in dept_names

    def test_member_item_has_required_fields(self, client_member, member_user):
        """각 멤버 항목에 id, name, rank 필드가 있다."""
        res = client_member.get("/api/org/members")
        assert res.status_code == 200
        for m in _flatten_members(res):
            assert "id" in m
            assert "name" in m
            assert "rank" in m

    def test_position_used_as_rank(self, client_member, db, company):
        """position이 설정된 직원은 rank에 해당 값이 반환된다."""
        u = User(id=str(uuid.uuid4()), email="senior@test.com", name="시니어", role="member", company_id=company.id, position="수석연구원")
        db.add(u)
        db.flush()

        res = client_member.get("/api/org/members")
        assert res.status_code == 200
        all_members = _flatten_members(res)
        senior = next((m for m in all_members if m["name"] == "시니어"), None)
        assert senior is not None
        assert senior["rank"] == "수석연구원"

    def test_no_position_falls_back_to_default_rank(self, client_member, member_user):
        """position이 없으면 기본 rank '연구원'이 반환된다."""
        # member_user는 position=None
        res = client_member.get("/api/org/members")
        assert res.status_code == 200
        all_members = _flatten_members(res)
        user_entry = next((m for m in all_members if m["id"] == member_user.id), None)
        assert user_entry is not None
        assert user_entry["rank"] == "연구원"


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _flatten_members(res) -> list[dict]:
    """응답의 모든 부서 항목에서 멤버 리스트를 평탄화한다."""
    return [m for dept in res.json()["data"]["items"] for m in dept["members"]]
