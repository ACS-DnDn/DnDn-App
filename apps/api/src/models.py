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
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
import uuid

# app/database.py 에서 만들어둔 Base 객체를 가져옵니다.
from apps.api.src.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# 0. 🏗️ 부서 테이블 (자기참조 트리)
class Department(Base):
    __tablename__ = "departments"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    parent_id = Column(String(50), ForeignKey("departments.id"), nullable=True)
    leader_id = Column(String(50), ForeignKey("users.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    children = relationship(
        "Department", backref=backref("parent", remote_side="Department.id")
    )
    leader = relationship("User", foreign_keys=[leader_id], lazy="joined")


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
    cognito_sub = Column(
        String(50), unique=True, nullable=True, index=True
    )  # Cognito sub (첫 로그인 시 채워짐)
    email = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    role = Column(String(20), default="member")  # hr | leader | member
    employee_no = Column(String(20), nullable=True)  # 사번
    position = Column(String(50), nullable=True)  # 직급

    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="users")

    department_id = Column(String(50), ForeignKey("departments.id"), nullable=True)
    department = relationship("Department", foreign_keys=[department_id])

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Slack 연동
    slack_user_id = Column(String(50), nullable=True)
    slack_access_token = Column(Text, nullable=True)
    slack_workspace = Column(String(100), nullable=True)
    slack_channel = Column(String(100), nullable=True)
    slack_notify = Column(Boolean, nullable=True)

    documents = relationship("Document", back_populates="author")
    approvals = relationship("Approval", back_populates="user")


# 3. 문서 (Documents) 테이블 (계획서 포함)
class Document(Base):
    __tablename__ = "documents"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    title = Column(String(200), nullable=False)

    # "계획서", "이벤트보고서", "헬스이벤트보고서", "주간보고서"
    type = Column(String(50), nullable=False, default="계획서")

    html_key = Column(String(500), nullable=True)  # S3 key — 렌더링된 HTML
    json_key = Column(String(500), nullable=True)  # S3 key — canonical JSON
    terraform_key = Column(String(500), nullable=True)  # S3 prefix — terraform 파일

    ref_doc_ids = Column(JSON, nullable=True)

    work_date = Column(Date, nullable=True)
    is_draft = Column(Boolean, default=False)

    status = Column(String(20), default="progress")

    workspace_id = Column(
        String(50), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    author_id = Column(String(50), ForeignKey("users.id"), nullable=True)

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
    type = Column(String(10), default="결재")  # 결재 / 협조 / 참조

    # 상태: wait(대기), current(현재 내 차례), approved(승인), rejected(반려)
    status = Column(String(20), default="wait")

    reject_reason = Column(Text, nullable=True)  # 반려 사유

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    document = relationship("Document", back_populates="approvals")
    user = relationship("User", back_populates="approvals")

    comment = Column(String(500), nullable=True)
    approval_date = Column(DateTime(timezone=True), nullable=True)


class DocumentRead(Base):
    __tablename__ = "document_reads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id = Column(
        String(50), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    read_at = Column(DateTime(timezone=True), server_default=func.now())


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String(50), primary_key=True)
    document_id = Column(
        String(50), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    # 프론트엔드에 내려줄 진짜 파일명 (예: "아키텍처_설계도.png")
    original_name = Column(String(255), nullable=False)

    # 서버나 S3에 실제로 저장된 경로/키 (예: "/uploads/2026/03/uuid-1234.png")
    file_path = Column(String(500), nullable=False)

    # 명세서에 있는 파일 크기 (KB)
    size_kb = Column(Integer, default=0)


# 6. 🏗️ 워크스페이스 테이블
class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    alias = Column(String(100), nullable=False)  # 별칭 (예: "Production")
    acct_id = Column(String(12), nullable=False)  # AWS 계정 ID (12자리)
    github_org = Column(String(100), nullable=False)  # GitHub 조직명
    repo = Column(String(200), nullable=False)  # 레포지토리명
    path = Column(String(500), nullable=True)  # 레포 내 경로 (옵션)
    branch = Column(String(200), nullable=False)  # 브랜치명
    icon = Column(String(30), nullable=False, default="rocket")  # 아이콘 키
    memo = Column(Text, nullable=True)  # 메모

    # OPA 인프라 정책 — PUT으로 전체 교체하므로 JSON 컬럼이 적합
    opa_settings = Column(JSON, nullable=True)

    # 워크스페이스 생성자 (부서장)
    owner_id = Column(String(50), ForeignKey("users.id"), nullable=False)
    owner = relationship("User")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 역참조: 이 워크스페이스의 보고서 설정
    report_settings = relationship(
        "ReportSettings", back_populates="workspace", uselist=False
    )
    report_schedules = relationship(
        "ReportSchedule", back_populates="workspace", cascade="all, delete-orphan"
    )


# 7. 📊 보고서 설정 테이블 (워크스페이스당 1개)
class ReportSettings(Base):
    __tablename__ = "report_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(
        String(50),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # 현황 보고서 설정
    repeat_enabled = Column(Boolean, default=False)  # 자동 반복 여부
    interval_hours = Column(Integer, default=168)  # 반복 주기 (시간). 168 = 1주
    last_run = Column(DateTime(timezone=True), nullable=True)  # 마지막 실행 일시

    # 이벤트 보고서 ON/OFF 설정 — {"sh-malicious-network": true, ...}
    event_settings = Column(JSON, nullable=True)

    workspace = relationship("Workspace", back_populates="report_settings")


# 8. 📅 보고서 스케줄 테이블 (워크스페이스당 여러 개)
class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(
        String(50), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )

    title = Column(String(200), nullable=False)  # 스케줄 제목
    preset = Column(String(20), nullable=False)  # daily / weekly / monthly
    day_of_week = Column(Integer, nullable=True)  # 요일 (1=월 ~ 7=일), weekly 시
    day_of_month = Column(Integer, nullable=True)  # 날짜 (1-31), monthly 시
    time = Column(String(5), nullable=False)  # 실행 시각 (HH:mm)
    include_range = Column(Boolean, default=True)  # 수집 기간 포함 여부

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="report_schedules")
