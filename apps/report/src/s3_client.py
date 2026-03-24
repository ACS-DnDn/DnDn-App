import boto3
import json
import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta

S3_BUCKET = os.getenv("S3_BUCKET", "dndn-reports")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")


def _client():
    return boto3.client("s3", region_name=REGION)


PRESIGNED_EXPIRES = int(os.getenv("S3_PRESIGNED_EXPIRES", "3600"))  # 기본 1시간
REPORTS_PREFIX = "reports"


def _presigned_url(client, key: str) -> str:
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=PRESIGNED_EXPIRES,
    )


def save_report(doc_id: str, data: dict, workspace_id: str = "default") -> str:
    """보고서 생성 결과를 S3에 저장하고 key 반환"""
    key = f"{workspace_id}/{REPORTS_PREFIX}/{doc_id}.json"
    _client().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )
    return key


def save_report_html(doc_id: str, html: str, workspace_id: str = "default") -> str:
    """렌더링된 보고서 HTML을 S3에 저장하고 key 반환"""
    key = f"{workspace_id}/{REPORTS_PREFIX}/{doc_id}.html"
    _client().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )
    return key


def list_reports(workspace_id: str = "default") -> list[dict]:
    """S3에서 보고서 + 작업계획서 목록 조회 (html presigned URL 포함)"""
    client = _client()
    items = []

    # 1. 자동생성 보고서 (Lambda → reports/)
    reports_prefix = f"{workspace_id}/{REPORTS_PREFIX}/"
    resp = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=reports_prefix)
    json_objs: dict[str, dict] = {}
    html_objs: dict[str, dict] = {}
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        filename = key.split("/")[-1]
        if filename.endswith(".json"):
            doc_id = filename[:-5]
            if doc_id:
                json_objs[doc_id] = obj
        elif filename.endswith(".html"):
            doc_id = filename[:-5]
            if doc_id:
                html_objs[doc_id] = obj

    for doc_id, obj in json_objs.items():
        html_obj = html_objs.get(doc_id)
        entry: dict = {
            "doc_id": doc_id,
            "type": "report",
            "last_modified": obj["LastModified"].isoformat(),
            "json_key": obj["Key"],
            "json_url": _presigned_url(client, obj["Key"]),
            "html_key": html_obj["Key"] if html_obj else None,
            "html_url": _presigned_url(client, html_obj["Key"]) if html_obj else None,
        }
        items.append(entry)

    # 2. 사용자 작성 계획서 (workplan/)
    workplan_prefix = f"{workspace_id}/workplan/"
    resp2 = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=workplan_prefix)
    wp_json: dict[str, dict] = {}
    wp_html: dict[str, dict] = {}
    for obj in resp2.get("Contents", []):
        key = obj["Key"]
        parts = key.split("/")
        # format: {workspace_id}/workplan/{job_id}/workplan.json
        if len(parts) < 4:
            continue
        job_id = parts[2]
        filename = parts[-1]
        if filename == "workplan.json":
            wp_json[job_id] = obj
        elif filename == "workplan.html":
            wp_html[job_id] = obj

    for job_id, obj in wp_json.items():
        html_obj = wp_html.get(job_id)
        entry = {
            "doc_id": job_id,
            "type": "workplan",
            "last_modified": obj["LastModified"].isoformat(),
            "json_key": obj["Key"],
            "json_url": _presigned_url(client, obj["Key"]),
            "html_key": html_obj["Key"] if html_obj else None,
            "html_url": _presigned_url(client, html_obj["Key"]) if html_obj else None,
        }
        items.append(entry)

    items.sort(key=lambda x: x.get("last_modified") or "", reverse=True)
    return items


def get_report(doc_id: str, workspace_id: str = "default") -> dict:
    """S3에서 보고서 canonical JSON 조회"""
    key = f"{workspace_id}/{REPORTS_PREFIX}/{doc_id}.json"
    resp = _client().get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(resp["Body"].read())


