from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# MariaDB 연결 URL (사용자, 암호, 호스트, DB이름 수정 필요)
# pymysql 드라이버를 사용합니다.
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://aiuser:aipassword@localhost:3306/aiproject"

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
