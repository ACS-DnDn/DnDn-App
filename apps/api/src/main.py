from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from prometheus_client import Counter, Histogram, make_asgi_app
import time
from apps.api.src.database import engine
from apps.api.src.models import Base
from apps.api.src.routers import (
    admin_companies,
    auth,
    dashboard,
    documents,
    github,
    internal,
    org,
    report_settings,
    reports,
    workspaces,
    hr_users,
    hr_departments,
    hr_company,
    slack,
)

# 1. MariaDB에 테이블 자동 생성 (models.py에 정의된 규격대로)
# 주의: 이미 테이블이 있으면 덮어쓰지 않습니다. 컬럼 추가/변경은 반영되지 않습니다.
# TODO: 운영 환경 전환 전 Alembic 마이그레이션으로 교체 필요
#       (create_all은 개발/테스트 전용으로만 사용)
Base.metadata.create_all(bind=engine)

# 기존 테이블에 누락된 컬럼 자동 추가 (create_all은 새 컬럼을 추가하지 않으므로)
from sqlalchemy import inspect as _sa_inspect, text as _sa_text
_insp = _sa_inspect(engine)
_migrations = [
    ("documents", "submit_comment", "TEXT"),
    ("documents", "pr_number", "INTEGER"),
    ("documents", "pr_url", "VARCHAR(500)"),
    ("documents", "pr_status", "VARCHAR(20)"),
    ("workspaces", "github_webhook_id", "INTEGER"),
    ("documents", "auto_merge", "BOOLEAN"),
    ("documents", "deploy_log", "JSON"),
    ("companies", "created_at", "DATETIME"),
    ("workspaces", "code", "VARCHAR(20)"),
]
with engine.begin() as _conn:
    for _tbl, _col, _coltype in _migrations:
        if _tbl in _insp.get_table_names():
            existing = [c["name"] for c in _insp.get_columns(_tbl)]
            if _col not in existing:
                _conn.execute(_sa_text(f"ALTER TABLE {_tbl} ADD COLUMN {_col} {_coltype}"))
del _insp, _migrations

# 기존 워크스페이스에 code가 없으면 자동 백필
import random as _random
_WS_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ2345678"
with engine.begin() as _conn:
    _rows = _conn.execute(_sa_text("SELECT id FROM workspaces WHERE code IS NULL")).fetchall()
    if _rows:
        _existing = {r[0] for r in _conn.execute(_sa_text("SELECT code FROM workspaces WHERE code IS NOT NULL")).fetchall()}
        for (_ws_id,) in _rows:
            while True:
                _code = "".join(_random.choices(_WS_CODE_CHARS, k=3))
                if _code not in _existing:
                    break
            _conn.execute(_sa_text("UPDATE workspaces SET code = :code WHERE id = :id"), {"code": _code, "id": _ws_id})
            _existing.add(_code)
    # 백필 완료 후 unique index 생성 (ALTER TABLE ADD COLUMN은 unique 제약을 만들지 않으므로)
    _idx_exists = _conn.execute(_sa_text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'workspaces' "
        "AND INDEX_NAME = 'idx_workspaces_code_unique'"
    )).scalar()
    if not _idx_exists:
        _conn.execute(_sa_text(
            "CREATE UNIQUE INDEX idx_workspaces_code_unique ON workspaces(code)"
        ))
    # acct_id unique index (기존 테이블에 제약 추가)
    _acct_idx = _conn.execute(_sa_text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'workspaces' "
        "AND INDEX_NAME = 'idx_workspaces_acct_id_unique'"
    )).scalar()
    if not _acct_idx:
        _conn.execute(_sa_text(
            "CREATE UNIQUE INDEX idx_workspaces_acct_id_unique ON workspaces(acct_id)"
        ))
del _random, _WS_CODE_CHARS

# 메트릭 정의
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP request count",
    ["method", "endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# 2. FastAPI 앱 초기화
app = FastAPI(
    title="AI Document System API",
    description="AI 기반 계획서 생성 및 결재 시스템 백엔드 API",
    version="1.0.0",
)

# 3. CORS 설정 (프론트엔드 도메인 허용)
# 프로덕션 도메인과 로컬 개발 환경만 허용합니다.
_ALLOWED_ORIGINS = [
    "https://www.dndn.cloud",
    "https://dndn.cloud",
    "https://www.dndnhr.cloud",
    "https://dndnhr.cloud",
    "http://localhost:3000",   # 로컬 개발
    "http://localhost:5173",   # Vite 기본 포트
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 메트릭 미들웨어
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    route = request.scope.get("route")
    endpoint = route.path if (route and getattr(route, "path", None)) else "unmatched_route"
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status=response.status_code,
    ).inc()
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=endpoint,
    ).observe(duration)
    return response


# /metrics 엔드포인트 (trailing slash 포함 마운트로 307 리다이렉트 방지)
app.mount("/metrics/", make_asgi_app())

# 4. 라우터 등록 — /api prefix 아래에 묶음
#    프론트엔드가 /api/auth/login 등으로 호출하고,
#    프로덕션 ALB도 /api prefix를 그대로 전달하므로 일치시킴
api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(dashboard.router)
api.include_router(documents.router)
api.include_router(org.router)
api.include_router(github.router)
api.include_router(report_settings.router)
api.include_router(reports.router)
api.include_router(workspaces.router)
api.include_router(hr_users.router)
api.include_router(hr_departments.router)
api.include_router(hr_company.router)
api.include_router(admin_companies.router)
api.include_router(slack.router)
app.include_router(api)

# 내부 서비스 간 통신 — /api prefix 없이 등록 (ALB Ingress /api 경로에 노출 안 됨)
app.include_router(internal.router)


# 💡 1. 우리가 발생시키는 모든 HTTPException을 가로채서 공통 포맷으로 변경
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # exc.detail 에 우리가 넣은 에러 코드(예: "MISSING_TARGET")가 들어있습니다.
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": str(exc.detail),
                "message": "요청 처리 중 오류가 발생했습니다.",  # 필요에 따라 상세 메시지 매핑 가능
            },
        },
    )


# 💡 2. Pydantic 유효성 검사 에러(필수값 누락 등)도 가로채서 공통 포맷으로 변경
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "입력값이 올바르지 않습니다.",
            },
        },
    )


# 5. 서버 상태 확인용 (Health Check)
@app.get("/", tags=["System"])
async def root():
    return {"message": "AI Document System API Server is Running!"}


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok"}
