from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from prometheus_client import Counter, Histogram, make_asgi_app
import time
from apps.api.src.database import engine
from apps.api.src.models import Base
from apps.api.src.routers import (
    auth,
    dashboard,
    documents,
    github,
    org,
    report_settings,
    reports,
    workspaces,
    hr_users,
    hr_departments,
    slack,
)

# 1. MariaDB에 테이블 자동 생성 (models.py에 정의된 규격대로)
# 주의: 이미 테이블이 있으면 덮어쓰지 않습니다. 컬럼 추가/변경은 반영되지 않습니다.
# TODO: 운영 환경 전환 전 Alembic 마이그레이션으로 교체 필요
#       (create_all은 개발/테스트 전용으로만 사용)
Base.metadata.create_all(bind=engine)

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
# 개발 환경이므로 일단 모든 출처를 허용(*)합니다. 실무에서는 프론트 주소만 넣으세요.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 예: ["http://localhost:3000"]
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 메트릭 미들웨어
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    endpoint = request.url.path
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


# /metrics 엔드포인트
app.mount("/metrics", make_asgi_app())

# 4. 라우터 등록 (여기서 URL들이 합쳐집니다)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(documents.router)
app.include_router(org.router)
app.include_router(github.router)
app.include_router(report_settings.router)
app.include_router(reports.router)
app.include_router(workspaces.router)
app.include_router(hr_users.router)
app.include_router(hr_departments.router)
app.include_router(slack.router)


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
