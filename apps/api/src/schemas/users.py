# app/schemas/users.py

from pydantic import BaseModel


class CompanyResponse(BaseModel):
    name: str
    logoUrl: str


class UserMeResponse(BaseModel):
    name: str
    role: str
    company: CompanyResponse
