# apps/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt
import urllib.request
import json

from apps.api.database import get_db
from apps.api.models import User
from apps.api.schemas.users import UserMeResponse

router = APIRouter(tags=["Auth"])

# -------------------------------------------------------------------
# ⚙️ AWS Cognito 설정 (본인의 AWS 환경에 맞게 나중에 수정해야 합니다)
# -------------------------------------------------------------------
COGNITO_REGION = "ap-northeast-2"  # 예: 서울 리전
COGNITO_USER_POOL_ID = "ap-northeast-2_AqyobCjs4"  # Cognito 유저 풀 ID
COGNITO_APP_CLIENT_ID = "2ihan310ih4tg1qk71t7fsvdu"  # Cognito 앱 클라이언트 ID

# AWS에서 제공하는 우리 유저 풀의 공개키(JWKS) 주소
JWKS_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"

# 매번 다운받지 않도록 메모리에 캐싱
jwks_cache = None


def get_jwks():
    global jwks_cache
    if jwks_cache is None:
        with urllib.request.urlopen(JWKS_URL) as response:
            jwks_cache = json.loads(response.read().decode("utf-8"))
    return jwks_cache


# -------------------------------------------------------------------
# 🛡️ Cognito 토큰 검증 로직 (핵심 의존성)
# -------------------------------------------------------------------
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않거나 만료된 Cognito 토큰입니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1. 토큰 해독 및 AWS 공개키(JWKS)로 서명 검증
        # (algorithms="RS256" 옵션이 Cognito의 암호화 방식입니다)
        payload = jwt.decode(
            token,
            get_jwks(),
            algorithms=["RS256"],
            audience=COGNITO_APP_CLIENT_ID,
            options={
                "verify_aud": False
            },  # Access Token의 경우 aud 대신 client_id를 쓰기도 하므로 일단 False (실무 환경에 맞춰 조절)
        )

        # 2. 토큰에서 유저의 고유 ID(sub)와 정보 추출
        cognito_user_id = payload.get("sub")
        email = payload.get("email")  # Cognito 설정에 따라 id_token에 포함됨
        username = payload.get("cognito:username", "알수없는유저")

        if cognito_user_id is None:
            raise credentials_exception

    except Exception as e:
        print(f"Token Verification Error: {e}")
        raise credentials_exception

    # 3. 우리 DB에 이 유저가 있는지 확인
    user = db.query(User).filter(User.id == cognito_user_id).first()

    # 🌟 [매우 중요] DB에 유저가 없다면? (최초 로그인)
    # Cognito 회원가입 후 처음 API를 찌른 상태이므로, 우리 DB에도 유저를 자동 생성해 줍니다.
    if user is None:
        user = User(
            id=cognito_user_id,
            email=email if email else f"{username}@placeholder.com",
            name=username,
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


# -------------------------------------------------------------------
# 🚀 API 엔드포인트
# -------------------------------------------------------------------
@router.get("/me", response_model=UserMeResponse, summary="내 정보 조회")
async def get_my_info(current_user: User = Depends(get_current_user)):
    """
    프론트엔드가 전달한 Cognito JWT 토큰을 검증하고 유저 및 소속 회사 정보를 반환합니다.
    """

    # 1. 유저에게 연결된 회사 정보가 있는지 확인
    company_data = {"name": "소속 회사 없음", "logoUrl": ""}

    # 2. 회사가 연결되어 있다면 실제 DB 데이터로 덮어쓰기
    if current_user.company:
        company_data["name"] = current_user.company.name
        company_data["logoUrl"] = current_user.company.logo_url

    # 3. 실제 데이터 반환!
    return {
        "name": current_user.name,
        "role": current_user.role,
        "company": company_data,
    }
