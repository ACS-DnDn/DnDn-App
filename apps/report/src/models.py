from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    JSON,
    Date,
    Enum,
)
from sqlalchemy.sql import func
import uuid
import enum

from apps.report.src.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class JobType(str, enum.Enum):
    plan = "plan"
    terraform = "terraform"


class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(String(50), primary_key=True)


class User(Base):
    __tablename__ = "users"
    id = Column(String(50), primary_key=True)
    email = Column(String(255), nullable=True)


class ReportJob(Base):
    __tablename__ = "report_jobs"

    job_id = Column(String(36), primary_key=True, index=True)
    workspace_id = Column(String(100), nullable=False, index=True)

    status = Column(String(20), nullable=False)

    job_type = Column(Enum(JobType), nullable=False)
    document_id = Column(String(36), nullable=True)
    content_url = Column(Text, nullable=True)
    title = Column(String(255), nullable=True)
    work_date = Column(String(50), nullable=True)

    files = Column(JSON, nullable=True)

    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


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
