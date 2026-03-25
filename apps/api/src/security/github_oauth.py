"""
GitHub OAuth 연동 서비스 모듈.

GitHub OAuth App을 통한 인증 플로우와
조직/레포지토리/브랜치 조회 기능을 제공한다.
FastAPI·DB 의존 없음 — 라우터에서 import하여 사용.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

import requests

# ── 환경 변수 ──────────────────────────────────────────────
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI", "http://localhost:5173/auth/github/callback"
)
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
GITHUB_WEBHOOK_URL = os.getenv(
    "GITHUB_WEBHOOK_URL", "https://www.dndn.cloud/api/github/webhook"
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
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": GITHUB_REDIRECT_URI,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )

    try:
        data = resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        raise GitHubError(502, "BAD_GATEWAY", "GitHub 토큰 응답을 파싱할 수 없습니다.")

    if "error" in data:
        raise GitHubError(
            400, "BAD_REQUEST", data.get("error_description", data["error"])
        )

    access_token = data.get("access_token")
    if not access_token:
        raise GitHubError(502, "BAD_GATEWAY", "GitHub 토큰 응답에 access_token이 없습니다.")

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
def get_repos(token: str, owner: str) -> list[RepoItem]:
    """선택한 조직 또는 사용자의 레포지토리 목록.

    조직인 경우 /orgs/{owner}/repos, 개인 계정인 경우 /users/{owner}/repos 로 시도.
    """
    # 먼저 조직으로 시도
    resp = requests.get(
        f"{_GITHUB_API}/orgs/{owner}/repos",
        headers=_gh_headers(token),
        params={"type": "all", "sort": "updated", "per_page": 100},
        timeout=10,
    )

    # 404면 개인 계정으로 재시도
    if resp.status_code == 404:
        resp = requests.get(
            f"{_GITHUB_API}/users/{owner}/repos",
            headers=_gh_headers(token),
            params={"type": "owner", "sort": "updated", "per_page": 100},
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
def get_branches(token: str, owner: str, repo: str) -> list[BranchItem]:
    """선택한 레포지토리의 브랜치 목록."""
    # 기본 브랜치명 확인
    repo_resp = requests.get(
        f"{_GITHUB_API}/repos/{owner}/{repo}",
        headers=_gh_headers(token),
        timeout=10,
    )
    _check_response(repo_resp)
    default_branch = repo_resp.json().get("default_branch", "main")

    # 브랜치 목록 조회
    resp = requests.get(
        f"{_GITHUB_API}/repos/{owner}/{repo}/branches",
        headers=_gh_headers(token),
        params={"per_page": 100},
        timeout=10,
    )
    _check_response(resp)

    return [
        BranchItem(name=b["name"], is_default=(b["name"] == default_branch))
        for b in resp.json()
    ]


# ── 6. Terraform PR 생성 ────────────────────────────────
def create_terraform_pr(
    token: str,
    owner: str,
    repo: str,
    base_branch: str,
    head_branch: str,
    files: dict[str, str],
    title: str,
    body: str,
    path_prefix: str | None = None,
) -> dict:
    """GitHub API로 새 브랜치에 terraform 파일을 커밋하고 PR을 생성한다.

    Args:
        token: GitHub access token
        owner: GitHub org/user
        repo: 레포지토리명
        base_branch: 베이스 브랜치 (e.g. main)
        head_branch: 생성할 브랜치명 (e.g. dndn/2026-PLN-0004)
        files: {filename: content} 딕셔너리
        title: PR 제목
        body: PR 본문
        path_prefix: 레포 내 경로 접두사 (e.g. terraform/)

    Returns:
        {"pr_url": "...", "pr_number": 123}
    """
    headers = _gh_headers(token)
    api = f"{_GITHUB_API}/repos/{owner}/{repo}"

    # 1) base branch의 최신 커밋 SHA 가져오기
    ref_resp = requests.get(f"{api}/git/ref/heads/{base_branch}", headers=headers, timeout=10)
    _check_response(ref_resp)
    base_sha = ref_resp.json()["object"]["sha"]

    # 2) base 커밋의 tree SHA 가져오기
    commit_resp = requests.get(f"{api}/git/commits/{base_sha}", headers=headers, timeout=10)
    _check_response(commit_resp)
    base_tree_sha = commit_resp.json()["tree"]["sha"]

    # 3) blob 생성 + tree 구성
    tree_items = []
    for filename, content in files.items():
        file_path = f"{path_prefix}/{filename}" if path_prefix else filename
        blob_resp = requests.post(
            f"{api}/git/blobs",
            headers=headers,
            json={"content": content, "encoding": "utf-8"},
            timeout=10,
        )
        _check_response(blob_resp)
        tree_items.append({
            "path": file_path,
            "mode": "100644",
            "type": "blob",
            "sha": blob_resp.json()["sha"],
        })

    # 4) tree 생성
    tree_resp = requests.post(
        f"{api}/git/trees",
        headers=headers,
        json={"base_tree": base_tree_sha, "tree": tree_items},
        timeout=10,
    )
    _check_response(tree_resp)
    new_tree_sha = tree_resp.json()["sha"]

    # 5) 커밋 생성
    commit_create_resp = requests.post(
        f"{api}/git/commits",
        headers=headers,
        json={
            "message": title,
            "tree": new_tree_sha,
            "parents": [base_sha],
        },
        timeout=10,
    )
    _check_response(commit_create_resp)
    new_commit_sha = commit_create_resp.json()["sha"]

    # 6) 새 브랜치 생성 (이미 존재하면 업데이트)
    ref_create_resp = requests.post(
        f"{api}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{head_branch}", "sha": new_commit_sha},
        timeout=10,
    )
    if ref_create_resp.status_code == 422:
        # 브랜치가 이미 존재 → ref 업데이트
        ref_update_resp = requests.patch(
            f"{api}/git/refs/heads/{head_branch}",
            headers=headers,
            json={"sha": new_commit_sha, "force": True},
            timeout=10,
        )
        _check_response(ref_update_resp)
    else:
        _check_response(ref_create_resp)

    # 7) PR 생성
    pr_resp = requests.post(
        f"{api}/pulls",
        headers=headers,
        json={
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        },
        timeout=10,
    )
    _check_response(pr_resp)
    pr_data = pr_resp.json()

    return {"pr_url": pr_data["html_url"], "pr_number": pr_data["number"]}


# ── 7. Webhook 등록 ──────────────────────────────────────
def register_webhook(
    token: str,
    owner: str,
    repo: str,
    callback_url: str | None = None,
    secret: str | None = None,
) -> int:
    """고객 repo에 GitHub webhook을 등록하고 hook_id를 반환한다.

    이미 동일 URL의 webhook이 있으면 기존 ID를 반환한다.
    """
    url = callback_url or GITHUB_WEBHOOK_URL
    webhook_secret = secret or GITHUB_WEBHOOK_SECRET
    headers = _gh_headers(token)
    api = f"{_GITHUB_API}/repos/{owner}/{repo}"

    resp = requests.post(
        f"{api}/hooks",
        headers=headers,
        json={
            "name": "web",
            "active": True,
            "events": ["check_run", "pull_request"],
            "config": {
                "url": url,
                "content_type": "json",
                "secret": webhook_secret,
                "insecure_ssl": "0",
            },
        },
        timeout=10,
    )

    if resp.status_code == 422:
        # webhook 이미 존재 — 기존 hook 찾아서 ID 반환
        list_resp = requests.get(
            f"{api}/hooks", headers=headers, timeout=10,
        )
        _check_response(list_resp)
        for hook in list_resp.json():
            if hook.get("config", {}).get("url") == url:
                return hook["id"]
        raise GitHubError(422, "HOOK_EXISTS", "Webhook이 이미 존재하지만 찾을 수 없습니다.")

    _check_response(resp)
    return resp.json()["id"]


def unregister_webhook(
    token: str,
    owner: str,
    repo: str,
    hook_id: int,
) -> None:
    """고객 repo에서 webhook을 삭제한다. 이미 없으면 무시."""
    headers = _gh_headers(token)
    resp = requests.delete(
        f"{_GITHUB_API}/repos/{owner}/{repo}/hooks/{hook_id}",
        headers=headers,
        timeout=10,
    )
    if resp.status_code == 404:
        return  # 이미 삭제됨
    _check_response(resp)
