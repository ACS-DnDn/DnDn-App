"""
공통 테스트 픽스처.

- SQLite 인메모리 DB 사용 (MySQL 없이 단위 테스트 가능)
- Cognito·S3 등 외부 서비스는 각 테스트에서 unittest.mock.patch로 격리
- 테스트 함수마다 독립된 DB 세션 사용 (test 간 데이터 오염 없음)
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.src.database import get_db
from apps.api.src.models import Base, Company, Department, User
from apps.api.src.routers import (
    dashboard as dashboard_router,
    documents as documents_router,
    hr_departments as hr_departments_router,
    hr_users as hr_users_router,
    internal as internal_router,
    org as org_router,
)
from apps.api.src.routers.auth import get_current_user


# ── DB 픽스처 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """테스트마다 새로운 SQLite 인메모리 DB를 생성하고 테스트 종료 시 파기."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 단일 커넥션 유지 — commit 후에도 인메모리 DB 유지
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ── 공통 데이터 픽스처 ────────────────────────────────────────────────────────


@pytest.fixture
def company(db):
    """테스트용 회사 레코드."""
    c = Company(name="테스트회사")
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def hr_user(db, company):
    """HR 권한 사용자."""
    u = User(
        id=str(uuid.uuid4()),
        email="hr@test.com",
        name="HR담당자",
        role="hr",
        company_id=company.id,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def member_user(db, company):
    """일반 사원 사용자."""
    u = User(
        id=str(uuid.uuid4()),
        email="member@test.com",
        name="일반사원",
        role="member",
        company_id=company.id,
    )
    db.add(u)
    db.flush()
    return u


# ── 테스트 앱 픽스처 ──────────────────────────────────────────────────────────


def _build_test_app(db_session) -> FastAPI:
    """실제 라우터를 등록하되, DB·인증 의존성을 오버라이드한 테스트용 앱."""
    app = FastAPI()

    # main.py와 동일한 에러 응답 포맷 등록
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": {"code": str(exc.detail), "message": ""}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": {"code": "VALIDATION_ERROR", "message": ""}},
        )

    app.include_router(org_router.router, prefix="/api")
    app.include_router(hr_users_router.router, prefix="/api")
    app.include_router(hr_departments_router.router, prefix="/api")
    app.include_router(dashboard_router.router, prefix="/api")
    app.include_router(documents_router.router, prefix="/api")
    app.include_router(internal_router.router)  # /internal — prefix 없음

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return app


@pytest.fixture
def test_app(db):
    return _build_test_app(db)


@pytest.fixture
def client_hr(test_app, hr_user):
    """HR 권한 사용자로 인증된 TestClient."""
    test_app.dependency_overrides[get_current_user] = lambda: hr_user
    return TestClient(test_app, raise_server_exceptions=True)


@pytest.fixture
def client_member(test_app, member_user):
    """일반 사원 권한으로 인증된 TestClient."""
    test_app.dependency_overrides[get_current_user] = lambda: member_user
    return TestClient(test_app, raise_server_exceptions=True)
