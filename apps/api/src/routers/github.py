# apps/api/routers/github.py

from __future__ import annotations

import hashlib
import hmac
import logging
import requests as _requests
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User, Document, Workspace, DocumentRead
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


def _mark_unread(db: Session, doc: Document) -> None:
    """문서 상태 변경 시 기존 읽음 기록을 삭제하여 안읽음으로 전환."""
    db.query(DocumentRead).filter(DocumentRead.document_id == doc.id).delete()


def _fetch_check_run_summary(repo_full: str, check_run_id: int, db: Session) -> str:
    """GitHub API로 check_run output의 title + summary 첫 줄만 조회. 실패 시 빈 문자열."""
    token = _get_github_token_for_repo(repo_full, db)
    if not token:
        return ""
    try:
        resp = _requests.get(
            f"https://api.github.com/repos/{repo_full}/check-runs/{check_run_id}",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        output = resp.json().get("output", {})
        title = output.get("title", "")
        summary = output.get("summary", "")
        first_line = summary.split("\n")[0].strip() if summary else ""
        parts = [p for p in [title, first_line] if p]
        return " — ".join(parts)[:300]
    except Exception as e:
        _logger.warning("check_run output 조회 실패: %s", e)
        return ""


def _get_github_token_for_repo(repo_full: str, db: Session) -> str | None:
    """repo_full에서 workspace owner의 GitHub 토큰을 조회."""
    parts = repo_full.split("/", 1)
    if len(parts) != 2:
        return None
    owner, repo_name = parts
    ws = db.query(Workspace).filter(
        Workspace.github_org == owner, Workspace.repo == repo_name
    ).first()
    if not ws:
        return None
    owner_user = db.query(User).filter(User.id == ws.owner_id).first()
    if not owner_user or not owner_user.github_access_token:
        return None
    return owner_user.github_access_token


def _fetch_status_description(repo_full: str, sha: str, context: str, db: Session) -> str:
    """GitHub API로 상세 에러 메시지를 조회. check_runs output > commit status description 순으로 시도."""
    token = _get_github_token_for_repo(repo_full, db)
    if not token:
        return ""
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    # 1차: 같은 커밋의 check_runs에서 Terraform 관련 output 조회 (가장 상세)
    try:
        resp = _requests.get(
            f"https://api.github.com/repos/{repo_full}/commits/{sha}/check-runs",
            headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            for cr in resp.json().get("check_runs", []):
                cr_name = (cr.get("name") or "").lower()
                if "terraform" in cr_name or context.lower() in cr_name:
                    output = cr.get("output", {})
                    title = output.get("title", "")
                    summary = output.get("summary", "")
                    if summary:
                        first_line = summary.split("\n")[0].strip()
                        desc_parts = [p for p in [title, first_line] if p]
                        desc = " — ".join(desc_parts)[:300]
                        if len(desc) > 20:
                            _logger.info("[check_runs API] found: name=%s desc=%s", cr.get("name"), desc[:80])
                            return desc
    except Exception as e:
        _logger.warning("check_runs 조회 실패: %s", e)

    # 2차: Combined Status API (fallback)
    try:
        resp = _requests.get(
            f"https://api.github.com/repos/{repo_full}/commits/{sha}/status",
            headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            for s in resp.json().get("statuses", []):
                if s.get("context") == context:
                    desc = s.get("description", "")
                    if len(desc) > 20:
                        return desc[:300]
    except Exception as e:
        _logger.warning("status API 조회 실패: %s", e)

    return ""


def _append_deploy_log(
    db: Session,
    doc: Document,
    event: str,
    status: str,
    description: str | None = None,
    url: str | None = None,
    context: str | None = None,
) -> None:
    """deploy_log JSON 배열에 이벤트를 추가한다."""
    entry = {
        "event": event,
        "status": status,
        "description": description,
        "url": url,
        "context": context,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    log = list(doc.deploy_log or [])
    log.append(entry)
    doc.deploy_log = log


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
        _logger.error("GITHUB_WEBHOOK_SECRET 미설정 — webhook 처리 불가")
        return JSONResponse(status_code=503, content={"error": "WEBHOOK_SECRET_NOT_CONFIGURED"})

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
            _mark_unread(db, doc)
            _append_deploy_log(db, doc, "merged", "success",
                               description="PR이 Merge되었습니다.",
                               url=pr.get("html_url"))
            db.commit()

    # ── check_run 이벤트 ──
    elif event == "check_run":
        check_run = payload.get("check_run", {})
        conclusion = check_run.get("conclusion")
        action = check_run.get("status")  # completed
        pull_requests = check_run.get("pull_requests", [])
        _logger.info("[webhook:check_run] repo=%s name=%s conclusion=%s prs=%d",
                     repo_full, check_run.get("name", ""), conclusion, len(pull_requests))

        for pr_ref in pull_requests:
            pr_number = pr_ref.get("number")
            if not pr_number:
                continue

            doc = _find_doc_by_pr(db, repo_full, pr_number)
            if not doc or doc.pr_status in ("merged", "closed"):
                continue

            if conclusion in ("failure", "timed_out", "action_required"):
                cr_output = check_run.get("output", {})
                cr_title = cr_output.get("title") or check_run.get("name", "")
                cr_summary = cr_output.get("summary") or ""
                cr_text = cr_output.get("text") or ""
                # 상세 로그 조합: title + summary + text (최대 5000자)
                cr_parts = [p for p in [cr_title, cr_summary, cr_text] if p]
                cr_desc = "\n".join(cr_parts)[:5000] or check_run.get("name", "")
                # webhook output이 빈약하면 GitHub API로 요약 조회
                if len(cr_desc) < 100 and check_run.get("id"):
                    api_desc = _fetch_check_run_summary(repo_full, check_run["id"], db)
                    if len(api_desc) > len(cr_desc):
                        cr_desc = api_desc
                cr_url = check_run.get("details_url") or check_run.get("html_url")
                cr_ctx = check_run.get("name", "")
                first_failure = doc.pr_status != "checks_failed"
                if first_failure:
                    doc.pr_status = "checks_failed"
                    doc.status = "deploy_failed"
                    _mark_unread(db, doc)
                _append_deploy_log(db, doc, "checks_failed", "failure",
                                   description=cr_desc, url=cr_url, context=cr_ctx)
                db.commit()
                if first_failure:
                    _notify_pr_status(db, doc, "checks_failed")
            elif conclusion == "success" and action == "completed":
                cr_output = check_run.get("output", {})
                cr_title = cr_output.get("title") or check_run.get("name", "")
                cr_summary = cr_output.get("summary") or ""
                cr_parts = [p for p in [cr_title, cr_summary] if p]
                cr_desc = "\n".join(cr_parts)[:500] or check_run.get("name", "")
                cr_url = check_run.get("details_url") or check_run.get("html_url")
                cr_ctx = check_run.get("name", "")
                _append_deploy_log(db, doc, "checks_passed", "success",
                                   description=cr_desc, url=cr_url, context=cr_ctx)
                db.commit()
                # 개별 check 성공 → 전체 통과 여부 확인 후 자동 머지
                _try_auto_merge(db, doc, repo_full)

    # ── status 이벤트 (Terraform Cloud 등 외부 CI) ──
    elif event == "status":
        state = payload.get("state", "")  # pending / success / failure / error
        branches = payload.get("branches", [])
        context = payload.get("context", "")
        sha = payload.get("sha", "")

        _logger.info("[webhook:status] repo=%s state=%s context=%s desc=%s",
                     repo_full, state, context, (payload.get("description", ""))[:100])

        if "/" not in repo_full:
            return JSONResponse({"received": True})
        repo_owner, repo_name = repo_full.split("/", 1)

        for branch_info in branches:
            branch_name = branch_info.get("name", "")

            # dndn/ prefix가 있는 브랜치의 status → PR 검증 결과
            if branch_name.startswith("dndn/"):
                # 브랜치명에서 doc_num 추출 (dndn/2026-PLN-0001 → 2026-PLN-0001)
                doc_num = branch_name.split("/", 1)[1]
                doc = (
                    db.query(Document)
                    .join(Workspace, Document.workspace_id == Workspace.id)
                    .filter(
                        Document.doc_num == doc_num,
                        Document.pr_status.in_(["open", "checks_failed"]),
                        Workspace.github_org == repo_owner,
                        Workspace.repo == repo_name,
                    )
                    .first()
                )
                if doc:
                    st_desc = payload.get("description", "") or ""
                    st_url = payload.get("target_url", "")
                    st_ctx = context
                    # Terraform Cloud 등 description이 빈약하면 상세 조회
                    if len(st_desc) < 50 and sha:
                        api_desc = _fetch_status_description(repo_full, sha, context, db)
                        if api_desc and len(api_desc) > len(st_desc):
                            st_desc = api_desc
                    if state in ("failure", "error"):
                        first_failure = doc.pr_status != "checks_failed"
                        if first_failure:
                            doc.pr_status = "checks_failed"
                            doc.status = "deploy_failed"
                            _mark_unread(db, doc)
                        _append_deploy_log(db, doc, "checks_failed", "failure",
                                           description=st_desc, url=st_url, context=st_ctx)
                        db.commit()
                        if first_failure:
                            _notify_pr_status(db, doc, "checks_failed")
                    elif state == "success":
                        _append_deploy_log(db, doc, "checks_passed", "success",
                                           description=st_desc, url=st_url, context=st_ctx)
                        db.commit()
                        _try_auto_merge(db, doc, repo_full)
                break

            # default branch의 status (머지 후) → Terraform Cloud apply 결과 추적
            if "terraform" in context.lower():
                # 가장 최근 머지된 문서 1건만 대상 (동일 repo에 여러 문서 시 오매칭 방지)
                doc = (
                    db.query(Document)
                    .join(Workspace, Document.workspace_id == Workspace.id)
                    .filter(
                        Document.pr_status == "merged",
                        Workspace.github_org == repo_owner,
                        Workspace.repo == repo_name,
                    )
                    .order_by(Document.updated_at.desc())
                    .first()
                )
                if doc:
                    apply_desc = payload.get("description", "") or ""
                    apply_url = payload.get("target_url", "")
                    apply_ctx = context
                    if len(apply_desc) < 50 and sha:
                        api_desc = _fetch_status_description(repo_full, sha, context, db)
                        if api_desc and len(api_desc) > len(apply_desc):
                            apply_desc = api_desc
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
                        _mark_unread(db, doc)
                        _append_deploy_log(db, doc, new_pr_status, "success" if new_pr_status == "applied" else "failure",
                                           description=apply_desc, url=apply_url, context=apply_ctx)
                        db.commit()
                        _notify_pr_status(db, doc, new_pr_status)
                break

    return JSONResponse({"received": True})


def _try_auto_merge(db: Session, doc: Document, repo_full: str) -> None:
    """모든 체크 통과 시 auto_merge 설정에 따라 머지하거나 수동 안내."""
    _logger.info("[auto_merge] 시작: doc=%s pr=#%s pr_status=%s auto_merge=%s",
                 doc.id, doc.pr_number, doc.pr_status, doc.auto_merge)
    if not doc.pr_number or doc.pr_status in ("merged",):
        _logger.info("[auto_merge] 스킵: pr_number=%s pr_status=%s", doc.pr_number, doc.pr_status)
        return

    ws = db.query(Workspace).filter(Workspace.id == doc.workspace_id).first()
    if not ws:
        _logger.warning("[auto_merge] 워크스페이스 없음: doc=%s", doc.id)
        return
    owner_user = db.query(User).filter(User.id == ws.owner_id).first()
    if not owner_user or not owner_user.github_access_token:
        _logger.warning("[auto_merge] owner 또는 GitHub 토큰 없음: ws=%s owner=%s", ws.id, ws.owner_id)
        return

    # 전체 체크 통과 확인
    checks_ok = get_pr_checks_passed(owner_user.github_access_token, ws.github_org, ws.repo, doc.pr_number)
    _logger.info("[auto_merge] checks_passed=%s for #%s", checks_ok, doc.pr_number)
    if not checks_ok:
        return

    # 체크 통과 → deploy_failed 복구 (이전 실패에서 재통과한 경우)
    if doc.status == "deploy_failed":
        doc.status = "deploying"
        doc.pr_status = "open"

    # auto_merge 여부에 따라 분기
    if doc.auto_merge:
        # 자동 Merge
        merged = merge_pr(owner_user.github_access_token, ws.github_org, ws.repo, doc.pr_number)
        if merged:
            doc.pr_status = "merged"
            _mark_unread(db, doc)
            _append_deploy_log(db, doc, "merged", "success",
                               description="PR 검증 통과 — 자동 Merge 완료")
            db.commit()
            _logger.info("PR 자동 Merge 완료: %s #%s", repo_full, doc.pr_number)
            _notify_pr_status(db, doc, "checks_passed")
        else:
            _logger.warning("PR 자동 Merge 실패: %s #%s", repo_full, doc.pr_number)
            _append_deploy_log(db, doc, "merge_failed", "failure",
                               description="자동 Merge 실패 (conflict 또는 권한 문제)")
            db.commit()
            _notify_pr_status(db, doc, "checks_failed")
    else:
        # 수동 Merge 안내
        db.commit()
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
    """webhook 미등록 워크스페이스에 대해 일괄 등록 (본인 소유만)."""
    workspaces = db.query(Workspace).filter(
        Workspace.github_webhook_id.is_(None),
        Workspace.owner_id == current_user.id,
    ).all()

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
