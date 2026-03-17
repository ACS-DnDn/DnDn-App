"""
Cognito 인증 서비스 모듈.

AWS Cognito User Pool을 통한 로그인, 토큰 갱신, 로그아웃,
비밀번호 재설정, JWT 검증 기능을 제공한다.
FastAPI·DB 의존 없음 — 라우터에서 import하여 사용.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError

# ── 환경 변수 ──────────────────────────────────────────────
REGION = os.getenv("AWS_REGION", "us-east-1")
USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")


# ── 응답 데이터 클래스 ────────────────────────────────────
@dataclass
class LoginResult:
    access_token: str
    refresh_token: str
    id_token: str
    expires_in: int


@dataclass
class ChallengeResult:
    challenge: str  # e.g. "NEW_PASSWORD_REQUIRED"
    session: str


@dataclass
class RefreshResult:
    access_token: str
    expires_in: int


@dataclass
class ForgotPasswordResult:
    destination: str  # 마스킹된 이메일


# ── 에러 코드 매핑 ────────────────────────────────────────
_ERROR_MAP: dict[str, tuple[int, str]] = {
    "NotAuthorizedException": (401, "INVALID_CREDENTIALS"),
    "UserNotFoundException": (401, "INVALID_CREDENTIALS"),  # 보안상 동일 처리
    "UserNotConfirmedException": (403, "USER_NOT_CONFIRMED"),
    "UserDisabledException": (403, "USER_DISABLED"),
    "CodeMismatchException": (400, "INVALID_CODE"),
    "ExpiredCodeException": (400, "INVALID_CODE"),
    "InvalidPasswordException": (400, "WEAK_PASSWORD"),
    "LimitExceededException": (429, "TOO_MANY_REQUESTS"),
    "TooManyRequestsException": (429, "TOO_MANY_REQUESTS"),
}


class CognitoError(Exception):
    """Cognito 서비스 에러. 라우터에서 HTTP 응답으로 변환."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _client():
    return boto3.client("cognito-idp", region_name=REGION)


def _handle_error(exc: ClientError) -> None:
    error_code = exc.response["Error"]["Code"]
    error_msg = exc.response["Error"].get("Message", "")
    status, code = _ERROR_MAP.get(error_code, (500, "INTERNAL_ERROR"))
    raise CognitoError(status, code, error_msg)


# ── 로그인 ────────────────────────────────────────────────
def login(username: str, password: str) -> LoginResult | ChallengeResult:
    """Cognito USER_PASSWORD_AUTH 로그인.

    초기 비밀번호(AdminCreateUser) 상태면 ChallengeResult를 반환한다.
    """
    try:
        resp = _client().initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
            },
        )
    except ClientError as e:
        _handle_error(e)
        raise  # unreachable — _handle_error always raises

    # 챌린지 반환 (NEW_PASSWORD_REQUIRED 등)
    if "ChallengeName" in resp:
        return ChallengeResult(
            challenge=resp["ChallengeName"],
            session=resp["Session"],
        )

    auth = resp["AuthenticationResult"]
    return LoginResult(
        access_token=auth["AccessToken"],
        refresh_token=auth["RefreshToken"],
        id_token=auth["IdToken"],
        expires_in=auth["ExpiresIn"],
    )


def respond_new_password(username: str, new_password: str, session: str) -> LoginResult:
    """NEW_PASSWORD_REQUIRED 챌린지에 새 비밀번호로 응답."""
    try:
        resp = _client().respond_to_auth_challenge(
            ClientId=CLIENT_ID,
            ChallengeName="NEW_PASSWORD_REQUIRED",
            Session=session,
            ChallengeResponses={
                "USERNAME": username,
                "NEW_PASSWORD": new_password,
            },
        )
    except ClientError as e:
        _handle_error(e)
        raise  # unreachable

    auth = resp["AuthenticationResult"]
    return LoginResult(
        access_token=auth["AccessToken"],
        refresh_token=auth["RefreshToken"],
        id_token=auth["IdToken"],
        expires_in=auth["ExpiresIn"],
    )


# ── 토큰 갱신 ─────────────────────────────────────────────
def refresh_token(refresh: str) -> RefreshResult:
    """refreshToken으로 새 accessToken 발급."""
    try:
        resp = _client().initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": refresh},
        )
    except ClientError as e:
        _handle_error(e)
        raise  # unreachable

    auth = resp["AuthenticationResult"]
    return RefreshResult(
        access_token=auth["AccessToken"],
        expires_in=auth["ExpiresIn"],
    )


