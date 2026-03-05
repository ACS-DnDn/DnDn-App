from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any
import json

from ai_generator import generate_event_report, generate_weekly_report, generate_work_plan

app = FastAPI(title="DnDn Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CanonicalRequest(BaseModel):
    canonical: dict[str, Any]

@app.post("/api/report/event")
async def event_report(req: CanonicalRequest):
    try:
        result = generate_event_report(req.canonical)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/report/weekly")
async def weekly_report(req: CanonicalRequest):
    try:
        result = generate_weekly_report(req.canonical)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/report/workplan")
async def work_plan(req: CanonicalRequest):
    try:
        result = generate_work_plan(req.canonical)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"ok": True}
