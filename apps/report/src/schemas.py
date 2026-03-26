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
    author_id: str | None = None           # 접속자 DB user ID
    author_name: str | None = None       # 접속자 이름
    author_position: str | None = None   # 접속자 직책
    company_logo_url: str | None = None  # 회사 로고 URL


class TerraformRequest(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    document_id: str
    workspace_id: str | None = None
    repo_name: str | None = None
    github_token: str | None = None
    deploy_log: list[dict] | None = None  # 이전 배포 실패 이력 (재수정 시 AI 참조용)


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
    ref_doc_ids: list[str] = []
