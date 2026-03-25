# apps/api/routers/github.py

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Document, Workspace
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.github import (
    GitHubAuthResponse,
    GitHubCallbackResponse,
    GitHubOrgItem,
    GitHubOrgsResponse,
    GitHubRepoItem,
    GitHubReposResponse,
    GitHubBranchItem,
    GitHubBranchesResponse,
)
from apps.api.src.security.github_oauth import (
    get_auth_url,
    exchange_code,
    get_orgs,
    get_repos,
    get_branches,
    register_webhook,
    GitHubError,
    GITHUB_WEBHOOK_SECRET,
)
from apps.api.src.security.slack_oauth import send_message, SlackError

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["GitHub"])

# ── TTL 설정 ──────────────────────────────────────────────
_STATE_TTL = timedelta(minutes=10)


def _get_valid_states(user: User) -> list[dict]:
    """만료되지 않은 state 목록 반환."""
    now = datetime.now(timezone.utc).isoformat()
    states = user.github_oauth_states or []
    return [s for s in states if s["expires_at"] > now]


def _get_github_token(user: User) -> str:
    """저장된 GitHub 토큰을 꺼낸다. 없으면 403."""
    if not user.github_access_token:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return user.github_access_token


# ---------------------------------------------------------
# 1. GitHub OAuth 시작 (GET /github/auth)
# ---------------------------------------------------------
@router.get("/auth", response_model=SuccessResponse[GitHubAuthResponse])
def github_auth(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    GitHub OAuth 인증 플로우를 시작한다.
    응답으로 받은 URL로 사용자를 리다이렉트한다.
    """
    result = get_auth_url()

    states = _get_valid_states(current_user)
    states.append({
        "value": result.state,
        "expires_at": (datetime.now(timezone.utc) + _STATE_TTL).isoformat(),
    })
    current_user.github_oauth_states = states
    db.commit()

    return SuccessResponse(
        data=GitHubAuthResponse(
            authorizeUrl=result.authorize_url,
            state=result.state,
        )
    )


# ---------------------------------------------------------
# 2. GitHub OAuth 콜백 (GET /github/callback)
# ---------------------------------------------------------
@router.get("/callback", response_model=SuccessResponse[GitHubCallbackResponse])
def github_callback(
    code: str,
    state: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    GitHub 인증 완료 후 리다이렉트되는 콜백.
    code를 access token으로 교환하고 DB에 저장한다.
    """
    # CSRF 방지: DB에 저장된 state에서 일치하는 항목 소비
    valid_states = _get_valid_states(current_user)
    matched = next((s for s in valid_states if s["value"] == state), None)
    if not matched:
        raise HTTPException(status_code=400, detail="INVALID_OAUTH_STATE")
    current_user.github_oauth_states = [s for s in valid_states if s["value"] != state]
    db.commit()

    try:
        result = exchange_code(code, state)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    current_user.github_access_token = result.access_token
    db.commit()

    return SuccessResponse(
        data=GitHubCallbackResponse(
            connected=result.connected,
            username=result.username,
        )
    )


# ---------------------------------------------------------
# 3. GitHub 조직 목록 조회 (GET /github/orgs)
# ---------------------------------------------------------
@router.get("/orgs", response_model=SuccessResponse[GitHubOrgsResponse])
def github_orgs(
    current_user: User = Depends(get_current_user),
):
    """
    OAuth 연결된 GitHub 계정의 접근 가능한 조직 목록을 반환한다.
    GitHub 연결 성공 후 자동 호출.
    """
    token = _get_github_token(current_user)

    try:
        orgs = get_orgs(token)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(
        data=GitHubOrgsResponse(
            orgs=[
                GitHubOrgItem(login=o.login, avatarUrl=o.avatar_url)
                for o in orgs
            ]
        )
    )


# ---------------------------------------------------------
# 4. 레포지토리 목록 조회 (GET /github/orgs/{org}/repos)
# ---------------------------------------------------------
@router.get("/orgs/{org}/repos", response_model=SuccessResponse[GitHubReposResponse])
def github_repos(
    org: str,
    current_user: User = Depends(get_current_user),
):
    """
    선택한 조직의 레포지토리 목록을 조회한다.
    조직 선택 시 호출.
    """
    token = _get_github_token(current_user)

    try:
        repos = get_repos(token, org)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(
        data=GitHubReposResponse(
            repos=[
                GitHubRepoItem(
                    name=r.name,
                    private=r.private,
                    defaultBranch=r.default_branch,
                )
                for r in repos
            ]
        )
    )


# ---------------------------------------------------------
# 5. 브랜치 목록 조회 (GET /github/repos/{org}/{repo}/branches)
# ---------------------------------------------------------
@router.get(
    "/repos/{org}/{repo}/branches",
    response_model=SuccessResponse[GitHubBranchesResponse],
)
def github_branches(
    org: str,
    repo: str,
    current_user: User = Depends(get_current_user),
):
    """
    선택한 레포지토리의 브랜치 목록을 조회한다.
    레포지토리 선택 시 호출.
    """
    token = _get_github_token(current_user)

    try:
        branches = get_branches(token, org, repo)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(
        data=GitHubBranchesResponse(
            branches=[
                GitHubBranchItem(name=b.name, isDefault=b.is_default)
                for b in branches
            ]
        )
    )


# ---------------------------------------------------------
# 6. GitHub Webhook 수신 (POST /github/webhook)
# ---------------------------------------------------------

def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """GitHub X-Hub-Signature-256 헤더 검증."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def _notify_pr_status(user: User | None, doc: Document, new_status: str) -> None:
    """PR 상태 변경 Slack 알림."""
    if not user or not user.slack_access_token or user.slack_notify is False or not user.slack_user_id:
        return
    emoji = {"merged": "🟢", "closed": "🔴", "checks_failed": "⚠️", "open": "🔄"}.get(new_status, "📋")
    text = f"{emoji} PR 상태 변경: {doc.title} → {new_status}"
    if doc.pr_url:
        text += f"\n{doc.pr_url}"
    try:
        send_message(user.slack_access_token, user.slack_user_id, text)
    except SlackError:
        pass


def _find_doc_by_pr(db: Session, repo_full_name: str, pr_number: int) -> Document | None:
    """repo full name (owner/repo)과 PR number로 문서를 찾는다."""
    parts = repo_full_name.split("/", 1)
    if len(parts) != 2:
        return None
    owner, repo_name = parts
    return (
        db.query(Document)
        .join(Workspace, Document.workspace_id == Workspace.id)
        .filter(
            Document.pr_number == pr_number,
            Workspace.github_org == owner,
            Workspace.repo == repo_name,
        )
        .first()
    )


@router.post("/webhook")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    """GitHub webhook 이벤트 수신. JWT 인증 없이 HMAC 서명으로 검증."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event = request.headers.get("X-GitHub-Event", "")

    if not GITHUB_WEBHOOK_SECRET:
        _logger.warning("GITHUB_WEBHOOK_SECRET 미설정 — webhook 무시")
        return JSONResponse({"received": True})

    if not _verify_signature(body, signature, GITHUB_WEBHOOK_SECRET):
        return JSONResponse(status_code=403, content={"error": "INVALID_SIGNATURE"})

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"received": True})

    repo_full = payload.get("repository", {}).get("full_name", "")

    # ── pull_request 이벤트 ──
    if event == "pull_request":
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number")
        merged = pr.get("merged", False)

        if not pr_number:
            return JSONResponse({"received": True})

        doc = _find_doc_by_pr(db, repo_full, pr_number)
        if not doc:
            return JSONResponse({"received": True})

        new_status = None
        if action == "closed" and merged:
            new_status = "merged"
        elif action == "closed" and not merged:
            new_status = "closed"
        elif action == "reopened":
            new_status = "open"

        if new_status and new_status != doc.pr_status:
            doc.pr_status = new_status
            db.commit()
            _notify_pr_status(doc.author, doc, new_status)

    # ── check_run 이벤트 ──
    elif event == "check_run":
        check_run = payload.get("check_run", {})
        conclusion = check_run.get("conclusion")  # success / failure / timed_out / ...
        pull_requests = check_run.get("pull_requests", [])

        for pr_ref in pull_requests:
            pr_number = pr_ref.get("number")
            if not pr_number:
                continue

            doc = _find_doc_by_pr(db, repo_full, pr_number)
            if not doc:
                continue

            new_status = None
            if conclusion in ("failure", "timed_out", "action_required"):
                new_status = "checks_failed"
            elif conclusion == "success" and doc.pr_status == "checks_failed":
                new_status = "open"

            if new_status and new_status != doc.pr_status:
                doc.pr_status = new_status
                db.commit()
                _notify_pr_status(doc.author, doc, new_status)

    return JSONResponse({"received": True})


# ---------------------------------------------------------
# 7. 기존 워크스페이스 Webhook 보정 (POST /github/webhooks/backfill)
# ---------------------------------------------------------
@router.post("/webhooks/backfill")
def github_webhook_backfill(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """webhook 미등록 워크스페이스에 대해 일괄 등록."""
    workspaces = db.query(Workspace).filter(Workspace.github_webhook_id.is_(None)).all()

    total = len(workspaces)
    registered = 0
    failed = 0

    for ws in workspaces:
        owner_user = db.query(User).filter(User.id == ws.owner_id).first()
        if not owner_user or not owner_user.github_access_token:
            failed += 1
            continue
        try:
            hook_id = register_webhook(
                token=owner_user.github_access_token,
                owner=ws.github_org,
                repo=ws.repo,
            )
            ws.github_webhook_id = hook_id
            db.commit()
            registered += 1
        except Exception as e:
            _logger.warning("webhook 등록 실패 (workspace=%s): %s", ws.id, e)
            failed += 1

    return SuccessResponse(data={"total": total, "registered": registered, "failed": failed})
