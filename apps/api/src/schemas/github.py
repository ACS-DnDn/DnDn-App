# apps/api/schemas/github.py

from pydantic import BaseModel
from typing import List, Optional


# --- GitHub OAuth 시작 (GET /github/auth) ---
class GitHubAuthResponse(BaseModel):
    authorizeUrl: str  # GitHub 인증 페이지 URL
    state: str  # CSRF 방지용 상태 값


# --- GitHub OAuth 콜백 (GET /github/callback) ---
class GitHubCallbackResponse(BaseModel):
    connected: bool  # 연결 성공 여부
    username: str  # GitHub 사용자명


# --- GitHub 조직 목록 (GET /github/orgs) ---
class GitHubOrgItem(BaseModel):
    login: str  # 조직 로그인명
    avatarUrl: Optional[str] = None  # 조직 아바타 URL


class GitHubOrgsResponse(BaseModel):
    orgs: List[GitHubOrgItem]


# --- 레포지토리 목록 (GET /github/orgs/{org}/repos) ---
class GitHubRepoItem(BaseModel):
    name: str  # 레포지토리명
    private: bool  # 비공개 여부
    defaultBranch: str  # 기본 브랜치명


class GitHubReposResponse(BaseModel):
    repos: List[GitHubRepoItem]


# --- 브랜치 목록 (GET /github/repos/{org}/{repo}/branches) ---
class GitHubBranchItem(BaseModel):
    name: str  # 브랜치명
    isDefault: bool  # 기본 브랜치 여부


class GitHubBranchesResponse(BaseModel):
    branches: List[GitHubBranchItem]
