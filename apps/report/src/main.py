from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from prometheus_client import Counter, Histogram, make_asgi_app
from typing import Any
import os
import asyncio
import logging
import time
from functools import partial
from datetime import datetime, timezone
import uuid

from dotenv import load_dotenv

load_dotenv()

from .schemas import (
    ReportRequest,
    WorkPlanRequest,
    TerraformRequest,
    SaveRequest,
    RenderRequest,
    WeeklyReportRequest,
)
from .ai_generator import (
    generate_event_report,
    generate_weekly_report,
    generate_work_plan,
    generate_health_event_report,
)
from .terraform_generator import generate_terraform_code
from .s3_client import (
    save_result,
    save_report,
    save_report_html,
    get_presigned_url,
    list_reports,
    get_report,
    save_terraform_files,
)
from .makejob import create_job, get_job
from .models import ReportJob, Document, JobType
from .database import SessionLocal, get_db

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

_raw_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

_background_tasks: set[asyncio.Task] = set()

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

app = FastAPI(title="DnDn Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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


def _run_work_plan(job_id: str, req: WorkPlanRequest, ctx: dict):
    db = SessionLocal()
    try:
        job = db.query(ReportJob).filter(ReportJob.job_id == job_id).first()
        if not job:
            return

        job.status = "generating"
        db.commit()

        html = generate_work_plan(req.target, req.content, ctx)

        doc_id = f"plan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        workspace_id = req.workspace_id or "default"

        canonical = {"target": req.target, "content": req.content, **ctx}
        json_key = save_report(doc_id, canonical, workspace_id)

        html_key = save_report_html(doc_id, html, workspace_id)
        content_url = get_presigned_url(html_key)

        doc = Document(
            id=doc_id,
            title=req.target or doc_id,
            type="계획서",
            html_key=html_key,
            json_key=json_key,
            ref_doc_ids=req.ref_doc_ids or None,
            workspace_id=workspace_id,
            status="done",
        )
        db.add(doc)

        job.status = "done"
        job.document_id = doc_id
        job.content_url = content_url
        job.title = req.target
        db.commit()

    except Exception as e:
        logger.error("work_plan AI 생성 오류: %s", e, exc_info=True)
        job = db.query(ReportJob).filter(ReportJob.job_id == job_id).first()
        if job:
            job.status = "failed"
            job.error_code = "AI_UNAVAILABLE"
            job.error_message = str(e)
            db.commit()

    finally:
        db.close()


def _run_terraform_job(job_id: str, req: TerraformRequest, repo: str):

    db = SessionLocal()

    try:
        job = db.query(ReportJob).filter(ReportJob.job_id == job_id).first()

        if not job:
            return

        # 상태 변경
        job.status = "generating"
        db.commit()

        # 1. workplan 조회 (plan 생성 시 저장한 canonical JSON)
        workplan = get_report(req.document_id, req.workspace_id or "default")

        # 2. Terraform 생성
        token = req.github_token or GITHUB_TOKEN

        result = generate_terraform_code(workplan, repo, token, workspace_id=req.workspace_id)

        # result = { "main.tf": "...", "vars.tf": "..." }

        # 3. terraform 파일 S3 저장
        tf_files = result.get("files", [])
        terraform_key = save_terraform_files(req.workspace_id, job_id, tf_files)

        # 4. Document.terraform_key 업데이트
        doc = db.query(Document).filter(Document.id == req.document_id).first()
        if doc:
            doc.terraform_key = terraform_key

        # 5. 성공 처리
        job.status = "done"
        job.files = result

        db.commit()

    except Exception as e:
        logger.error("terraform job 실패: %s", e, exc_info=True)

        job = db.query(ReportJob).filter(ReportJob.job_id == job_id).first()

        if job:
            job.status = "failed"
            job.error_code = "AI_UNAVAILABLE"
            job.error_message = str(e)
            db.commit()

    finally:
        db.close()


async def _merge_context(ref_doc_ids: list[str], workspace_id: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for doc_id in ref_doc_ids:
        try:
            merged.update(await asyncio.to_thread(get_report, doc_id, workspace_id))
        except Exception:
            pass
    return merged


# ── 이벤트 보고서 ──────────────────────────────────────────
@app.post("/api/report/event")
async def event_report(req: ReportRequest, db: Session = Depends(get_db)):
    doc_id = f"event-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    ctx = await _merge_context(req.ref_doc_ids, req.workspace_id)
    canonical = {
        "meta": {
            "type": "EVENT",
            "title": req.target,
            "workspace_id": req.workspace_id,
        },
        "content": req.content,
        **ctx,
    }

    try:
        json_key = await asyncio.to_thread(
            save_report, doc_id, canonical, req.workspace_id
        )
    except Exception as e:
        logger.error("event_report: JSON 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="보고서 저장 실패")

    try:
        html = await asyncio.to_thread(generate_event_report, canonical)
    except Exception as e:
        logger.error("event_report: AI 생성 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="AI 보고서 생성 실패")

    try:
        html_key = await asyncio.to_thread(
            save_report_html, doc_id, html, req.workspace_id
        )
        html_url = await asyncio.to_thread(get_presigned_url, html_key)
    except Exception as e:
        logger.error("event_report: HTML 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="HTML 저장 실패")

    doc = Document(
        id=doc_id,
        title=req.target or doc_id,
        type="이벤트보고서",
        html_key=html_key,
        json_key=json_key,
        ref_doc_ids=req.ref_doc_ids or None,
        workspace_id=req.workspace_id,
        status="done",
    )
    db.add(doc)
    db.commit()

    return {"success": True, "data": {"doc_id": doc_id, "html_url": html_url}}


# ── Health 이벤트 보고서 ───────────────────────────────────
@app.post("/api/report/health-event")
async def health_event_report(req: ReportRequest, db: Session = Depends(get_db)):
    doc_id = f"event-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    ctx = await _merge_context(req.ref_doc_ids, req.workspace_id)
    canonical = {
        "meta": {
            "type": "HEALTH",
            "title": req.target,
            "workspace_id": req.workspace_id,
        },
        "content": req.content,
        **ctx,
    }

    try:
        json_key = await asyncio.to_thread(
            save_report, doc_id, canonical, req.workspace_id
        )
    except Exception as e:
        logger.error("health_event_report: JSON 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="보고서 저장 실패")

    try:
        html = await asyncio.to_thread(generate_health_event_report, canonical)
    except Exception as e:
        logger.error("health_event_report: AI 생성 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="AI 보고서 생성 실패")

    try:
        html_key = await asyncio.to_thread(
            save_report_html, doc_id, html, req.workspace_id
        )
        html_url = await asyncio.to_thread(get_presigned_url, html_key)
    except Exception as e:
        logger.error("health_event_report: HTML 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="HTML 저장 실패")

    doc = Document(
        id=doc_id,
        title=req.target or doc_id,
        type="이벤트보고서",
        html_key=html_key,
        json_key=json_key,
        ref_doc_ids=req.ref_doc_ids or None,
        workspace_id=req.workspace_id,
        status="done",
    )
    db.add(doc)
    db.commit()

    return {"success": True, "data": {"doc_id": doc_id, "html_url": html_url}}


# ── 주간 보고서 ────────────────────────────────────────────
@app.post("/api/report/weekly")
async def weekly_report(req: WeeklyReportRequest, db: Session = Depends(get_db)):
    doc_id = f"weekly-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    ctx = await _merge_context(req.ref_doc_ids, req.workspace_id)
    ctx_meta = ctx.get("meta", {})

    canonical = {
        "meta": {
            **ctx_meta,  # canonical_summary의 account_id, time_range 등 보존
            # 요청 필드가 ctx_meta를 덮어씀
            "type": "WEEKLY",
            "run_id": doc_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workspace_id": req.workspace_id,
            "period": {"start": req.period_start, "end": req.period_end},
            "title": req.target,
        },
        "content": req.content,
        **{k: v for k, v in ctx.items() if k != "meta"},
    }

    try:
        json_key = await asyncio.to_thread(
            save_report, doc_id, canonical, req.workspace_id
        )
    except Exception as e:
        logger.error("weekly_report: JSON 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="보고서 저장 실패")

    try:
        html = await asyncio.to_thread(generate_weekly_report, canonical)
    except Exception as e:
        logger.error("weekly_report: AI 생성 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="AI 보고서 생성 실패")

    try:
        html_key = await asyncio.to_thread(
            save_report_html, doc_id, html, req.workspace_id
        )
        html_url = await asyncio.to_thread(get_presigned_url, html_key)
    except Exception as e:
        logger.error("weekly_report: HTML 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="HTML 저장 실패")

    doc = Document(
        id=doc_id,
        title=req.target or doc_id,
        type="주간보고서",
        html_key=html_key,
        json_key=json_key,
        workspace_id=req.workspace_id,
        status="done",
    )
    db.add(doc)
    db.commit()

    return {"success": True, "data": {"doc_id": doc_id, "html_url": html_url}}


# ── 작업계획서 생성 (target + content + refDocIds → HTML) ──
@app.post("/todo/documents/generate/plan", status_code=202)
async def work_plan(req: WorkPlanRequest):

    if not req.target:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {"code": "MISSING_TARGET", "message": "target은 필수입니다."},
            },
        )
    if not req.content:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "MISSING_CONTENT",
                    "message": "content는 필수입니다.",
                },
            },
        )
    if not req.workspace_id:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_WORKSPACE",
                    "message": "workspaceId는 필수입니다.",
                },
            },
        )

    job_id = str(uuid.uuid4())
    create_job(req.workspace_id, job_id)

    ctx = await _merge_context(req.ref_doc_ids, req.workspace_id)

    task = asyncio.create_task(asyncio.to_thread(_run_work_plan, job_id, req, ctx))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"success": True, "data": {"jobId": job_id, "status": "pending"}}


# ── 테라폼 코드 생성 ───────────────────────────────────────
@app.post("/todo/documents/generate/terraform", status_code=202)
async def terraform_generate(req: TerraformRequest, db: Session = Depends(get_db)):

    # 1. documentId 검증
    if not req.document_id:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_DOCUMENT",
                    "message": "documentId는 필수입니다.",
                },
            },
        )

    if not req.workspace_id:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_WORKSPACE",
                    "message": "workspaceId는 필수입니다.",
                },
            },
        )

    # 2. repo 설정
    repo = req.repo_name or GITHUB_REPO
    if not repo:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": {
                    "code": "AI_UNAVAILABLE",
                    "message": "GITHUB_REPO가 설정되지 않았습니다.",
                },
            },
        )

    # 3. job 생성
    job_id = str(uuid.uuid4())

    job = ReportJob(
        job_id=job_id,
        workspace_id=req.workspace_id,
        status="pending",
        job_type=JobType.terraform,
        document_id=req.document_id,
    )

    db.add(job)
    db.commit()

    # 4. background 실행
    task = asyncio.create_task(asyncio.to_thread(_run_terraform_job, job_id, req, repo))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # 5. 즉시 반환
    return {"success": True, "data": {"jobId": job_id, "status": "pending"}}


