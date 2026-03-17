from .ai_generator import generate_work_plan
from .database import get_db
from .schemas import *


def create_job(workspace_id: str, job_id: str) -> str:

    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO report_jobs (job_id, workspace_id, status)
            VALUES (%s, %s, 'pending')
            """,
            (job_id, workspace_id),
        )
    conn.commit()
    conn.close()


def get_job(job_id: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT job_id, workspace_id, status
            FROM report_jobs
            WHERE job_id=%s
            """,
            (job_id,),
        )
        job = cur.fetchone()
    conn.close()

    return job


def update_job_status(job_id: str, status: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE report_jobs
            SET status=%s
            WHERE job_id=%s
            """,
            (status, job_id),
        )
    conn.commit()
    conn.close()
