from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt
from typing import Union
import urllib.request
import json

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
)
from apps.api.src.security.cognito import (
    login,
    respond_new_password,
    refresh_token,
    logout,
    LoginResult,
    ChallengeResult,
    CognitoError,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# -------------------------------------------------------------------
# ⚙️ AWS Cognito 설정
# -------------------------------------------------------------------
COGNITO_REGION = "ap-northeast-2"
COGNITO_USER_POOL_ID = "ap-northeast-2_AqyobCjs4"
COGNITO_APP_CLIENT_ID = "2ihan310ih4tg1qk71t7fsvdu"

JWKS_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"

jwks_cache = None


def get_jwks():
    global jwks_cache
    if jwks_cache is None:
        with urllib.request.urlopen(JWKS_URL) as response:
            jwks_cache = json.loads(response.read().decode("utf-8"))
    return jwks_cache


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
        payload = jwt.decode(
            token,
            get_jwks(),
            algorithms=["RS256"],
            audience=COGNITO_APP_CLIENT_ID,
            options={"verify_aud": False},
        )

        cognito_user_id = payload.get("sub")
        email = payload.get("email")
        username = payload.get("cognito:username", "알수없는유저")

        if cognito_user_id is None:
            raise credentials_exception

    except Exception as e:
        print(f"Token Verification Error: {e}")
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
            email=email if email else f"{username}@placeholder.com",
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
async def auth_login(req: LoginRequest):
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
async def auth_challenge(req: ChallengeRequest):
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
async def auth_refresh(req: RefreshRequest):
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
async def auth_logout(token: str = Depends(_extract_access_token)):
    """Cognito Global Sign-Out. 모든 토큰 무효화."""
    try:
        logout(token)
    except CognitoError as e:
        raise HTTPException(status_code=e.status, detail=e.code) from e

    return SuccessResponse(data={"message": "로그아웃 완료"})


# -------------------------------------------------------------------
# 5. 내 정보 조회 (GET /auth/me) — DB User + 회사 정보
# -------------------------------------------------------------------
@router.get(
    "/me", response_model=SuccessResponse[UserMeResponse], summary="내 정보 조회"
)
async def get_my_info(current_user: User = Depends(get_current_user)):
    """Cognito JWT를 검증하고 유저 및 소속 회사 정보를 반환한다."""
    company_data = {"name": "소속 회사 없음", "logoUrl": ""}

    if current_user.company:
        company_data["name"] = current_user.company.name
        company_data["logoUrl"] = current_user.company.logo_url

    my_info_data = {
        "name": current_user.name,
        "role": current_user.role,
        "company": company_data,
    }

    return SuccessResponse(data=my_info_data)
