from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any
import os
import asyncio
import logging
from functools import partial

from dotenv import load_dotenv
load_dotenv()

from .ai_generator import generate_event_report, generate_weekly_report, generate_work_plan, generate_health_event_report
from .terraform_generator import generate_terraform_code
from .s3_client import save_result, save_report, list_reports, get_report

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


class CanonicalRequest(BaseModel):
    canonical: dict[str, Any]


class HealthEventRequest(BaseModel):
    raw: dict[str, Any]   # AWS Health EventBridge raw JSON


class DocBasedWorkPlanRequest(BaseModel):
    source_doc: dict[str, Any]   # 이벤트 보고서 or 주간 보고서 canonical


class TerraformRequest(BaseModel):
    workplan: dict[str, Any]
    repo_name: str | None = None
    github_token: str | None = None


class SaveRequest(BaseModel):
    account_id: str = "default"
    workplan: dict[str, Any]
    html: str = ""
    terraform_files: list[dict[str, str]]  # [{ name, code }]


class ReportSaveRequest(BaseModel):
    account_id: str = "default"
    doc_id: str
    data: dict[str, Any]


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
async def event_report(req: CanonicalRequest):
    try:
        result = await asyncio.to_thread(generate_event_report, req.canonical)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("event_report 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── Health 이벤트 보고서 ───────────────────────────────────
@app.post("/api/report/health-event")
async def health_event_report(req: HealthEventRequest):
    try:
        result = await asyncio.to_thread(generate_health_event_report, req.raw)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("health_event_report 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── 주간 보고서 ────────────────────────────────────────────
@app.post("/api/report/weekly")
async def weekly_report(req: CanonicalRequest):
    try:
        result = await asyncio.to_thread(generate_weekly_report, req.canonical)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("weekly_report 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── 작업계획서 (문서 기반) ──────────────────────────────────
@app.post("/api/report/workplan")
async def work_plan(req: DocBasedWorkPlanRequest):
    try:
        result = await asyncio.to_thread(generate_work_plan, req.source_doc)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("work_plan 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


# ── 테라폼 코드 생성 ───────────────────────────────────────
@app.post("/api/terraform/generate")
async def terraform_generate(req: TerraformRequest):
    repo = req.repo_name or GITHUB_REPO
    if not repo:
        raise HTTPException(status_code=400, detail="GITHUB_REPO 환경변수가 설정되지 않았습니다.")
    try:
        token = req.github_token or GITHUB_TOKEN
        fn = partial(generate_terraform_code, req.workplan, repo, token)
        result = await asyncio.to_thread(fn)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("terraform_generate 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


@app.post("/api/save")
async def save_to_s3(req: SaveRequest):
    try:
        result = await asyncio.to_thread(
            save_result, req.account_id, req.workplan, req.html, req.terraform_files
        )
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("save 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="내부 서버 오류")


@app.get("/health")
async def health():
    return {"ok": True}
