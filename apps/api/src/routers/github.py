# apps/api/routers/github.py

from fastapi import APIRouter, Depends, HTTPException

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

# 💡 사용자별 GitHub access_token 임시 저장소
# 실무에서는 DB 또는 Redis를 사용합니다. 지금은 메모리(dict)로 처리.
_github_tokens: dict[str, str] = {}


def _get_github_token(user_id: str) -> str:
    """저장된 GitHub 토큰을 꺼낸다. 없으면 403."""
    token = _github_tokens.get(user_id)
    if not token:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return token


# ---------------------------------------------------------
# 1. GitHub OAuth 시작 (GET /github/auth)
# ---------------------------------------------------------
@router.get("/auth", response_model=SuccessResponse[GitHubAuthResponse])
async def github_auth(
    current_user: User = Depends(get_current_user),
):
    """
    GitHub OAuth 인증 플로우를 시작한다.
    응답으로 받은 URL로 사용자를 리다이렉트한다.
    """
    result = get_auth_url()

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
async def github_callback(
    code: str,
    state: str,
    current_user: User = Depends(get_current_user),
):
    """
    GitHub 인증 완료 후 리다이렉트되는 콜백.
    code를 access token으로 교환하고 서버에 저장한다.
    """
    try:
        result = exchange_code(code, state)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code)

    # access_token을 사용자 ID 기준으로 서버에 보관
    _github_tokens[current_user.id] = result.access_token

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
async def github_orgs(
    current_user: User = Depends(get_current_user),
):
    """
    OAuth 연결된 GitHub 계정의 접근 가능한 조직 목록을 반환한다.
    GitHub 연결 성공 후 자동 호출.
    """
    token = _get_github_token(current_user.id)

    try:
        orgs = get_orgs(token)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code)

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
async def github_repos(
    org: str,
    current_user: User = Depends(get_current_user),
):
    """
    선택한 조직의 레포지토리 목록을 조회한다.
    조직 선택 시 호출.
    """
    token = _get_github_token(current_user.id)

    try:
        repos = get_repos(token, org)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code)

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
async def github_branches(
    org: str,
    repo: str,
    current_user: User = Depends(get_current_user),
):
    """
    선택한 레포지토리의 브랜치 목록을 조회한다.
    레포지토리 선택 시 호출.
    """
    token = _get_github_token(current_user.id)

    try:
        branches = get_branches(token, org, repo)
    except GitHubError as e:
        raise HTTPException(status_code=e.status, detail=e.code)

    return SuccessResponse(
        data=GitHubBranchesResponse(
            branches=[
                GitHubBranchItem(name=b.name, isDefault=b.is_default)
                for b in branches
            ]
        )
    )
