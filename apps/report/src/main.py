from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from typing import Any
import os
import re
import json
import asyncio
import logging
import boto3
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
from .terraform_generator import generate_terraform_code, _run_checkov_scan, _load_opa_policies
from .s3_client import (
    save_result,
    save_report,
    save_report_html,
    get_presigned_url,
    get_html,
    list_reports,
    get_report,
    save_terraform_files,
)
from .makejob import create_job, get_job
from .models import ReportJob, Document, JobType, Workspace, User, Attachment
from .database import SessionLocal, get_db, Base, engine

logger = logging.getLogger(__name__)

# 테이블 자동 생성 (Attachment 등 신규 모델 반영)
Base.metadata.create_all(bind=engine)

# ── 문서번호 타입 매핑 ──────────────────────────────────────
DOC_TYPE_CODE = {
    "계획서": "PLN",
    "이벤트보고서": "EVT",
    "헬스이벤트보고서": "RPT",
    "주간보고서": "RPT",
}


def _next_doc_num(db: Session, doc_type: str) -> str:
    """연도-종류-일련번호 형식의 문서번호 채번 (예: 2026-PLN-0001).

    CAST(suffix AS INTEGER)로 최댓값을 구해 10000번 이후 정렬 오류를 방지한다.
    """
    from sqlalchemy import cast, Integer

    code = DOC_TYPE_CODE.get(doc_type, "DOC")
    year = datetime.now(timezone.utc).year
    prefix = f"{year}-{code}-"

    suffix_expr = sa_func.substr(Document.doc_num, len(prefix) + 1)
    max_seq = (
        db.query(sa_func.max(cast(suffix_expr, Integer)))
        .filter(Document.doc_num.like(f"{prefix}%"))
        .scalar()
    )
    seq = (max_seq or 0) + 1
    return f"{prefix}{seq:04d}"

_TITLE_RE = re.compile(r'<div\s+class="doc-header-title">\s*(.+?)\s*</div>', re.DOTALL)


def _extract_title_from_html(html: str, fallback: str) -> str:
    """생성된 HTML에서 doc-header-title 텍스트를 추출."""
    m = _TITLE_RE.search(html)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title:
            return title
    return fallback


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

_background_tasks: set[asyncio.Task] = set()

