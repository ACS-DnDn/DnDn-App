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
from apps.report.src.database import Base


class ReportJob(Base):
    __tablename__ = "report_jobs"

    job_id = Column(String(36), primary_key=True, index=True)
    workspace_id = Column(String(100), nullable=False, index=True)

    status = Column(String(20), nullable=False)

    document_id = Column(String(36), nullable=True)
    content_url = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    work_date = Column(String(50), nullable=True)

    files = Column(JSON, nullable=True)

    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
