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
def login(username: str, password: str) -> LoginResult:
    """Cognito USER_PASSWORD_AUTH 로그인."""
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
        return True
    except ClientError as e:
        _handle_error(e)
    return False


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
        return True
    except ClientError as e:
        _handle_error(e)
    return False


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

    attrs: dict[str, Any] = {"username": resp["Username"]}
    for attr in resp.get("UserAttributes", []):
        attrs[attr["Name"]] = attr["Value"]
    return attrs