app = FastAPI(title="DnDn Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_work_plan(job_id: str, req: WorkPlanRequest, ctx: dict):
    db = SessionLocal()
    try:
        job = db.query(ReportJob).filter(ReportJob.job_id == job_id).first()
        if not job:
            return

        job.status = "generating"
        db.commit()

        doc_type = "계획서"
        # doc_num은 상신 시점에 채번 (미상신 문서가 번호를 소모하지 않도록)

        # 담당자 정보
        author_label = req.author_name or ""
        if req.author_position:
            author_label = f"{author_label} {req.author_position}".strip()

        doc_meta = {
            "doc_num": "",
            "author_label": author_label,
            "company_logo_url": req.company_logo_url or "",
        }

        html = generate_work_plan(req.target, req.content, ctx, doc_meta=doc_meta)

        doc_id = f"plan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        workspace_id = req.workspace_id or "default"

        canonical = {"target": req.target, "content": req.content, **ctx}
        json_key = save_report(doc_id, canonical, workspace_id)

        html_key = save_report_html(doc_id, html, workspace_id)
        content_url = get_presigned_url(html_key)

        # HTML에서 제목 추출 (AI가 생성한 실제 문서 제목)
        title = _extract_title_from_html(html, req.target or doc_id)

        doc = Document(
            id=doc_id,
            doc_num=None,
            title=title,
            type=doc_type,
            html_key=html_key,
            json_key=json_key,
            ref_doc_ids=req.ref_doc_ids or None,
            workspace_id=workspace_id,
            author_id=req.author_id or None,
            status="draft",
        )
        db.add(doc)
        db.flush()  # FK 제약 충족을 위해 Document 먼저 flush

        # 근거자료 첨부 — AI 생성 입력 데이터
        canonical_json_bytes = json.dumps(canonical, ensure_ascii=False).encode("utf-8")
        canonical_size_kb = max(1, len(canonical_json_bytes) // 1024)
        db.add(Attachment(
            id=f"{doc_id}-canonical",
            document_id=doc_id,
            original_name="작업계획_요청데이터.json",
            file_path=json_key,
            size_kb=canonical_size_kb,
        ))

        job.status = "done"
        job.document_id = doc_id
        job.content_url = content_url
        job.title = title
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


def _run_terraform_job(job_id: str, req: TerraformRequest, repo: str, token: str | None = None):

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
        result = generate_terraform_code(workplan, repo, token, workspace_id=req.workspace_id, deploy_log=req.deploy_log)

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
    from .ai_generator import _MAX_REF_DOCS

    merged: dict[str, Any] = {}
    merged_count = 0
    for doc_id in ref_doc_ids:
        if merged_count >= _MAX_REF_DOCS:
            break
        try:
            merged.update(await asyncio.to_thread(get_report, doc_id, workspace_id))
            merged_count += 1
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

    evt_doc_num = _next_doc_num(db, "이벤트보고서")
    evt_meta = {"doc_num": evt_doc_num, "author_label": "DnDn Agent"}

    try:
        html = await asyncio.to_thread(generate_event_report, canonical, doc_meta=evt_meta)
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
    evt_title = _extract_title_from_html(html, req.target or doc_id)
    doc = Document(
        id=doc_id,
        doc_num=evt_doc_num,
        title=evt_title,
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

    health_doc_num = _next_doc_num(db, "헬스이벤트보고서")
    health_meta = {"doc_num": health_doc_num, "author_label": "DnDn Agent"}

    try:
        html = await asyncio.to_thread(generate_health_event_report, canonical, doc_meta=health_meta)
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
    health_title = _extract_title_from_html(html, req.target or doc_id)
    doc = Document(
        id=doc_id,
        doc_num=health_doc_num,
        title=health_title,
        type="헬스이벤트보고서",
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

    weekly_doc_num = _next_doc_num(db, "주간보고서")
    weekly_meta = {"doc_num": weekly_doc_num, "author_label": "DnDn Agent"}

    try:
        html = await asyncio.to_thread(generate_weekly_report, canonical, doc_meta=weekly_meta)
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
    weekly_title = _extract_title_from_html(html, req.target or doc_id)
    doc = Document(
        id=doc_id,
        doc_num=weekly_doc_num,
        title=weekly_title,
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
@app.post("/report-api/documents/generate/plan", status_code=202)
async def work_plan(req: WorkPlanRequest):

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
@app.post("/report-api/documents/generate/terraform", status_code=202)
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

    # 2. 워크스페이스에서 GitHub 정보 조회
    workspace = db.query(Workspace).filter(Workspace.id == req.workspace_id).first()
    if not workspace:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_WORKSPACE",
                    "message": "워크스페이스를 찾을 수 없습니다.",
                },
            },
        )

    repo = req.repo_name or (
        f"{workspace.github_org}/{workspace.repo}"
        if workspace.github_org and workspace.repo
        else GITHUB_REPO
    )
    if not repo:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": {
                    "code": "AI_UNAVAILABLE",
                    "message": "워크스페이스에 GitHub 저장소가 설정되지 않았습니다.",
                },
            },
        )

    # GitHub 토큰: 요청 > 워크스페이스 소유자 > 환경변수
    token = req.github_token
    if not token and workspace.owner_id:
        owner = db.query(User).filter(User.id == workspace.owner_id).first()
        if owner:
            token = owner.github_access_token
    if not token:
        token = GITHUB_TOKEN

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
    task = asyncio.create_task(asyncio.to_thread(_run_terraform_job, job_id, req, repo, token))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # 5. 즉시 반환
    return {"success": True, "data": {"jobId": job_id, "status": "pending"}}


