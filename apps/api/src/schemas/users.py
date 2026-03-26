# app/schemas/users.py

from __future__ import annotations

from pydantic import BaseModel


class CompanyResponse(BaseModel):
    name: str
    logoUrl: str = ""


class UserMeResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    position: str | None = None
    company: CompanyResponse
    createdAt: str | None = None
