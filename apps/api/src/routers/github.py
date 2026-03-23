# apps/api/routers/github.py

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.database import get_db
from apps.api.src.models import User
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
    GitHubError,
)

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