# ─────────────────폴링─────────────────
@app.get("/report-api/documents/generate/{job_id}")
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
        html_content = None
        if job.document_id:
            html_key = f"{job.workspace_id}/reports/{job.document_id}.html"
            try:
                html_content = await asyncio.to_thread(get_html, html_key)
            except Exception:
                pass
        data["result"] = {
            "documentId": job.document_id,
            "contentUrl": job.content_url,
            "htmlContent": html_content,
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


# ── Checkov CLI 직접 실행 (MCP 불필요) ────────────────────────
def _run_checkov_cli(files_list: list[dict]) -> dict:
    """Checkov CLI를 직접 실행하여 보안 스캔 수행"""
    import tempfile, subprocess as sp
    if not files_list:
        return {}
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files_list:
            safe_name = os.path.basename(f.get("filename", "main.tf"))
            if not safe_name.endswith(".tf"):
                safe_name += ".tf"
            with open(os.path.join(tmpdir, safe_name), "w") as fp:
                fp.write(f.get("content", ""))
        try:
            result = sp.run(
                ["/app/.venv/bin/checkov", "-d", tmpdir, "--framework", "terraform", "-o", "json", "--quiet", "--compact"],
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout.strip()
            if not output:
                logger.warning("Checkov 출력 없음 (exit=%d): %s", result.returncode, result.stderr[:500])
                return {}
            parsed = json.loads(output)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
            summary = parsed.get("summary", {})
            return {
                "summary": {"passed": summary.get("passed", 0), "failed": summary.get("failed", 0)},
                "failed_checks": parsed.get("results", {}).get("failed_checks", []),
            }
        except sp.TimeoutExpired:
            logger.warning("Checkov 타임아웃 (120s)")
            return {"error": "timeout"}
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Checkov 결과 파싱 실패: %s", e)
            return {}


# ── Terraform 검증 (Checkov + OPA) ─────────────────────────
@app.post("/report-api/documents/generate/terraform/validate")
async def terraform_validate(req: dict):
    files_map = req.get("files", {})
    workspace_id = req.get("workspaceId", "default")

    files_list = [{"filename": k, "content": v} for k, v in files_map.items()]

    # Checkov 스캔 (CLI 직접 실행)
    checkov_passed = True
    checkov_issues = []
    summary = {}
    try:
        checkov_raw = await asyncio.to_thread(_run_checkov_cli, files_list)
        failed_checks = checkov_raw.get("failed_checks", [])
        summary = checkov_raw.get("summary", {})
        checkov_passed = summary.get("failed", 0) == 0
        checkov_issues = [
            {
                "id": c.get("check_id", ""),
                "resource": c.get("resource", ""),
                "file": c.get("file_path", ""),
                "line": c.get("file_line_range", [0])[0] if c.get("file_line_range") else 0,
                "severity": c.get("severity", ""),
            }
            for c in failed_checks
        ]
    except Exception as e:
        logger.warning("Checkov 스캔 실패 (계속 진행): %s", e, exc_info=True)

    # OPA 정책 검증 (실제 OPA 엔진)
    opa_blocks, opa_warns = [], []
    try:
        from .opa_engine import evaluate_opa_policies
        logger.info("OPA 검증 시작 — workspace_id=%s", workspace_id)
        opa_policies = await asyncio.to_thread(_load_opa_policies, workspace_id)
        logger.info("OPA 정책 로드: %d개 카테고리", len(opa_policies))
        if opa_policies:
            active_count = sum(
                1 for cat in opa_policies for it in cat.get("items", []) if it.get("on")
            )
            logger.info("OPA 활성 정책: %d개", active_count)
        opa_blocks, opa_warns = await asyncio.to_thread(
            evaluate_opa_policies, files_map, opa_policies
        )
        logger.info("OPA 결과: blocks=%d, warns=%d", len(opa_blocks), len(opa_warns))
    except Exception as e:
        logger.warning("OPA 평가 실패 (계속 진행): %s", e, exc_info=True)

    opa_passed = len(opa_blocks) == 0
    opa_summary_parts = []
    if opa_blocks:
        opa_summary_parts.append(f"차단 {len(opa_blocks)}건")
    if opa_warns:
        opa_summary_parts.append(f"경고 {len(opa_warns)}건")

    return {
        "success": True,
        "data": {
            "checkov": {
                "passed": checkov_passed,
                "summary": f"passed: {summary.get('passed', 0)}, failed: {summary.get('failed', 0)}",
                "issues": checkov_issues,
            },
            "opa": {
                "passed": opa_passed,
                "summary": ", ".join(opa_summary_parts) if opa_summary_parts else "정책 준수",
                "blocks": opa_blocks,
                "warns": opa_warns,
            },
        },
    }


# ── 문서 HTML 저장 (편집 후 S3 덮어쓰기) ─────────────────────
@app.put("/report-api/documents/html/save")
async def document_html_save(req: dict, db: Session = Depends(get_db)):
    doc_id = req.get("docId")
    html = req.get("html")

    if not doc_id or not html:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": {"code": "INVALID_PARAMS", "message": "docId, html은 필수입니다."}},
        )

    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": {"code": "NOT_FOUND", "message": "문서를 찾을 수 없습니다."}},
        )

    workspace_id = doc.workspace_id or "default"

    try:
        html_key = await asyncio.to_thread(save_report_html, doc_id, html, workspace_id)
        if doc.html_key != html_key:
            doc.html_key = html_key
            db.commit()
        return {"success": True, "data": {"html_key": html_key}}
    except Exception as e:
        logger.error("document html save 실패: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": {"code": "SAVE_FAILED", "message": "문서 HTML 저장에 실패했습니다."}},
        )