_MCP_CACHE_PREFIX = "_mcp_docs_cache"
_MCP_CACHE_TTL_HOURS = 24


def get_mcp_docs_cache(query: str) -> str | None:
    """S3에서 MCP 문서 캐시 조회. TTL 초과 또는 없으면 None 반환"""
    key = f"{_MCP_CACHE_PREFIX}/{hashlib.md5(query.encode()).hexdigest()}.json"
    try:
        resp = _client().get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(resp["Body"].read())
        cached_at = datetime.fromisoformat(data["cached_at"])
        if datetime.now(timezone.utc) - cached_at < timedelta(
            hours=_MCP_CACHE_TTL_HOURS
        ):
            return data["content"]
        return None  # TTL 초과
    except Exception:
        return None  # 캐시 없음 또는 오류


def set_mcp_docs_cache(query: str, content: str) -> None:
    """S3에 MCP 문서 캐시 저장"""
    key = f"{_MCP_CACHE_PREFIX}/{hashlib.md5(query.encode()).hexdigest()}.json"
    try:
        _client().put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(
                {
                    "query": query,
                    "content": content,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
            ),
            ContentType="application/json",
        )
    except Exception:
        pass  # 캐시 저장 실패는 무시


def get_presigned_url(key: str) -> str:
    """S3 key에 대한 presigned URL 반환"""
    return _presigned_url(_client(), key)


def get_html(key: str) -> str:
    """S3에서 HTML 파일 내용 조회"""
    resp = _client().get_object(Bucket=S3_BUCKET, Key=key)
    return resp["Body"].read().decode("utf-8")


def save_terraform_files(workspace_id: str, job_id: str, files: list[dict]) -> str:
    """terraform 파일 목록을 S3에 저장하고 prefix 반환 (각 파일: {filename, content})"""
    client = _client()
    prefix = f"{workspace_id}/workplan/{job_id}/terraform"
    for f in files:
        key = f"{prefix}/{f['filename']}"
        body = f["content"]
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=body.encode("utf-8") if isinstance(body, str) else body,
            ContentType="text/plain",
        )
    return prefix


def get_workplan(job_id: str, workspace_id: str = "default") -> dict:
    """S3에서 작업계획서 JSON 조회"""
    key = f"{workspace_id}/workplan/{job_id}/workplan.json"
    resp = _client().get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(resp["Body"].read())


def save_result(
    workspace_id: str,
    workplan: dict,
    html: str,
    tf_files: list[dict],
    job_id: str | None = None,
) -> dict:
    """편집된 작업계획서 + HTML + Terraform 파일을 S3에 저장하고 키 + presigned URL 반환"""
    if not job_id:
        job_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    client = _client()

    wp_key = f"{workspace_id}/workplan/{job_id}/workplan.json"
    client.put_object(
        Bucket=S3_BUCKET,
        Key=wp_key,
        Body=json.dumps(workplan, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )

    html_key = f"{workspace_id}/workplan/{job_id}/workplan.html"
    client.put_object(
        Bucket=S3_BUCKET,
        Key=html_key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )

    tf_results = []
    for f in tf_files:
        tf_key = f"{workspace_id}/workplan/{job_id}/terraform/{f['name']}"
        client.put_object(
            Bucket=S3_BUCKET,
            Key=tf_key,
            Body=f["code"],
            ContentType="text/plain",
        )
        tf_results.append(
            {
                "name": f["name"],
                "key": tf_key,
                "url": _presigned_url(client, tf_key),
            }
        )

    return {
        "job_id": job_id,
        "workplan": {
            "key": wp_key,
            "url": _presigned_url(client, wp_key),
        },
        "html": {
            "key": html_key,
            "url": _presigned_url(client, html_key),
        },
        "terraform_files": tf_results,
        "s3_bucket": S3_BUCKET,
    }
