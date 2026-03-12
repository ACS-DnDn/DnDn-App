import boto3
import json
import os
import uuid
from datetime import datetime

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


def save_report(doc_id: str, data: dict, account_id: str = "default") -> str:
    """보고서 생성 결과를 S3에 저장하고 key 반환"""
    key = f"{account_id}/{REPORTS_PREFIX}/{doc_id}.json"
    _client().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )
    return key


def list_reports(account_id: str = "default") -> list[dict]:
    """S3에서 보고서 목록 조회"""
    client = _client()
    prefix = f"{account_id}/{REPORTS_PREFIX}/"
    resp = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    items = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        doc_id = key.split("/")[-1].replace(".json", "")
        if not doc_id:
            continue
        items.append({
            "doc_id": doc_id,
            "key": key,
            "last_modified": obj["LastModified"].isoformat(),
            "size": obj["Size"],
        })
    return items


def get_report(doc_id: str, account_id: str = "default") -> dict:
    """S3에서 보고서 canonical JSON 조회"""
    key = f"{account_id}/{REPORTS_PREFIX}/{doc_id}.json"
    resp = _client().get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(resp["Body"].read())


def save_result(account_id: str, workplan: dict, tf_files: list[dict]) -> dict:
    """편집된 작업계획서 + Terraform 파일을 S3에 저장하고 키 + presigned URL 반환"""
    job_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    client = _client()

    wp_key = f"{account_id}/workplan/{job_id}/workplan.json"
    client.put_object(
        Bucket=S3_BUCKET,
        Key=wp_key,
        Body=json.dumps(workplan, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )

    tf_results = []
    for f in tf_files:
        tf_key = f"{account_id}/workplan/{job_id}/terraform/{f['name']}"
        client.put_object(
            Bucket=S3_BUCKET,
            Key=tf_key,
            Body=f["code"],
            ContentType="text/plain",
        )
        tf_results.append({
            "name": f["name"],
            "key": tf_key,
            "url": _presigned_url(client, tf_key),
        })

    return {
        "job_id": job_id,
        "workplan": {
            "key": wp_key,
            "url": _presigned_url(client, wp_key),
        },
        "terraform_files": tf_results,
        "s3_bucket": S3_BUCKET,
    }
