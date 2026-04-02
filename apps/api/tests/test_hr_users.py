"""HR 사원 관리 API 단위 테스트 — /api/hr/users"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from apps.api.src.models import Company, User, Workspace
from apps.api.src.security.cognito import CognitoError

# Cognito 함수 패치 경로
_COGNITO = "apps.api.src.routers.hr_users"


# ── GET /api/hr/users ─────────────────────────────────────────────────────────


class TestListUsers:
    def test_hr_lists_own_company_users(self, client_hr, member_user):
        """HR 담당자는 같은 회사 사원 목록을 조회할 수 있다."""
        res = client_hr.get("/api/hr/users")
        assert res.status_code == 200
        ids = [u["id"] for u in res.json()["data"]]
        assert member_user.id in ids

    def test_member_cannot_list_users(self, client_member):
        """일반 사원은 HR 기능에 접근할 수 없다."""
        res = client_member.get("/api/hr/users")
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "HR_ONLY"

    def test_excludes_other_company_users(self, client_hr, db):
        """다른 회사 사원은 목록에 포함되지 않는다."""
        other_co = Company(name="타회사")
        db.add(other_co)
        db.flush()
        other = User(id=str(uuid.uuid4()), email="x@other.com", name="타회사직원", role="member", company_id=other_co.id)
        db.add(other)
        db.flush()

        res = client_hr.get("/api/hr/users")
        ids = [u["id"] for u in res.json()["data"]]
        assert other.id not in ids

    def test_response_ordered_by_name(self, client_hr, db, company):
        """사원 목록은 이름 오름차순으로 정렬된다."""
        for name in ["Charlie", "Alpha", "Beta"]:
            db.add(User(id=str(uuid.uuid4()), email=f"{name}@test.com", name=name, role="member", company_id=company.id))
        db.flush()

        res = client_hr.get("/api/hr/users")
        names = [u["name"] for u in res.json()["data"] if u["name"] in ("Alpha", "Beta", "Charlie")]
        assert names == sorted(names)


# ── GET /api/hr/users/{user_id} ───────────────────────────────────────────────


class TestGetUser:
    def test_get_existing_user(self, client_hr, member_user):
        res = client_hr.get(f"/api/hr/users/{member_user.id}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["id"] == member_user.id
        assert data["email"] == member_user.email

    def test_get_nonexistent_user_returns_404(self, client_hr):
        res = client_hr.get("/api/hr/users/nonexistent-id")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "USER_NOT_FOUND"

    def test_cannot_get_other_company_user(self, client_hr, db):
        """다른 회사 사용자 ID 조회 시 404."""
        other_co = Company(name="타회사")
        db.add(other_co)
        db.flush()
        other = User(id=str(uuid.uuid4()), email="other@other.com", name="타직원", role="member", company_id=other_co.id)
        db.add(other)
        db.flush()

        res = client_hr.get(f"/api/hr/users/{other.id}")
        assert res.status_code == 404

    def test_response_has_required_fields(self, client_hr, member_user):
        res = client_hr.get(f"/api/hr/users/{member_user.id}")
        data = res.json()["data"]
        for field in ("id", "name", "email", "role", "position", "employeeNo", "departmentId", "departmentName"):
            assert field in data


# ── POST /api/hr/users ────────────────────────────────────────────────────────


class TestCreateUser:
    @patch(f"{_COGNITO}.admin_create_user", return_value=("username", "cognito-sub-001"))
    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_create_member_user(self, _sg, _cu, client_hr):
        """일반 사원을 정상 생성한다."""
        res = client_hr.post("/api/hr/users", json={
            "email": "new@test.com",
            "name": "신규사원",
            "role": "member",
            "position": "연구원",
            "employeeNo": "EMP-001",
        })
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["email"] == "new@test.com"
        assert data["name"] == "신규사원"
        assert data["role"] == "member"
        assert data["position"] == "연구원"

    @patch(f"{_COGNITO}.admin_create_user", return_value=("username", "cognito-sub-002"))
    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_create_hr_user(self, _sg, _cu, client_hr):
        """HR 역할 사원도 생성 가능하다."""
        res = client_hr.post("/api/hr/users", json={
            "email": "hr2@test.com",
            "name": "HR2",
            "role": "hr",
        })
        assert res.status_code == 201
        assert res.json()["data"]["role"] == "hr"

    def test_create_with_leader_role_rejected(self, client_hr):
        """leader 역할은 생성 시 직접 지정할 수 없다."""
        res = client_hr.post("/api/hr/users", json={
            "email": "lead@test.com",
            "name": "팀장후보",
            "role": "leader",
        })
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_ROLE"

    @patch(f"{_COGNITO}.admin_create_user", return_value=("username", "cognito-sub-003"))
    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_create_duplicate_email_returns_409(self, _sg, _cu, client_hr, member_user):
        """이미 존재하는 이메일로 생성 요청 시 409."""
        res = client_hr.post("/api/hr/users", json={
            "email": member_user.email,
            "name": "중복이메일",
            "role": "member",
        })
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    @patch(f"{_COGNITO}.admin_create_user",
           side_effect=CognitoError(400, "COGNITO_ERROR", "UsernameExistsException", "UsernameExistsException"))
    def test_cognito_error_propagates(self, _cu, client_hr):
        """Cognito 오류 발생 시 해당 상태코드로 응답한다."""
        res = client_hr.post("/api/hr/users", json={
            "email": "cognifail@test.com",
            "name": "코그니토실패",
            "role": "member",
        })
        assert res.status_code == 400

    def test_member_cannot_create_user(self, client_member):
        res = client_member.post("/api/hr/users", json={"email": "x@x.com", "name": "X", "role": "member"})
        assert res.status_code == 403


# ── PATCH /api/hr/users/{user_id} ────────────────────────────────────────────


class TestUpdateUser:
    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_update_name(self, _sg, client_hr, member_user):
        res = client_hr.patch(f"/api/hr/users/{member_user.id}", json={"name": "변경된이름"})
        assert res.status_code == 200
        assert res.json()["data"]["name"] == "변경된이름"

    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_update_position(self, _sg, client_hr, member_user):
        res = client_hr.patch(f"/api/hr/users/{member_user.id}", json={"position": "선임연구원"})
        assert res.status_code == 200
        assert res.json()["data"]["position"] == "선임연구원"

    @patch(f"{_COGNITO}.admin_set_group", return_value=None)
    def test_update_role_member_to_hr(self, _sg, client_hr, member_user):
        """member → hr 역할 변경 가능."""
        res = client_hr.patch(f"/api/hr/users/{member_user.id}", json={"role": "hr"})
        assert res.status_code == 200
        assert res.json()["data"]["role"] == "hr"

    def test_update_role_to_leader_rejected(self, client_hr, member_user):
        """leader 역할로 직접 변경 불가."""
        res = client_hr.patch(f"/api/hr/users/{member_user.id}", json={"role": "leader"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_ROLE"

    def test_update_existing_leader_role_rejected(self, client_hr, db, company):
        """이미 leader인 사용자의 역할은 HR 엔드포인트로 변경 불가 (부서관리에서만)."""
        leader = User(id=str(uuid.uuid4()), email="ldr@test.com", name="팀장", role="leader", company_id=company.id)
        db.add(leader)
        db.flush()

        res = client_hr.patch(f"/api/hr/users/{leader.id}", json={"role": "member"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "LEADER_MANAGED_BY_DEPT"

    def test_update_nonexistent_user(self, client_hr):
        res = client_hr.patch("/api/hr/users/nonexistent", json={"name": "없음"})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "USER_NOT_FOUND"

    def test_member_cannot_update_user(self, client_member, member_user):
        res = client_member.patch(f"/api/hr/users/{member_user.id}", json={"name": "시도"})
        assert res.status_code == 403


# ── DELETE /api/hr/users/{user_id} ───────────────────────────────────────────


class TestDeleteUser:
    @patch(f"{_COGNITO}.admin_delete_user", return_value=None)
    def test_delete_user_success(self, _du, client_hr, member_user):
        res = client_hr.delete(f"/api/hr/users/{member_user.id}")
        assert res.status_code == 200
        assert "삭제" in res.json()["data"]["message"]

    def test_delete_nonexistent_user(self, client_hr):
        res = client_hr.delete("/api/hr/users/nonexistent")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "USER_NOT_FOUND"

    @patch(f"{_COGNITO}.admin_delete_user", return_value=None)
    def test_delete_workspace_owner_cascades(self, _du, client_hr, db, member_user):
        """워크스페이스 소유자 삭제 시 워크스페이스도 함께 삭제."""
        ws_id = str(uuid.uuid4())
        ws = Workspace(
            id=ws_id,
            alias="테스트WS",
            acct_id="123456789012",
            github_org="test-org",
            repo="test-repo",
            branch="main",
            owner_id=member_user.id,
        )
        db.add(ws)
        db.flush()

        res = client_hr.delete(f"/api/hr/users/{member_user.id}")
        assert res.status_code == 200
        assert db.query(Workspace).filter(Workspace.id == ws_id).first() is None

    def test_member_cannot_delete_user(self, client_member, member_user):
        res = client_member.delete(f"/api/hr/users/{member_user.id}")
        assert res.status_code == 403


# ── POST /api/hr/users/{user_id}/reset-password ───────────────────────────────


class TestResetPassword:
    @patch(f"{_COGNITO}.admin_reset_user_password", return_value=None)
    def test_reset_password_success(self, _rp, client_hr, member_user):
        res = client_hr.post(f"/api/hr/users/{member_user.id}/reset-password")
        assert res.status_code == 200
        assert "임시 비밀번호" in res.json()["data"]["message"]

    def test_reset_password_user_not_found(self, client_hr):
        res = client_hr.post("/api/hr/users/nonexistent/reset-password")
        assert res.status_code == 404

    @patch(f"{_COGNITO}.admin_reset_user_password",
           side_effect=CognitoError(500, "INTERNAL_ERROR", "Cognito 오류", None))
    def test_reset_password_cognito_error(self, _rp, client_hr, member_user):
        res = client_hr.post(f"/api/hr/users/{member_user.id}/reset-password")
        assert res.status_code == 500
