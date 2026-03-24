from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Any
import os
import asyncio
import logging
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
from .terraform_generator import generate_terraform_code, _run_checkov_scan, _load_opa_policies, _format_opa_for_prompt
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
from .models import ReportJob, Document, JobType, Workspace, User
from .database import SessionLocal, get_db

logger = logging.getLogger(__name__)

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


# ── Terraform 검증 (Checkov + OPA) ─────────────────────────
@app.post("/report-api/documents/generate/terraform/validate")
async def terraform_validate(req: dict):
    files_map = req.get("files", {})
    workspace_id = req.get("workspaceId", "default")

    files_list = [{"filename": k, "content": v} for k, v in files_map.items()]

    # Checkov 스캔
    checkov_raw = await asyncio.to_thread(_run_checkov_scan, files_list)
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

    # OPA 정책 검증
    opa_policies = _load_opa_policies(workspace_id)
    opa_blocks = []
    opa_warns = []
    all_code = "\n".join(files_map.values()).lower()

    for category in opa_policies:
        for item in category.get("items", []):
            if not item.get("on"):
                continue
            severity = item.get("severity", "warn")
            label = item.get("label", "")
            params = item.get("params")

            violated = False
            if params and params.get("type") == "list":
                allowed = [v.lower() for v in params.get("values", [])]
                if allowed:
                    key = item.get("key", "")
                    if "region" in key and not any(r in all_code for r in allowed):
                        violated = True
            if params and params.get("type") == "services":
                services = [s.lower() for s in params.get("values", [])]
                if services:
                    for svc in services:
                        if svc in all_code:
                            violated = True
                            break

            if violated:
                entry = {"key": item.get("key", ""), "label": label}
                if severity == "block":
                    opa_blocks.append(entry)
                else:
                    opa_warns.append(entry)

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
            issues_text += f"- [차단] {b.get('label', '')}\n"
    if opa_warns:
        issues_text += "\n## OPA 정책 경고\n"
        for w in opa_warns:
            issues_text += f"- [경고] {w.get('label', '')}\n"

    files_text = ""
    for fname, code in files_map.items():
        files_text += f"\n# === {fname} ===\n{code}\n"

    from .terraform_generator import MODEL_ID, REGION
    import boto3, json as _json

    client = boto3.client("bedrock-runtime", region_name=REGION)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "system": (
            "당신은 Terraform 보안 전문가입니다. "
            "아래 Terraform 코드에서 보안/정책 이슈를 수정하세요. "
            "수정된 전체 코드를 JSON으로 반환하세요. "
            '형식: {"files": {"파일명.tf": "수정된 전체 코드", ...}}'
        ),
        "messages": [{"role": "user", "content": f"## 현재 코드\n{files_text}\n{issues_text}\n위 이슈를 모두 수정한 전체 코드를 JSON으로 반환하세요."}],
    }

    try:
        response = await asyncio.to_thread(
            client.invoke_model,
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=_json.dumps(body),
        )
        result = _json.loads(response["body"].read())
        text = result["content"][0]["text"]
        clean = text.strip().removeprefix("```json").removesuffix("```").strip()
        fixed = _json.loads(clean, strict=False)
        fixed_files = fixed.get("files", {})
        return {"success": True, "data": {"files": fixed_files}}
    except Exception as e:
        logger.error("terraform fix 실패: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": {"code": "FIX_FAILED", "message": str(e)}},
        )


@app.get("/health")
async def health():
    return {"ok": True}
