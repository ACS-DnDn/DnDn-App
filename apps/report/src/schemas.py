from pydantic import BaseModel, ConfigDict


def _to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class ReportRequest(BaseModel):
    workspace_id: str = "default"
    target: str = ""
    content: str = ""
    ref_doc_ids: list[str] = []


class WorkPlanRequest(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    workspace_id: str | None = None
    target: str | None = None
    content: str | None = None
    ref_doc_ids: list[str] = []


class TerraformRequest(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    document_id: str
    workspace_id: str | None = None
    repo_name: str | None = None
    github_token: str | None = None


class SaveRequest(BaseModel):
    workspace_id: str = "default"
    job_id: str | None = None
    html: str = ""
    terraform_files: list[dict[str, str]] = []


class RenderRequest(BaseModel):
    doc_id: str
    workspace_id: str = "default"


class WeeklyReportRequest(BaseModel):
    target: str = ""
    content: str = ""
    period_start: str = ""
    period_end: str = ""
    workspace_id: str = "default"
