# apps/api/schemas/org.py
from pydantic import BaseModel
from typing import List


class MemberItem(BaseModel):
    id: str
    name: str
    rank: str


class OrgDeptItem(BaseModel):
    dept: str
    members: List[MemberItem]


class OrgMembersResponse(BaseModel):
    data: List[OrgDeptItem]
