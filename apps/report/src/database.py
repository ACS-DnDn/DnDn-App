import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# MariaDB 연결 URL은 환경변수 `SQLALCHEMY_DATABASE_URL`에서 주입합니다.
# 예시 값은 .env.example 등에만 두고, 실제 비밀정보는 커밋하지 않습니다.
SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise RuntimeError(
        "환경변수 'SQLALCHEMY_DATABASE_URL'이 설정되지 않았습니다. "
        "DB 연결 문자열을 환경변수로 설정해 주세요."
    )

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# DB 세션 의존성 주입 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
