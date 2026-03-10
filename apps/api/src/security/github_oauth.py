"""
GitHub OAuth 연동 서비스 모듈.

GitHub OAuth App을 통한 인증 플로우와
조직/레포지토리/브랜치 조회 기능을 제공한다.
FastAPI·DB 의존 없음 — 라우터에서 import하여 사용.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field

import requests

# ── 환경 변수 ──────────────────────────────────────────────
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI", "http://localhost:8000/api/github/callback"
)

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_API = "https://api.github.com"

# OAuth 스코프: 조직 읽기 + 레포 읽기
_SCOPES = "read:org,repo"


# ── 응답 데이터 클래스 ────────────────────────────────────
@dataclass
class AuthUrlResult:
    authorize_url: str
    state: str


@dataclass
class CallbackResult:
    connected: bool
    username: str
    access_token: str  # 서버에서만 보관, 프론트에 노출 X


@dataclass
class OrgItem:
    login: str
    avatar_url: str | None = None


@dataclass
class RepoItem:
    name: str
    private: bool
    default_branch: str


@dataclass
class BranchItem:
    name: str
    is_default: bool = False


# ── 에러 ──────────────────────────────────────────────────
class GitHubError(Exception):
    """GitHub API 호출 에러."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _check_response(resp: requests.Response) -> None:
    if resp.status_code == 401:
        raise GitHubError(401, "UNAUTHORIZED", "GitHub 토큰이 만료되었습니다.")
    if resp.status_code == 403:
        raise GitHubError(403, "FORBIDDEN", "GitHub 연동되지 않음")
    if resp.status_code == 404:
        raise GitHubError(404, "NOT_FOUND", "리소스를 찾을 수 없습니다.")
    if not resp.ok:
        raise GitHubError(resp.status_code, "GITHUB_ERROR", resp.text)


# ── 1. OAuth 인증 URL 생성 ────────────────────────────────
def get_auth_url() -> AuthUrlResult:
    """GitHub OAuth 인증 페이지 URL과 CSRF state 반환."""
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": _SCOPES,
        "state": state,
    }
    url = requests.Request("GET", _GITHUB_AUTHORIZE_URL, params=params).prepare().url
    return AuthUrlResult(authorize_url=url or "", state=state)


# ── 2. OAuth 콜백 (code → access_token) ───────────────────
def exchange_code(code: str, state: str) -> CallbackResult:
    """GitHub 인증 코드를 access token으로 교환.

    Args:
        code: GitHub이 발급한 인증 코드
        state: CSRF 검증용 state (호출자가 세션 state와 비교해야 함)
    """
    resp = requests.post(
        _GITHUB_TOKEN_URL,
        json={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": GITHUB_REDIRECT_URI,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    data = resp.json()

    if "error" in data:
        raise GitHubError(
            400, "BAD_REQUEST", data.get("error_description", data["error"])
        )

    access_token = data["access_token"]

    # 사용자 정보 조회
    user_resp = requests.get(
        f"{_GITHUB_API}/user",
        headers=_gh_headers(access_token),
        timeout=10,
    )
    _check_response(user_resp)
    username = user_resp.json().get("login", "")

    return CallbackResult(
        connected=True,
        username=username,
        access_token=access_token,
    )


# ── 3. 조직 목록 조회 ─────────────────────────────────────
def get_orgs(token: str) -> list[OrgItem]:
    """OAuth 연결된 GitHub 계정의 접근 가능한 조직 목록."""
    resp = requests.get(
        f"{_GITHUB_API}/user/orgs",
        headers=_gh_headers(token),
        timeout=10,
    )
    _check_response(resp)

    return [
        OrgItem(login=org["login"], avatar_url=org.get("avatar_url"))
        for org in resp.json()
    ]


# ── 4. 레포지토리 목록 조회 ───────────────────────────────
def get_repos(token: str, org: str) -> list[RepoItem]:
    """선택한 조직의 레포지토리 목록."""
    resp = requests.get(
        f"{_GITHUB_API}/orgs/{org}/repos",
        headers=_gh_headers(token),
        params={"type": "all", "sort": "updated", "per_page": 100},
        timeout=10,
    )
    _check_response(resp)

    return [
        RepoItem(
            name=r["name"],
            private=r["private"],
            default_branch=r.get("default_branch", "main"),
        )
        for r in resp.json()
    ]


# ── 5. 브랜치 목록 조회 ───────────────────────────────────
def get_branches(token: str, org: str, repo: str) -> list[BranchItem]:
    """선택한 레포지토리의 브랜치 목록."""
    # 기본 브랜치명 확인
    repo_resp = requests.get(
        f"{_GITHUB_API}/repos/{org}/{repo}",
        headers=_gh_headers(token),
        timeout=10,
    )
    _check_response(repo_resp)
    default_branch = repo_resp.json().get("default_branch", "main")

    # 브랜치 목록 조회
    resp = requests.get(
        f"{_GITHUB_API}/repos/{org}/{repo}/branches",
        headers=_gh_headers(token),
        params={"per_page": 100},
        timeout=10,
    )
    _check_response(resp)

    return [
        BranchItem(name=b["name"], is_default=(b["name"] == default_branch))
        for b in resp.json()
    ]
