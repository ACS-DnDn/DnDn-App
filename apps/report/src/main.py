from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any
import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from functools import partial

from dotenv import load_dotenv
load_dotenv()

from .ai_generator import (
    generate_event_report,
    generate_weekly_report,
    generate_work_plan,
    generate_health_event_report,
)
from .terraform_generator import generate_terraform_code
from .s3_client import save_result, save_report, save_report_html, get_presigned_url, list_reports, get_report, get_workplan

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app = FastAPI(title="DnDn Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReportRequest(BaseModel):
    workspace_id: str = "default"
    target: str = ""
    content: str = ""
    ref_doc_ids: list[str] = []
    account_id: str = "default"


WorkPlanRequest = ReportRequest  # alias


class TerraformRequest(BaseModel):
    job_id: str | None = None
    workplan: dict[str, Any] | None = None  # 직접 전달 (하위 호환)
    repo_name: str | None = None
    github_token: str | None = None


class SaveRequest(BaseModel):
    account_id: str = "default"
    job_id: str | None = None
    html: str = ""
    terraform_files: list[dict[str, str]] = []


class RenderRequest(BaseModel):
    doc_id: str
    account_id: str = "default"


async def _merge_context(ref_doc_ids: list[str], account_id: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for doc_id in ref_doc_ids:
        try:
            merged.update(await asyncio.to_thread(get_report, doc_id, account_id))
        except Exception:
            pass
    return merged


# ── 보고서 목록 조회 ───────────────────────────────────────
@app.get("/api/reports")
async def list_reports_api(account_id: str = "default"):
    try:
        result = await asyncio.to_thread(list_reports, account_id)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("list_reports 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── 보고서 단건 조회 ───────────────────────────────────────
@app.get("/api/reports/{doc_id}")
async def get_report_api(doc_id: str, account_id: str = "default"):
    try:
        result = await asyncio.to_thread(get_report, doc_id, account_id)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("get_report 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")


# ── 이벤트 보고서 ──────────────────────────────────────────
@app.post("/api/report/event")
async def event_report(req: ReportRequest):
    ctx = await _merge_context(req.ref_doc_ids, req.account_id)
    try:
        html = await asyncio.to_thread(generate_event_report, req.target, req.content, ctx)
        return {"ok": True, "data": html}
    except Exception as e:
        logger.error("event_report 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── Health 이벤트 보고서 ───────────────────────────────────
@app.post("/api/report/health-event")
async def health_event_report(req: ReportRequest):
    ctx = await _merge_context(req.ref_doc_ids, req.account_id)
    try:
        html = await asyncio.to_thread(generate_health_event_report, req.target, req.content, ctx)
        return {"ok": True, "data": html}
    except Exception as e:
        logger.error("health_event_report 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── 주간 보고서 ────────────────────────────────────────────
class WeeklyReportRequest(BaseModel):
    target: str = ""
    content: str = ""
    period_start: str = ""
    period_end: str = ""
    account_id: str = "default"


@app.post("/api/report/weekly")
async def weekly_report(req: WeeklyReportRequest):
    doc_id = f"weekly-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    canonical = {
        "meta": {
            "type": "WEEKLY",
            "run_id": doc_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "account_id": req.account_id,
            "period": {"start": req.period_start, "end": req.period_end},
            "title": req.target,
        },
        "content": req.content,
    }

    try:
        await asyncio.to_thread(save_report, doc_id, canonical, req.account_id)
    except Exception as e:
        logger.error("weekly_report: JSON 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="보고서 저장 실패")

    try:
        html = await asyncio.to_thread(generate_weekly_report, req.target, req.content, canonical)
    except Exception as e:
        logger.error("weekly_report: AI 생성 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="AI 보고서 생성 실패")

    try:
        html_key = await asyncio.to_thread(save_report_html, doc_id, html, req.account_id)
        html_url = await asyncio.to_thread(get_presigned_url, html_key)
        return {"ok": True, "data": {"doc_id": doc_id, "html_url": html_url}}
    except Exception as e:
        logger.error("weekly_report: HTML 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="HTML 저장 실패")


# ── 작업계획서 생성 (target + content + refDocIds → HTML) ──
@app.post("/api/report/workplan")
async def work_plan(req: WorkPlanRequest):
    ctx = await _merge_context(req.ref_doc_ids, req.account_id)
    try:
        html = await asyncio.to_thread(generate_work_plan, req.target, req.content, ctx)
    except Exception as e:
        logger.error("work_plan AI 생성 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="계획서 생성 실패")

    try:
        meta = {"target": req.target, "content": req.content}
        result = await asyncio.to_thread(save_result, req.account_id, meta, html, [])
        return {"ok": True, "data": {**result, "html": html}}
    except Exception as e:
        logger.error("work_plan 저장 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="계획서 저장 실패")


# ── 테라폼 코드 생성 ───────────────────────────────────────
@app.post("/api/terraform/generate")
async def terraform_generate(req: TerraformRequest):
    repo = req.repo_name or GITHUB_REPO
    if not repo:
        raise HTTPException(status_code=400, detail="GITHUB_REPO 환경변수가 설정되지 않았습니다.")

    if req.job_id:
        try:
            workplan = await asyncio.to_thread(get_workplan, req.job_id)
        except Exception as e:
            logger.error("terraform: workplan 조회 실패: %s", e, exc_info=True)
            raise HTTPException(status_code=404, detail="작업계획서를 찾을 수 없습니다.")
    elif req.workplan:
        workplan = req.workplan
    else:
        raise HTTPException(status_code=400, detail="job_id 또는 workplan 중 하나는 필수입니다.")

    try:
        token = req.github_token or GITHUB_TOKEN
        fn = partial(generate_terraform_code, workplan, repo, token)
        result = await asyncio.to_thread(fn)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("terraform_generate 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


@app.post("/api/save")
async def save_to_s3(req: SaveRequest):
    try:
        result = await asyncio.to_thread(
            save_result, req.account_id, {}, req.html, req.terraform_files, req.job_id
        )
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("save 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── 보고서 HTML 자동 렌더 (Lambda → S3 JSON 저장 후 호출) ──────
@app.post("/api/report/render")
async def render_report(req: RenderRequest):
    """S3 canonical JSON 읽기 → AI HTML 보고서 생성 → HTML 저장 → html_key 반환"""
    try:
        canonical = await asyncio.to_thread(get_report, req.doc_id, req.account_id)
    except Exception as e:
        logger.error("render_report: canonical 조회 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=404, detail="canonical JSON을 찾을 수 없습니다.")

    try:
        meta_type = canonical.get("meta", {}).get("type", "EVENT")
        if meta_type == "WEEKLY":
            fn = partial(generate_weekly_report, "", "", canonical)
        else:
            fn = partial(generate_event_report, "", "", canonical)
        html = await asyncio.to_thread(fn)
    except Exception as e:
        logger.error("render_report: AI 생성 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="AI 보고서 생성 실패")

    try:
        html_key = await asyncio.to_thread(save_report_html, req.doc_id, html, req.account_id)
        return {"ok": True, "data": {"doc_id": req.doc_id, "html_key": html_key}}
    except Exception as e:
        logger.error("render_report: HTML 저장 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="HTML 저장 실패")


# ── 기존 S3 JSON으로 HTML 일괄 생성 (html 없는 것만) ──────
@app.post("/api/reports/render-pending")
async def render_pending(account_id: str = "default"):
    """S3에 JSON은 있지만 HTML이 없는 보고서를 일괄 렌더링"""
    try:
        items = await asyncio.to_thread(list_reports, account_id)
    except Exception as e:
        logger.error("render_pending: 목록 조회 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="보고서 목록 조회 실패")

    pending = [it for it in items if it.get("type") == "report" and not it.get("html_key")]
    if not pending:
        return {"ok": True, "data": {"rendered": 0, "skipped": 0}}

    rendered, failed = 0, 0
    for item in pending:
        doc_id = item["doc_id"]
        try:
            canonical = await asyncio.to_thread(get_report, doc_id, account_id)
            meta_type = canonical.get("meta", {}).get("type", "EVENT").upper()
            if meta_type == "WEEKLY":
                fn = partial(generate_weekly_report, "", "", canonical)
            elif meta_type == "HEALTH":
                fn = partial(generate_health_event_report, "", "", canonical)
            else:
                fn = partial(generate_event_report, "", "", canonical)
            html = await asyncio.to_thread(fn)
            await asyncio.to_thread(save_report_html, doc_id, html, account_id)
            rendered += 1
            logger.info("render_pending: 완료 %s", doc_id)
        except Exception as e:
            logger.error("render_pending: 실패 %s: %s", doc_id, e, exc_info=True)
            failed += 1

    return {"ok": True, "data": {"rendered": rendered, "failed": failed}}


@app.get("/health")
async def health():
    return {"ok": True}
