import re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("올바른 이메일 형식이 아닙니다.")
        return v.strip().lower()


class LoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    idToken: str
    expiresIn: int


class ChallengeResponse(BaseModel):
    challenge: str
    session: str


class ChallengeRequest(BaseModel):
    email: str
    newPassword: str = Field(..., min_length=8)
    session: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("올바른 이메일 형식이 아닙니다.")
        return v.strip().lower()


class RefreshRequest(BaseModel):
    refreshToken: str = Field(..., min_length=1)


class RefreshResponse(BaseModel):
    accessToken: str
    expiresIn: int


class MeResponse(BaseModel):
    username: str
    email: str
    name: str | None = None
