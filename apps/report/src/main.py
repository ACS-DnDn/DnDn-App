from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any
import os
import asyncio
from functools import partial

from .ai_generator import generate_event_report, generate_weekly_report, generate_work_plan, generate_health_event_report
from .terraform_generator import generate_terraform_code

app = FastAPI(title="DnDn Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ChanHyeok-Jeon/terraform-class")


class CanonicalRequest(BaseModel):
    canonical: dict[str, Any]


class HealthEventRequest(BaseModel):
    raw: dict[str, Any]   # AWS Health EventBridge raw JSON


class DocBasedWorkPlanRequest(BaseModel):
    source_doc: dict[str, Any]   # 이벤트 보고서 or 주간 보고서 canonical
    doc_type: str                 # "event" | "weekly"


class TerraformRequest(BaseModel):
    workplan: dict[str, Any]
    repo_name: str | None = None
    github_token: str | None = None


# ── 이벤트 보고서 ──────────────────────────────────────────
@app.post("/api/report/event")
async def event_report(req: CanonicalRequest):
    try:
        result = await asyncio.to_thread(generate_event_report, req.canonical)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Health 이벤트 보고서 ───────────────────────────────────
@app.post("/api/report/health-event")
async def health_event_report(req: HealthEventRequest):
    try:
        result = await asyncio.to_thread(generate_health_event_report, req.raw)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 주간 보고서 ────────────────────────────────────────────
@app.post("/api/report/weekly")
async def weekly_report(req: CanonicalRequest):
    try:
        result = await asyncio.to_thread(generate_weekly_report, req.canonical)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 작업계획서 (문서 기반) ──────────────────────────────────
@app.post("/api/report/workplan")
async def work_plan(req: DocBasedWorkPlanRequest):
    try:
        result = await asyncio.to_thread(generate_work_plan, req.source_doc)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 테라폼 코드 생성 ───────────────────────────────────────
@app.post("/api/terraform/generate")
async def terraform_generate(req: TerraformRequest):
    try:
        repo = req.repo_name or GITHUB_REPO
        token = req.github_token or GITHUB_TOKEN
        fn = partial(generate_terraform_code, req.workplan, repo, token)
        result = await asyncio.to_thread(fn)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"ok": True}
