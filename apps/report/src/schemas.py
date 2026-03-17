from pydantic import BaseModel
from typing import Any


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


class TerraformRequest(BaseModel):
    workspace_id: str
    document_id: str


class WeeklyReportRequest(BaseModel):
    target: str = ""
    content: str = ""
    period_start: str = ""
    period_end: str = ""
    account_id: str = "default"