# ─────────────────폴링─────────────────
@app.get("/todo/documents/generate/{job_id}")
async def get_generate_status(job_id: str, db: Session = Depends(get_db)):

    job = get_job(db, job_id)

    if not job:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {"code": "JOB_NOT_FOUND", "message": "존재하지 않는 jobId"},
            },
        )

    data = {"jobId": job.job_id, "status": job.status}

    if job.status == "done":
        data["result"] = {
            "documentId": job.document_id,
            "contentUrl": job.content_url,
            "title": job.title,
            "workDate": job.work_date,
            "files": job.files,
        }

    if job.status == "failed":
        data["error"] = {"code": job.error_code, "message": job.error_message}

    return {"success": True, "data": data}


# ── 보고서 HTML 자동 렌더 (Lambda → S3 JSON 저장 후 호출) ──────
@app.post("/api/report/render")
async def render_report(req: RenderRequest):
    """S3 canonical JSON 읽기 → AI HTML 보고서 생성 → HTML 저장 → html_key 반환"""
    try:
        canonical = await asyncio.to_thread(get_report, req.doc_id, req.workspace_id)
    except Exception as e:
        logger.error("render_report: canonical 조회 실패: %s", e, exc_info=True)
        raise HTTPException(
            status_code=404, detail="canonical JSON을 찾을 수 없습니다."
        )

    try:
        meta_type = canonical.get("meta", {}).get("type", "EVENT").upper()
        if meta_type == "WEEKLY":
            fn = partial(generate_weekly_report, canonical)
        elif meta_type == "HEALTH":
            fn = partial(generate_health_event_report, canonical)
        else:
            fn = partial(generate_event_report, canonical)
        html = await asyncio.to_thread(fn)
    except Exception as e:
        logger.error("render_report: AI 생성 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="AI 보고서 생성 실패")

    try:
        html_key = await asyncio.to_thread(
            save_report_html, req.doc_id, html, req.workspace_id
        )
        return {"ok": True, "data": {"doc_id": req.doc_id, "html_key": html_key}}
    except Exception as e:
        logger.error("render_report: HTML 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="HTML 저장 실패")


@app.get("/health")
async def health():
    return {"ok": True}