# ── Terraform 코드 저장 (수정 후 S3 덮어쓰기) ─────────────
@app.put("/report-api/documents/generate/terraform/save")
async def terraform_save(req: dict):
    workspace_id = req.get("workspaceId")
    job_id = req.get("jobId")
    files_map = req.get("files", {})

    if not workspace_id or not job_id:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": {"code": "INVALID_PARAMS", "message": "workspaceId와 jobId는 필수입니다."}},
        )

    if not files_map:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": {"code": "NO_FILES", "message": "저장할 파일이 없습니다."}},
        )

    files_list = [{"filename": k, "content": v} for k, v in files_map.items()]
    try:
        prefix = await asyncio.to_thread(save_terraform_files, workspace_id, job_id, files_list)
        return {"success": True, "data": {"prefix": prefix}}
    except Exception as e:
        logger.error("terraform save 실패: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": {"code": "SAVE_FAILED", "message": "Terraform 코드 저장에 실패했습니다."}},
        )


# ── Terraform 자동 수정 ────────────────────────────────────
@app.post("/report-api/documents/generate/terraform/fix")
async def terraform_fix(req: dict):
    files_map = req.get("files", {})
    checkov_issues = req.get("checkovIssues", [])
    opa_blocks = req.get("opaBlocks", [])
    opa_warns = req.get("opaWarns", [])

    issues_text = ""
    if checkov_issues:
        issues_text += "\n## Checkov 보안 이슈\n"
        for issue in checkov_issues:
            issues_text += f"- {issue.get('id', '')}: {issue.get('resource', '')} ({issue.get('file', '')}:{issue.get('line', '')})\n"
    if opa_blocks:
        issues_text += "\n## OPA 정책 위반 (차단)\n"
        for b in opa_blocks:
            detail = f" — {b['detail']}" if b.get('detail') else ""
            issues_text += f"- [차단] {b.get('label', '')}{detail}\n"
    if opa_warns:
        issues_text += "\n## OPA 정책 경고\n"
        for w in opa_warns:
            detail = f" — {w['detail']}" if w.get('detail') else ""
            issues_text += f"- [경고] {w.get('label', '')}{detail}\n"

    files_text = ""
    for fname, code in files_map.items():
        files_text += f"\n# === {fname} ===\n{code}\n"

    from .terraform_generator import MODEL_ID, REGION

    client = boto3.client("bedrock-runtime", region_name=REGION)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "system": (
            "당신은 Terraform 보안 전문가입니다. "
            "아래 Terraform 코드에서 보안/정책 이슈를 수정하세요. "
            "반드시 JSON만 출력하세요. 설명, 주석, 마크다운 코드펜스 없이 순수 JSON만 반환하세요. "
            '형식: {"files": {"파일명.tf": "수정된 전체 코드", ...}}'
        ),
        "messages": [{"role": "user", "content": f"## 현재 코드\n{files_text}\n{issues_text}\n위 이슈를 모두 수정한 전체 코드를 순수 JSON으로만 반환하세요. 설명 없이 JSON만 출력."}],
    }

    logger.info("terraform fix 시작 — 파일 %d개, 이슈: checkov=%d, opa_block=%d, opa_warn=%d",
                len(files_map), len(checkov_issues), len(opa_blocks), len(opa_warns))
    try:
        response = await asyncio.to_thread(
            client.invoke_model,
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        logger.info("terraform fix Bedrock 응답 길이: %d자", len(text))
        clean = re.sub(r'^```\w*\n?', '', text.strip())
        clean = re.sub(r'\n?```$', '', clean).strip()
        # Bedrock가 JSON 뒤에 설명을 붙이는 경우 — 첫 번째 JSON 객체만 추출
        brace_count = 0
        json_end = 0
        for idx, ch in enumerate(clean):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = idx + 1
                    break
        if json_end > 0:
            clean = clean[:json_end]
        fixed = json.loads(clean, strict=False)
        fixed_files = fixed.get("files", {})
        if not fixed_files:
            logger.warning("terraform fix: Bedrock가 빈 files 반환. 원문: %s", clean[:300])
        return {"success": True, "data": {"files": fixed_files}}
    except Exception as e:
        logger.error("terraform fix 실패: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": {"code": "FIX_FAILED", "message": f"자동 수정 실패: {type(e).__name__}: {str(e)[:200]}"}},
        )


@app.get("/health")
async def health():
    return {"ok": True}
