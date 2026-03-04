from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.api.database import engine
from apps.api.models import Base
from apps.routers import auth, dashboard, documents

# 1. MariaDB에 테이블 자동 생성 (models.py에 정의된 규격대로)
# 주의: 이미 테이블이 있으면 덮어쓰지 않습니다. (실무에서는 Alembic 같은 마이그레이션 툴 사용)
Base.metadata.create_all(bind=engine)

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. 라우터 등록 (여기서 URL들이 합쳐집니다)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(documents.router)


# 5. 서버 상태 확인용 (Health Check)
@app.get("/", tags=["System"])
async def root():
    return {"message": "AI Document System API Server is Running!"}
