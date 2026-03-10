"""
AWS STS 연동 서비스 모듈.

교차 계정 AssumeRole을 통해 고객 AWS 계정 연결 상태를 검증하고,
CloudFormation Quick-create URL을 생성한다.
FastAPI·DB 의존 없음 — 라우터에서 import하여 사용.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlencode

import boto3
from botocore.exceptions import ClientError

# ── 환경 변수 ──────────────────────────────────────────────
REGION = os.getenv("AWS_REGION", "us-east-1")
ROLE_NAME = os.getenv("STS_ROLE_NAME", "DnDnOpsAgentRole")
EXTERNAL_ID = os.getenv("STS_EXTERNAL_ID", "dndn-ops-agent")
PLATFORM_ACCOUNT_ID = os.getenv("PLATFORM_ACCOUNT_ID", "451017115109")
CFN_TEMPLATE_URL = os.getenv(
    "CFN_TEMPLATE_URL",
    "https://dndn-cfn-templates.s3.amazonaws.com/cfn/dndn-ops-agent-role.yaml",
)
SESSION_NAME = "dndn-test-session"

_ACCT_ID_RE = re.compile(r"^\d{12}$")


# ── 응답 데이터 클래스 ────────────────────────────────────
@dataclass
class AssumeRoleResult:
    success: bool
    acct_id: str
    role_arn: str
    error: str | None = None


@dataclass
class CfnLinkResult:
    url: str
    acct_id: str


# ── 유효성 검사 ───────────────────────────────────────────
class StsValidationError(Exception):
    """계정 ID 형식 오류 등 입력 검증 실패."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _validate_acct_id(acct_id: str) -> str:
    """숫자만 추출 후 12자리 검증."""
    clean = re.sub(r"\D", "", acct_id)
    if not _ACCT_ID_RE.match(clean):
        raise StsValidationError("AWS 계정 ID는 12자리 숫자여야 합니다.")
    return clean


# ── CloudFormation Quick-create URL 생성 ──────────────────
def get_cfn_link(acct_id: str) -> CfnLinkResult:
    """고객이 스택을 생성할 수 있는 CloudFormation 콘솔 URL 반환.

    고객이 이 URL을 열면 파라미터가 미리 채워진 스택 생성 페이지로 이동.
    """
    clean = _validate_acct_id(acct_id)

    params = {
        "templateURL": CFN_TEMPLATE_URL,
        "stackName": "DnDn-OpsAgent",
        "param_DnDnPlatformAccountId": PLATFORM_ACCOUNT_ID,
        "param_ExternalId": EXTERNAL_ID,
    }
    url = (
        f"https://{REGION}.console.aws.amazon.com/cloudformation/home"
        f"?region={REGION}#/stacks/quickcreate?{urlencode(params)}"
    )

    return CfnLinkResult(url=url, acct_id=clean)


# ── STS AssumeRole 테스트 ─────────────────────────────────
def test_assume_role(acct_id: str) -> AssumeRoleResult:
    """대상 계정의 DnDnOpsAgentRole을 AssumeRole하여 연동 상태 검증.

    Args:
        acct_id: AWS 계정 ID (12자리 숫자 또는 하이픈 포함 문자열)

    Returns:
        AssumeRoleResult — success=True이면 연동 성공
    """
    clean = _validate_acct_id(acct_id)
    role_arn = f"arn:aws:iam::{clean}:role/{ROLE_NAME}"

    try:
        sts = boto3.client("sts", region_name=REGION)
        sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=SESSION_NAME,
            ExternalId=EXTERNAL_ID,
            DurationSeconds=900,
        )
        return AssumeRoleResult(
            success=True,
            acct_id=clean,
            role_arn=role_arn,
        )
    except ClientError as e:
        error_code = e.response["Error"].get("Code", "")
        if error_code == "AccessDenied":
            error_msg = "연동 역할에 접근할 수 없습니다. 스택 생성을 확인하세요."
        elif error_code == "MalformedPolicyDocument":
            error_msg = "역할 정책 구성에 문제가 있습니다."
        else:
            error_msg = "AWS 계정 연동에 실패했습니다. 잠시 후 다시 시도하세요."
        return AssumeRoleResult(
            success=False,
            acct_id=clean,
            role_arn=role_arn,
            error=error_msg,
        )
