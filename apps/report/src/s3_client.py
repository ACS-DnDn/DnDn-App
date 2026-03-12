import boto3
import json
import os
import uuid
from datetime import datetime

S3_BUCKET = os.getenv("S3_BUCKET", "dndn-reports")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")


def _client():
    return boto3.client("s3", region_name=REGION)


def save_result(account_id: str, workplan: dict, tf_files: list[dict]) -> dict:
    """편집된 작업계획서 + Terraform 파일을 S3에 저장하고 키 정보 반환"""
    job_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    client = _client()

    wp_key = f"{account_id}/workplan/{job_id}/workplan.json"
    client.put_object(
        Bucket=S3_BUCKET,
        Key=wp_key,
        Body=json.dumps(workplan, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )

    tf_keys = []
    for f in tf_files:
        tf_key = f"{account_id}/workplan/{job_id}/terraform/{f['name']}"
        client.put_object(
            Bucket=S3_BUCKET,
            Key=tf_key,
            Body=f["code"],
            ContentType="text/plain",
        )
        tf_keys.append(tf_key)

    return {
        "job_id": job_id,
        "workplan_key": wp_key,
        "terraform_keys": tf_keys,
        "s3_bucket": S3_BUCKET,
    }
