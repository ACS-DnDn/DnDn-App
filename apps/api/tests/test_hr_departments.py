"""HR 부서 관리 API 단위 테스트 — /api/hr/departments"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.api.src.models import Department, User
from apps.api.src.security.cognito import CognitoError

_COGNITO = "apps.api.src.routers.hr_departments"


# ── GET /api/hr/departments ───────────────────────────────────────────────────


class TestListDepartments:
    def test_returns_own_company_departments(self, client_member, db, company):
        """같은 회사 부서 목록이 반환된다."""
        dept = Department(id=str(uuid.uuid4()), name="개발팀", company_id=company.id)
        db.add(dept)
        db.flush()

        res = client_member.get("/api/hr/departments")
        assert res.status_code == 200
        names = [d["name"] for d in res.json()["data"]]
        assert "개발팀" in names

    def test_excludes_other_company_departments(self, client_member, db):
        """다른 회사 부서는 목록에 없다."""
        from apps.api.src.models import Company
        other_co = Company(name="타회사")
        db.add(other_co)
        db.flush()
        other_dept = Department(id=str(uuid.uuid4()), name="타회사기획팀", company_id=other_co.id)
        db.add(other_dept)
        db.flush()

        res = client_member.get("/api/hr/departments")
        names = [d["name"] for d in res.json()["data"]]
        assert "타회사기획팀" not in names

    def test_member_can_list_departments(self, client_member):
        """일반 사원도 부서 목록 조회 가능 (get_current_user만 필요)."""
        res = client_member.get("/api/hr/departments")
        assert res.status_code == 200

    def test_response_has_required_fields(self, client_member, db, company):
        dept = Department(id=str(uuid.uuid4()), name="QA팀", company_id=company.id)
        db.add(dept)
        db.flush()

        res = client_member.get("/api/hr/departments")
        for d in res.json()["data"]:
            for field in ("id", "name", "parentId", "leaderId", "leaderName"):
                assert field in d


# ── POST /api/hr/departments ──────────────────────────────────────────────────


class TestCreateDepartment:
    def test_create_root_department(self, client_hr):
        """최상위 부서를 생성한다."""
        res = client_hr.post("/api/hr/departments", json={"name": "신규부서"})
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["name"] == "신규부서"
        assert data["parentId"] is None
        assert data["leaderId"] is None

    def test_create_child_department(self, client_hr, db, company):
        """하위 부서를 생성한다."""
        parent = Department(id=str(uuid.uuid4()), name="본부", company_id=company.id)
        db.add(parent)
        db.flush()

        res = client_hr.post("/api/hr/departments", json={"name": "팀", "parentId": parent.id})
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["name"] == "팀"
        assert data["parentId"] == parent.id

    def test_create_with_nonexistent_parent_returns_404(self, client_hr):
        """존재하지 않는 부모 부서 ID 사용 시 404."""
        res = client_hr.post("/api/hr/departments", json={"name": "고아부서", "parentId": "nonexistent-id"})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "PARENT_NOT_FOUND"

    def test_member_cannot_create_department(self, client_member):
        res = client_member.post("/api/hr/departments", json={"name": "몰래만든팀"})
        assert res.status_code == 403


# ── DELETE /api/hr/departments/{dept_id} ─────────────────────────────────────


class TestDeleteDepartment:
    def test_delete_leaf_department(self, client_hr, db, company):
        """자식 없는 부서는 삭제 가능."""
        dept = Department(id=str(uuid.uuid4()), name="삭제대상팀", company_id=company.id)
        db.add(dept)
        db.flush()

        res = client_hr.delete(f"/api/hr/departments/{dept.id}")
        assert res.status_code == 200
        assert "삭제" in res.json()["data"]["message"]

    def test_delete_nonexistent_department(self, client_hr):
        res = client_hr.delete("/api/hr/departments/nonexistent")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "DEPT_NOT_FOUND"

    def test_delete_department_with_children_blocked(self, client_hr, db, company):
        """하위 부서가 있는 부서는 삭제 불가."""
        parent = Department(id=str(uuid.uuid4()), name="상위부서", company_id=company.id)
        db.add(parent)
        db.flush()
        child = Department(id=str(uuid.uuid4()), name="하위부서", parent_id=parent.id, company_id=company.id)
        db.add(child)
        db.flush()

        res = client_hr.delete(f"/api/hr/departments/{parent.id}")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "HAS_CHILDREN"

    def test_member_cannot_delete_department(self, client_member, db, company):
        dept = Department(id=str(uuid.uuid4()), name="보호팀", company_id=company.id)
        db.add(dept)
        db.flush()

        res = client_member.delete(f"/api/hr/departments/{dept.id}")
        assert res.status_code == 403


# ── PATCH /api/hr/departments/{dept_id}/leader ───────────────────────────────


class TestSetLeader:
    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_set_leader_promotes_to_leader_role(self, _sg, client_hr, db, company):
        """부서장 지정 시 해당 사용자 role이 leader로 변경된다."""
        dept = Department(id=str(uuid.uuid4()), name="팀", company_id=company.id)
        db.add(dept)
        db.flush()
        candidate = User(id=str(uuid.uuid4()), email="cand@test.com", name="후보", role="member", company_id=company.id)
        db.add(candidate)
        db.flush()

        res = client_hr.patch(f"/api/hr/departments/{dept.id}/leader", json={"leaderId": candidate.id})
        assert res.status_code == 200
        assert res.json()["data"]["leaderId"] == candidate.id

        db.refresh(candidate)
        assert candidate.role == "leader"

    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_set_leader_demotes_old_leader(self, _sg, client_hr, db, company):
        """기존 부서장을 교체하면 이전 부서장은 member로 강등된다."""
        dept = Department(id=str(uuid.uuid4()), name="팀", company_id=company.id)
        db.add(dept)
        db.flush()
        old_leader = User(id=str(uuid.uuid4()), email="old@test.com", name="전임팀장", role="leader", company_id=company.id)
        new_leader = User(id=str(uuid.uuid4()), email="new@test.com", name="신임팀장", role="member", company_id=company.id)
        db.add_all([old_leader, new_leader])
        db.flush()
        dept.leader_id = old_leader.id
        db.flush()

        res = client_hr.patch(f"/api/hr/departments/{dept.id}/leader", json={"leaderId": new_leader.id})
        assert res.status_code == 200

        db.refresh(old_leader)
        assert old_leader.role == "member"

    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_set_leader_hr_role_unchanged(self, _sg, client_hr, db, company):
        """hr 역할 사용자를 부서장으로 지정해도 role은 hr 유지."""
        dept = Department(id=str(uuid.uuid4()), name="팀", company_id=company.id)
        db.add(dept)
        db.flush()
        hr_candidate = User(id=str(uuid.uuid4()), email="hr2@test.com", name="HR겸팀장", role="hr", company_id=company.id)
        db.add(hr_candidate)
        db.flush()

        res = client_hr.patch(f"/api/hr/departments/{dept.id}/leader", json={"leaderId": hr_candidate.id})
        assert res.status_code == 200

        db.refresh(hr_candidate)
        assert hr_candidate.role == "hr"  # hr 역할은 변경되지 않음

    def test_set_leader_nonexistent_department(self, client_hr):
        res = client_hr.patch("/api/hr/departments/nonexistent/leader", json={"leaderId": "some-user"})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "DEPT_NOT_FOUND"

    def test_set_leader_nonexistent_user(self, client_hr, db, company):
        dept = Department(id=str(uuid.uuid4()), name="팀", company_id=company.id)
        db.add(dept)
        db.flush()

        res = client_hr.patch(f"/api/hr/departments/{dept.id}/leader", json={"leaderId": "ghost-user-id"})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "USER_NOT_FOUND"

    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_unset_leader(self, _sg, client_hr, db, company):
        """leaderId=None으로 부서장을 해제한다."""
        dept = Department(id=str(uuid.uuid4()), name="팀", company_id=company.id)
        db.add(dept)
        db.flush()

        res = client_hr.patch(f"/api/hr/departments/{dept.id}/leader", json={"leaderId": None})
        assert res.status_code == 200
        assert res.json()["data"]["leaderId"] is None

    def test_member_cannot_set_leader(self, client_member, db, company):
        dept = Department(id=str(uuid.uuid4()), name="팀", company_id=company.id)
        db.add(dept)
        db.flush()

        res = client_member.patch(f"/api/hr/departments/{dept.id}/leader", json={"leaderId": None})
        assert res.status_code == 403