# ── 로그아웃 ──────────────────────────────────────────────
def logout(access_token: str) -> bool:
    """Cognito Global Sign-Out. 모든 토큰 무효화."""
    try:
        _client().global_sign_out(AccessToken=access_token)
    except ClientError as e:
        _handle_error(e)
    else:
        return True
    return False  # unreachable — _handle_error always raises


# ── 비밀번호 재설정 요청 ──────────────────────────────────
def forgot_password(email: str) -> ForgotPasswordResult:
    """비밀번호 재설정 인증 코드 발송."""
    try:
        resp = _client().forgot_password(
            ClientId=CLIENT_ID,
            Username=email,
        )
    except ClientError as e:
        _handle_error(e)
        raise  # unreachable

    dest = resp["CodeDeliveryDetails"]["Destination"]
    return ForgotPasswordResult(destination=dest)


# ── 비밀번호 재설정 확인 ──────────────────────────────────
def confirm_reset_password(email: str, code: str, new_password: str) -> bool:
    """인증 코드 + 새 비밀번호로 비밀번호 변경."""
    try:
        _client().confirm_forgot_password(
            ClientId=CLIENT_ID,
            Username=email,
            ConfirmationCode=code,
            Password=new_password,
        )
    except ClientError as e:
        _handle_error(e)
    else:
        return True
    return False  # unreachable — _handle_error always raises


# ── HR 관리자 전용 (Admin API) ────────────────────────────

def admin_create_user(email: str, name: str, temp_password: str) -> str:
    """AdminCreateUser — 사용자 생성 및 초대 이메일 발송. Returns username."""
    try:
        _client().admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            TemporaryPassword=temp_password,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": name},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",  # 초대 이메일 직접 발송하지 않음 (HR이 전달)
        )
    except ClientError as e:
        _handle_error(e)
        raise  # unreachable
    return email


def admin_delete_user(username: str) -> None:
    """사용자 계정 영구 삭제."""
    try:
        _client().admin_delete_user(UserPoolId=USER_POOL_ID, Username=username)
    except ClientError as e:
        _handle_error(e)


def admin_reset_user_password(username: str) -> None:
    """임시 비밀번호 재발급 (다음 로그인 시 변경 강제)."""
    try:
        _client().admin_reset_user_password(UserPoolId=USER_POOL_ID, Username=username)
    except ClientError as e:
        _handle_error(e)


def admin_add_to_group(username: str, group: str) -> None:
    """사용자를 Cognito 그룹에 추가."""
    try:
        _client().admin_add_user_to_group(
            UserPoolId=USER_POOL_ID, Username=username, GroupName=group
        )
    except ClientError as e:
        _handle_error(e)


def admin_remove_from_group(username: str, group: str) -> None:
    """사용자를 Cognito 그룹에서 제거."""
    try:
        _client().admin_remove_user_from_group(
            UserPoolId=USER_POOL_ID, Username=username, GroupName=group
        )
    except ClientError as e:
        _handle_error(e)


def admin_set_group(username: str, new_group: str, old_group: str | None = None) -> None:
    """그룹 변경: old_group 제거 후 new_group 추가. old_group=None이면 추가만."""
    if old_group and old_group != new_group:
        admin_remove_from_group(username, old_group)
    admin_add_to_group(username, new_group)


def admin_get_groups(username: str) -> list[str]:
    """사용자가 속한 Cognito 그룹 목록 반환."""
    try:
        resp = _client().admin_list_groups_for_user(
            UserPoolId=USER_POOL_ID, Username=username
        )
    except ClientError as e:
        _handle_error(e)
        raise  # unreachable
    return [g["GroupName"] for g in resp.get("Groups", [])]


# ── JWT 검증 (보호 엔드포인트용) ──────────────────────────
def get_user(access_token: str) -> dict[str, Any]:
    """accessToken으로 Cognito에서 사용자 정보 조회.

    Returns:
        {
            "username": str,
            "email": str,
            "name": str,
            ...Cognito UserAttributes
        }
    """
    try:
        resp = _client().get_user(AccessToken=access_token)
    except ClientError as e:
        _handle_error(e)
        raise  # unreachable

    attrs: dict[str, Any] = {"username": resp["Username"]}
    for attr in resp.get("UserAttributes", []):
        attrs[attr["Name"]] = attr["Value"]
    return attrs
