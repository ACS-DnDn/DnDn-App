import json
import os
import shutil
import boto3
import subprocess
import threading
import time
from typing import Any
from github import Github

# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
# MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")  # Legacy
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")
REGION = os.getenv("AWS_REGION", "us-east-1")

def _find_uvx() -> str:
    return (
        os.getenv("UVX_PATH")
        or shutil.which("uvx")
        or os.path.expanduser("~/.local/bin/uvx")
    )


# ─────────────────────────────────────────────────
# MCP Client (stdio transport)
# ─────────────────────────────────────────────────

class TerraformMCPClient:
    """awslabs.terraform-mcp-server와 stdio JSON-RPC 통신"""

    def __init__(self):
        self.proc = None
        self._req_id = 0
        self._lock = threading.Lock()

    def start(self):
        self.proc = subprocess.Popen(
            [_find_uvx(), "awslabs.terraform-mcp-server@latest"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # initialize 핸드셰이크
        self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dndn-report", "version": "1.0"},
            },
        })
        resp = self._read()
        # initialized 알림
        self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        return resp

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        resp = self._read()
        content = resp.get("result", {}).get("content", [])
        return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")

    def stop(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.terminate()
            self.proc = None

    def _next_id(self):
        with self._lock:
            self._req_id += 1
            return self._req_id

    def _send(self, obj: dict):
        line = json.dumps(obj) + "\n"
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def _read(self) -> dict:
        for _ in range(30):
            line = self.proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            try:
                obj = json.loads(line)
                if "id" in obj:
                    return obj
            except json.JSONDecodeError:
                continue
        return {}


# ─────────────────────────────────────────────────
# GitHub .tf 수집
# ─────────────────────────────────────────────────

def load_tf_from_github(repo_name: str, token: str = None) -> str:
    g = Github(token) if token else Github()
    repo = g.get_repo(repo_name)
    tf_files = []
    contents = repo.get_contents("")
    while contents:
        f = contents.pop(0)
        if f.type == "dir":
            contents.extend(repo.get_contents(f.path))
        elif f.name.endswith(".tf"):
            tf_files.append(f"# === {f.path} ===\n{f.decoded_content.decode()}")
    return "\n\n".join(tf_files)


# ─────────────────────────────────────────────────
# MCP 컨텍스트 조회
# ─────────────────────────────────────────────────

def _extract_resource_hint(workplan: dict) -> str:
    """작업계획서에서 AWS 리소스 타입 추출"""
    title = workplan.get("title", "").lower()
    steps_text = " ".join(
        s.get("description", "") for s in workplan.get("steps", [])
    ).lower()
    combined = title + " " + steps_text

    resource_map = {
        "eks": "aws_eks_cluster",
        "lambda": "aws_lambda_function",
        "rds": "aws_db_instance",
        "ec2": "aws_instance",
        "s3": "aws_s3_bucket",
        "waf": "aws_wafv2_web_acl",
        "alb": "aws_lb",
        "vpc": "aws_vpc",
        "iam": "aws_iam_role",
        "cloudwatch": "aws_cloudwatch_metric_alarm",
        "certificate": "aws_acm_certificate",
        "인증서": "aws_acm_certificate",
        "인스턴스": "aws_instance",
        "클러스터": "aws_eks_cluster",
        "런타임": "aws_lambda_function",
    }
    for keyword, resource in resource_map.items():
        if keyword in combined:
            return resource
    return ""


def _fetch_mcp_context(workplan: dict) -> dict:
    """MCP 서버에서 AWS Provider 문서 + Best Practices 조회"""
    context = {"aws_docs": "", "best_practices": ""}

    mcp = TerraformMCPClient()
    try:
        mcp.start()
        resource_hint = _extract_resource_hint(workplan)

        # AWS Provider 문서 조회
        if resource_hint:
            docs = mcp.call_tool("SearchAwsProviderDocs", {"asset": resource_hint})
            context["aws_docs"] = docs[:3000] if docs else ""
            print(f"[MCP] AWS 문서 조회 완료: {resource_hint} ({len(context['aws_docs'])}자)")

        # AWS AWSCC Provider 문서도 조회 (best practices 대체)
        if resource_hint:
            awscc_hint = resource_hint.replace("aws_", "awscc_", 1)
            awscc = mcp.call_tool("SearchAwsccProviderDocs", {"asset": awscc_hint})
            context["best_practices"] = awscc[:2000] if awscc else ""
            print(f"[MCP] AWSCC Provider 문서 조회 완료 ({len(context['best_practices'])}자)")

    except Exception as e:
        print(f"[MCP] 컨텍스트 조회 실패 (계속 진행): {e}")
    finally:
        mcp.stop()

    return context


def _run_checkov_scan(files: list) -> dict:
    """생성된 .tf 파일 Checkov 보안 스캔"""
    import tempfile, os

    if not files:
        return {}

    checkov_result = {}
    mcp = TerraformMCPClient()
    try:
        mcp.start()
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files:
                # path traversal 방지: basename만 허용, .tf 확장자 강제
                safe_name = os.path.basename(f.get("filename", "main.tf"))
                if not safe_name.endswith(".tf"):
                    safe_name = safe_name + ".tf"
                with open(os.path.join(tmpdir, safe_name), "w") as fp:
                    fp.write(f.get("content", ""))

            result = mcp.call_tool("RunCheckovScan", {
                "working_directory": tmpdir,
                "framework": "terraform",
                "output_format": "json",
            })
            if result:
                try:
                    parsed = json.loads(result)
                    # Checkov는 리스트([{...}]) 또는 단일 dict로 반환
                    if isinstance(parsed, list):
                        parsed = parsed[0] if parsed else {}
                    summary = parsed.get("summary", {})
                    passed = summary.get("passed", 0)
                    failed = summary.get("failed", 0)
                    checkov_result = {
                        "summary": {"passed": passed, "failed": failed},
                        "failed_checks": parsed.get("results", {}).get("failed_checks", []),
                    }
                    print(f"[MCP] Checkov 스캔 완료 — passed: {passed}, failed: {failed}")
                except (json.JSONDecodeError, KeyError, IndexError):
                    checkov_result = {"raw": result[:500]}

    except Exception as e:
        print(f"[MCP] Checkov 스캔 실패 (계속 진행): {e}")
        checkov_result = {"error": str(e)}
    finally:
        mcp.stop()

    return checkov_result


# ─────────────────────────────────────────────────
# Bedrock 호출
# ─────────────────────────────────────────────────

def _call_bedrock(workplan: dict, existing_tf: str, mcp_context: dict) -> dict:
    client = boto3.client("bedrock-runtime", region_name=REGION)

    aws_docs_section = (
        f"\n## AWS Provider 공식 문서 (MCP 실시간 조회)\n{mcp_context['aws_docs']}\n"
        if mcp_context.get("aws_docs") else ""
    )
    best_practices_section = (
        f"\n## AWS Terraform Best Practices (MCP)\n{mcp_context['best_practices']}\n"
        if mcp_context.get("best_practices") else ""
    )

    system = """
당신은 AWS 인프라 테라폼 코드 전문가입니다.
작업계획서, 기존 테라폼 코드, AWS 공식 문서를 분석하여 바로 apply 가능한 테라폼 코드를 생성하세요.

규칙:
1. 기존 코드의 네이밍 컨벤션, 변수 스타일, 태그 구조를 반드시 따르세요
2. AWS Provider 공식 문서의 최신 argument를 사용하세요
3. AWS Best Practices를 반드시 준수하세요
4. Checkov 보안 스캔을 통과할 수 있도록 보안 설정을 포함하세요
5. 반드시 JSON만 반환하고 다른 텍스트는 절대 포함하지 마세요
""".strip()

    user = f"""
## 작업계획서
{json.dumps(workplan, ensure_ascii=False, indent=2)}

## 기존 테라폼 코드 (스타일/컨벤션 참고)
{existing_tf}
{aws_docs_section}
{best_practices_section}

위 내용을 모두 반영하여 바로 apply 가능한 테라폼 코드를 생성해주세요.

다음 JSON 형식으로 반환하세요:
{{
  "files": [
    {{
      "filename": "파일명.tf",
      "content": "테라폼 코드 전체 내용"
    }}
  ],
  "summary": "생성된 코드 설명 (한국어, 2~3문장)"
}}
""".strip()

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    clean = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답 JSON 파싱 실패: {e}\n원문: {clean[:200]}")


# ─────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────

def generate_terraform_code(
    workplan: dict,
    repo_name: str,
    github_token: str = None,
) -> dict:
    """
    작업계획서 + MCP(AWS Provider 문서 + Checkov) → 테라폼 코드 생성

    흐름:
    1. GitHub .tf 수집 (기존 스타일 학습)
    2. MCP로 AWS Provider 문서 + Best Practices 조회
    3. Bedrock으로 코드 생성
    4. MCP Checkov로 보안 스캔
    """
    print("[1/4] GitHub .tf 코드 수집 중...")
    existing_tf = load_tf_from_github(repo_name, github_token)

    print("[2/4] MCP로 AWS 문서 조회 중...")
    mcp_context = _fetch_mcp_context(workplan)

    print("[3/4] Bedrock으로 코드 생성 중...")
    generated = _call_bedrock(workplan, existing_tf, mcp_context)

    print("[4/4] MCP Checkov 보안 스캔 중...")
    checkov_result = _run_checkov_scan(generated.get("files", []))

    return {**generated, "checkov": checkov_result}
