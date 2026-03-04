from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    JSON,
    Date,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

# app/database.py 에서 만들어둔 Base 객체를 가져옵니다.
from apps.api.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# 1. 🏢 회사 테이블
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    logo_url = Column(String(255), nullable=True)

    # 역참조: 이 회사에 소속된 유저들
    users = relationship("User", back_populates="company")


# 2. 👤 유저 테이블
class User(Base):
    __tablename__ = "users"

    id = Column(String(50), primary_key=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    role = Column(String(20), default="user")

    # 👇 새로 추가되는 부분: 어떤 회사에 소속되어 있는지 연결
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="users")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship("Task", back_populates="user")
    documents = relationship("Document", back_populates="author")
    approvals = relationship("Approval", back_populates="user")


# 2. 오늘의 업무 (Tasks) 테이블
class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(String(255), nullable=False)
    status = Column(String(20), default="todo")  # "todo", "done" 등

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="tasks")


# 3. 문서 (Documents) 테이블 (계획서 포함)
class Document(Base):
    __tablename__ = "documents"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)  # HTML 본문 (길이가 길 수 있으므로 Text)

    # MariaDB의 JSON 타입 활용
    terraform = Column(JSON, nullable=True)  # {"main.tf": "..."} 저장용
    ref_doc_ids = Column(JSON, nullable=True)  # ["doc_001", "doc_002"] 저장용

    work_date = Column(Date, nullable=False)  # 작업 예정일
    is_draft = Column(Boolean, default=False)  # 임시저장 여부

    # 상태: progress(진행중), done(완료), rejected(반려), failed(실패)
    status = Column(String(20), default="progress")

    author_id = Column(String(50), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    author = relationship("User", back_populates="documents")
    approvals = relationship(
        "Approval", back_populates="document", cascade="all, delete-orphan"
    )


# 4. 결재선 (Approvals) 테이블
class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(50), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(String(50), ForeignKey("users.id"), nullable=False)

    seq = Column(Integer, nullable=False)  # 결재 순서 (1, 2, 3...)

    # 상태: wait(대기), current(현재 내 차례), approved(승인), rejected(반려)
    status = Column(String(20), default="wait")

    reject_reason = Column(Text, nullable=True)  # 반려 사유

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    document = relationship("Document", back_populates="approvals")
    user = relationship("User", back_populates="approvals")
