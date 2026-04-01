from src.schemas import WorkPlanRequest, TerraformRequest, _to_camel


def test_to_camel_converts_snake_case():
    assert _to_camel("workspace_id") == "workspaceId"
    assert _to_camel("author_position") == "authorPosition"


def test_work_plan_request_accepts_camel_case_fields():
    req = WorkPlanRequest.model_validate(
        {
            "workspaceId": "ws-1",
            "target": "EC2 보안 조치",
            "content": "상세 내용",
            "refDocIds": ["doc-1", "doc-2"],
            "authorId": "user-1",
            "authorName": "홍길동",
            "authorPosition": "팀장",
            "companyLogoUrl": "https://example.com/logo.png",
        }
    )

    assert req.workspace_id == "ws-1"
    assert req.ref_doc_ids == ["doc-1", "doc-2"]
    assert req.author_id == "user-1"
    assert req.author_name == "홍길동"
    assert req.author_position == "팀장"
    assert req.company_logo_url == "https://example.com/logo.png"


def test_terraform_request_accepts_both_alias_and_field_name():
    req = TerraformRequest.model_validate(
        {
            "document_id": "doc-123",
            "workspaceId": "ws-1",
            "repoName": "org/repo",
            "github_token": "token-1",
        }
    )

    assert req.document_id == "doc-123"
    assert req.workspace_id == "ws-1"
    assert req.repo_name == "org/repo"
    assert req.github_token == "token-1"
