# apps/api/schemas/aws.py

from pydantic import BaseModel
from typing import Optional


# --- AWS 연동 테스트 (POST /workspaces/test-aws) ---
class AwsTestRequest(BaseModel):
    acctId: str  # AWS 계정 ID (12자리 숫자)


class AwsTestResponse(BaseModel):
    success: bool  # AssumeRole 성공 여부
    acctId: str  # 테스트한 계정 ID
    roleArn: Optional[str] = None  # 성공 시 ARN
    error: Optional[str] = None  # 실패 시 오류 메시지


# --- CFN Quick-create URL 생성 (POST /workspaces/cfn-link) ---
class CfnLinkRequest(BaseModel):
    acctId: str  # AWS 계정 ID (12자리 숫자)


class CfnLinkResponse(BaseModel):
    url: str   # CloudFormation Quick-create URL
    acctId: str  # 검증된 계정 ID
