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
    merge_pr,
    get_pr_checks_passed,
    GitHubError,
    GITHUB_WEBHOOK_SECRET,
)
from apps.api.src.models import Approval
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


def _notify_pr_status(db: Session, doc: Document, new_status: str) -> None:
    """PR 상태 변경 Slack 알림 — 문서 작성자 + 결재선 전원에게 DM.

    알림 대상 상태: checks_passed, checks_failed, applied, apply_failed
    """
    status_labels = {
        "checks_passed": "🟢 PR 검증 통과 — 자동 Merge 완료",
        "checks_passed_manual": "🟢 PR 검증 통과 — 직접 Merge가 필요합니다",
        "checks_failed": "⚠️ PR 검증 실패",
        "applied": "✅ Terraform Apply 성공",
        "apply_failed": "❌ Terraform Apply 실패",
    }
    label = status_labels.get(new_status, f"📋 PR 상태: {new_status}")
    text = f"{label}\n📄 {doc.title}"
    if doc.pr_url:
        text += f"\n{doc.pr_url}"
    if new_status == "checks_passed_manual" and doc.pr_url:
        text += "\n👉 위 링크에서 직접 Merge 해주세요."

    # 알림 대상: 작성자 + 결재선 사용자 (중복 제거)
    user_ids: set[str] = set()
    if doc.author_id:
        user_ids.add(doc.author_id)
    approvals = db.query(Approval).filter(Approval.document_id == doc.id).all()
    for a in approvals:
        user_ids.add(a.user_id)

    users = db.query(User).filter(User.id.in_(user_ids)).all()
    for u in users:
        if u.slack_access_token and u.slack_user_id and u.slack_notify is not False:
            try:
                send_message(u.slack_access_token, u.slack_user_id, text)
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

        # 머지 완료만 추적 (DnDn이 PR 라이프사이클 관리)
        if action == "closed" and merged and doc.pr_status != "merged":
            doc.pr_status = "merged"
            db.commit()

    # ── check_run 이벤트 ──
    elif event == "check_run":
        check_run = payload.get("check_run", {})
        conclusion = check_run.get("conclusion")
        action = check_run.get("status")  # completed
        pull_requests = check_run.get("pull_requests", [])

        for pr_ref in pull_requests:
            pr_number = pr_ref.get("number")
            if not pr_number:
                continue

            doc = _find_doc_by_pr(db, repo_full, pr_number)
            if not doc or doc.pr_status in ("merged", "closed"):
                continue

            if conclusion in ("failure", "timed_out", "action_required"):
                if doc.pr_status != "checks_failed":
                    doc.pr_status = "checks_failed"
                    doc.status = "deploy_failed"
                    db.commit()
                    _notify_pr_status(db, doc, "checks_failed")
            elif conclusion == "success" and action == "completed":
                # 개별 check 성공 → 전체 통과 여부 확인 후 자동 머지
                _try_auto_merge(db, doc, repo_full)

    # ── status 이벤트 (Terraform Cloud 등 외부 CI) ──
    elif event == "status":
        state = payload.get("state", "")  # pending / success / failure / error
        branches = payload.get("branches", [])
        context = payload.get("context", "")
        sha = payload.get("sha", "")

        # Terraform Cloud apply 결과인지 확인 (머지 후 default branch의 status)
        # 머지 전 PR의 status는 check_run과 함께 처리
        for branch_info in branches:
            branch_name = branch_info.get("name", "")

            # dndn/ prefix가 있는 브랜치의 status → PR 검증 결과
            if branch_name.startswith("dndn/"):
                # PR에 연결된 문서 찾기 — sha로 PR을 역추적
                docs = (
                    db.query(Document)
                    .join(Workspace, Document.workspace_id == Workspace.id)
                    .filter(
                        Document.pr_status.in_(["open", "checks_failed"]),
                        Workspace.github_org == repo_full.split("/")[0] if "/" in repo_full else "",
                        Workspace.repo == repo_full.split("/")[1] if "/" in repo_full else "",
                    )
                    .all()
                )
                for doc in docs:
                    if doc.pr_status in ("merged", "closed"):
                        continue
                    if state == "failure" or state == "error":
                        if doc.pr_status != "checks_failed":
                            doc.pr_status = "checks_failed"
                            doc.status = "deploy_failed"
                            db.commit()
                            _notify_pr_status(db, doc, "checks_failed")
                    elif state == "success":
                        _try_auto_merge(db, doc, repo_full)
                break

            # default branch의 status (머지 후) → apply 결과 추적
            # Terraform Cloud context 패턴: "Terraform Cloud/..."
            if "terraform" in context.lower() or "Terraform Cloud" in context:
                # 머지된 문서 중 해당 repo의 것을 찾아 apply 결과 업데이트
                merged_docs = (
                    db.query(Document)
                    .join(Workspace, Document.workspace_id == Workspace.id)
                    .filter(
                        Document.pr_status == "merged",
                        Workspace.github_org == repo_full.split("/")[0] if "/" in repo_full else "",
                        Workspace.repo == repo_full.split("/")[1] if "/" in repo_full else "",
                    )
                    .all()
                )
                for doc in merged_docs:
                    new_pr_status = None
                    new_doc_status = None
                    if state == "success":
                        new_pr_status = "applied"
                        new_doc_status = "done"
                    elif state in ("failure", "error"):
                        new_pr_status = "apply_failed"
                        new_doc_status = "deploy_failed"

                    if new_pr_status and new_pr_status != doc.pr_status:
                        doc.pr_status = new_pr_status
                        doc.status = new_doc_status
                        db.commit()
                        _notify_pr_status(db, doc, new_pr_status)
                break

    return JSONResponse({"received": True})


def _try_auto_merge(db: Session, doc: Document, repo_full: str) -> None:
    """모든 체크 통과 시 auto_merge 설정에 따라 머지하거나 수동 안내."""
    if not doc.pr_number or doc.pr_status in ("merged",):
        return

    ws = db.query(Workspace).filter(Workspace.id == doc.workspace_id).first()
    if not ws:
        return
    owner_user = db.query(User).filter(User.id == ws.owner_id).first()
    if not owner_user or not owner_user.github_access_token:
        return

    # 전체 체크 통과 확인
    if not get_pr_checks_passed(owner_user.github_access_token, ws.github_org, ws.repo, doc.pr_number):
        return

    # auto_merge 여부에 따라 분기
    if doc.auto_merge is not False:
        # 자동 Merge
        merged = merge_pr(owner_user.github_access_token, ws.github_org, ws.repo, doc.pr_number)
        if merged:
            doc.pr_status = "merged"
            db.commit()
            _logger.info("PR 자동 Merge 완료: %s #%s", repo_full, doc.pr_number)
            _notify_pr_status(db, doc, "checks_passed")
        else:
            _logger.warning("PR 자동 Merge 실패: %s #%s", repo_full, doc.pr_number)
    else:
        # 수동 Merge 안내
        _logger.info("PR 검증 통과 (수동 Merge 대기): %s #%s", repo_full, doc.pr_number)
        _notify_pr_status(db, doc, "checks_passed_manual")


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
