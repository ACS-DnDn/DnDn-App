from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import ReportJob, JobType


def create_job(workspace_id: str, job_id: str) -> None:
    db = SessionLocal()
    try:
        job = ReportJob(
            job_id=job_id,
            workspace_id=workspace_id,
            status="pending",
            job_type=JobType.plan,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()


def get_job(db: Session, job_id: str) -> ReportJob | None:
    return db.query(ReportJob).filter(ReportJob.job_id == job_id).first()


def update_job_status(job_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(ReportJob).filter(ReportJob.job_id == job_id).first()
        if job:
            job.status = status
            db.commit()
    finally:
        db.close()
