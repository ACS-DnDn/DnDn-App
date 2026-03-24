from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt
from typing import Union
import urllib.request
import json
import datetime
import logging

from apps.api.src.database import get_db
from apps.api.src.models import User
from apps.api.src.schemas.users import UserMeResponse
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.auth import (
    LoginRequest,
    LoginResponse,
    ChallengeResponse,
    ChallengeRequest,
    RefreshRequest,
    RefreshResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ConfirmResetRequest,
)
from apps.api.src.security.cognito import (
    login,
    respond_new_password,
    refresh_token,
    logout,
    forgot_password,
    confirm_reset_password,
    LoginResult,
    ChallengeResult,
    CognitoError,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# -------------------------------------------------------------------
# ⚙️ AWS Cognito 설정
# -------------------------------------------------------------------
import os as _os
COGNITO_REGION = _os.getenv("AWS_REGION", "ap-northeast-2")
COGNITO_USER_POOL_ID = _os.getenv("COGNITO_USER_POOL_ID", "")

JWKS_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour TTL for JWKS cache

jwks_cache = None


def get_jwks():
    """
    JWKS를 가져오고, TTL 기반 캐싱과 네트워크 타임아웃을 적용한다.
    """
    global jwks_cache
    now = datetime.datetime.utcnow()

    # jwks_cache 구조: {"data": <jwks_dict>, "fetched_at": <datetime>}
    cache_valid = (
        isinstance(jwks_cache, dict)
        and "data" in jwks_cache
        and "fetched_at" in jwks_cache
        and now - jwks_cache["fetched_at"] < datetime.timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
    )

    if not cache_valid:
        try:
            with urllib.request.urlopen(JWKS_URL, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                jwks_cache = {
                    "data": data,
                    "fetched_at": now,
                }
        except Exception as e:
            if not cache_valid and (jwks_cache is None or "data" not in jwks_cache):
                raise
            # 이전 캐시가 있으면 로그만 남기고 기존 캐시를 계속 사용한다.
            logging.getLogger(__name__).warning("JWKS fetch error, using cached JWKS: %s", e)

    if isinstance(jwks_cache, dict) and "data" in jwks_cache:
        return jwks_cache["data"]

    raise RuntimeError("JWKS cache is not initialized and fetch failed.")


def _get_public_key(token: str) -> dict:
    """JWT header의 kid에 맞는 공개키를 JWKS에서 반환. kid 불일치 시 캐시 무효화 후 재시도."""
    global jwks_cache

    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    for key in get_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key

    # 키 롤오버 대응: 캐시 무효화 후 1회 재시도
    jwks_cache = None
    for key in get_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key

    raise ValueError(f"kid '{kid}'에 맞는 공개키가 없습니다")


# -------------------------------------------------------------------
# 🛡️ Cognito JWT 검증 + DB 유저 조회 (다른 라우터의 공통 의존성)
# -------------------------------------------------------------------
security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
    db: Session = Depends(get_db),
):
    """
    JWT를 JWKS로 검증한 뒤 DB User 객체를 반환한다.
    dashboard, documents, org, report_settings 등에서 의존한다.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않거나 만료된 Cognito 토큰입니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        public_key = _get_public_key(token)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="인증 서비스를 일시적으로 사용할 수 없습니다.",
        )

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Cognito access token은 aud 클레임 없음
        )

        # iss, token_use 명시적 검증
        if payload.get("iss") != COGNITO_ISSUER:
            raise ValueError("iss 불일치")
        if payload.get("token_use") != "access":
            raise ValueError("access token만 허용")

        cognito_user_id = payload.get("sub")
        email = payload.get("email")
        username = payload.get("cognito:username") or f"unknown-{cognito_user_id[:8] if cognito_user_id else 'none'}"

        if cognito_user_id is None:
            raise credentials_exception

    except Exception:
        raise credentials_exception

    # 1차: cognito_sub로 조회 (정상 경로)
    user = db.query(User).filter(User.cognito_sub == cognito_user_id).first()

    if user is None and email:
        # 2차: HR이 사전 생성한 유저를 이메일로 조회 → cognito_sub 등록
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            user.cognito_sub = cognito_user_id
            db.commit()
            db.refresh(user)

    if user is None:
        # 3차: 완전히 새 유저 (AdminCreateUser 없이 직접 Cognito 가입한 경우 — 기본 fallback)
        import uuid as _uuid
        user = User(
            id=str(_uuid.uuid4()),
            cognito_sub=cognito_user_id,
            email=email or f"{cognito_user_id}@placeholder.invalid",
            name=username,
            role="member",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


# -------------------------------------------------------------------
# 헤더에서 Bearer 토큰 추출 (Cognito SDK 호출용)
# -------------------------------------------------------------------
def _extract_access_token(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
) -> str:
    return credentials.credentials


# -------------------------------------------------------------------
# 1. 로그인 (POST /auth/login)
# -------------------------------------------------------------------
@router.post(
    "/login",
    response_model=SuccessResponse[Union[LoginResponse, ChallengeResponse]],
)
def auth_login(req: LoginRequest):
    """
    이메일+비밀번호로 Cognito 로그인.
    초기 비밀번호 상태면 챌린지를 반환한다.
    """
    try:
        result = login(req.email, req.password)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    if isinstance(result, ChallengeResult):
        return SuccessResponse(
            data=ChallengeResponse(
                challenge=result.challenge,
                session=result.session,
            )
        )

    return SuccessResponse(
        data=LoginResponse(
            accessToken=result.access_token,
            refreshToken=result.refresh_token,
            idToken=result.id_token,
            expiresIn=result.expires_in,
        )
    )


# -------------------------------------------------------------------
# 2. 비밀번호 변경 챌린지 (POST /auth/challenge)
# -------------------------------------------------------------------
@router.post("/challenge", response_model=SuccessResponse[LoginResponse])
def auth_challenge(req: ChallengeRequest):
    """NEW_PASSWORD_REQUIRED 챌린지에 새 비밀번호로 응답."""
    try:
        result = respond_new_password(req.email, req.newPassword, req.session)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(
        data=LoginResponse(
            accessToken=result.access_token,
            refreshToken=result.refresh_token,
            idToken=result.id_token,
            expiresIn=result.expires_in,
        )
    )


# -------------------------------------------------------------------
# 3. 토큰 갱신 (POST /auth/refresh)
# -------------------------------------------------------------------
@router.post("/refresh", response_model=SuccessResponse[RefreshResponse])
def auth_refresh(req: RefreshRequest):
    """refreshToken으로 새 accessToken 발급."""
    try:
        result = refresh_token(req.refreshToken)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(
        data=RefreshResponse(
            accessToken=result.access_token,
            expiresIn=result.expires_in,
        )
    )


# -------------------------------------------------------------------
# 4. 로그아웃 (POST /auth/logout)
# -------------------------------------------------------------------
@router.post("/logout", response_model=SuccessResponse[dict])
def auth_logout(token: str = Depends(_extract_access_token)):
    """Cognito Global Sign-Out. 모든 토큰 무효화."""
    try:
        logout(token)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(data={"message": "로그아웃 완료"})


# -------------------------------------------------------------------
# 5. 비밀번호 재설정 요청 (POST /auth/forgot-password)
# -------------------------------------------------------------------
@router.post("/forgot-password", response_model=SuccessResponse[ForgotPasswordResponse])
def auth_forgot_password(req: ForgotPasswordRequest):
    """비밀번호 재설정 인증 코드를 이메일로 발송."""
    try:
        result = forgot_password(req.email)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(
        data=ForgotPasswordResponse(destination=result.destination)
    )


# -------------------------------------------------------------------
# 6. 비밀번호 재설정 확인 (POST /auth/confirm-reset)
# -------------------------------------------------------------------
@router.post("/confirm-reset", response_model=SuccessResponse[dict])
def auth_confirm_reset(req: ConfirmResetRequest):
    """인증 코드 + 새 비밀번호로 비밀번호 변경."""
    try:
        confirm_reset_password(req.email, req.code, req.newPassword)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(data={"message": "비밀번호가 변경되었습니다."})


# -------------------------------------------------------------------
# 7. 내 정보 조회 (GET /auth/me) — DB User + 회사 정보
# -------------------------------------------------------------------
@router.get(
    "/me", response_model=SuccessResponse[UserMeResponse], summary="내 정보 조회"
)
def get_my_info(current_user: User = Depends(get_current_user)):
    """Cognito JWT를 검증하고 유저 및 소속 회사 정보를 반환한다."""
    company_data = {"name": "소속 회사 없음", "logoUrl": ""}

    if current_user.company:
        company_data["name"] = current_user.company.name
        company_data["logoUrl"] = current_user.company.logo_url

    created_at = None
    if current_user.created_at:
        created_at = current_user.created_at.strftime("%Y.%m.%d")

    my_info_data = {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "position": current_user.position,
        "company": company_data,
        "createdAt": created_at,
    }

    return SuccessResponse(data=my_info_data)
