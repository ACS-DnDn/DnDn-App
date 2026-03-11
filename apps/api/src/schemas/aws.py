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
