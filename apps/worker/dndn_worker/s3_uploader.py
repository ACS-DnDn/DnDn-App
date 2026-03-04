from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import List

import boto3


def upload_tree_to_s3(
    session: boto3.Session,
    local_root: Path,
    bucket: str,
    prefix: str,
    *,
    sse: str = "AES256",
) -> List[str]:
    """Upload every file under local_root to s3://bucket/prefix/<relative_path>.

    - Stable order (sorted) to make debugging easier
    - Skips macOS noise files (.DS_Store / AppleDouble)
    - Uses SSE-S3 by default (AES256)

    Returns a list of uploaded S3 URIs.
    """
    s3 = session.client("s3")
    prefix = prefix.strip("/")

    uploaded: List[str] = []
    for p in sorted(local_root.rglob("*")):
        if p.is_dir():
            continue
        if p.name == ".DS_Store" or p.name.startswith("._"):
            continue

        rel = p.relative_to(local_root).as_posix()
        key = f"{prefix}/{rel}" if prefix else rel

        extra = {"ServerSideEncryption": sse}
        ctype = mimetypes.guess_type(p.name)[0]
        if ctype:
            extra["ContentType"] = ctype

        s3.upload_file(str(p), bucket, key, ExtraArgs=extra)
        uploaded.append(f"s3://{bucket}/{key}")

    return uploaded
