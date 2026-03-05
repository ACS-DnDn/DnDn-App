# PR4: S3 storage 적용 가이드 (A/Worker)

이 zip은 **새 파일 1개**만 포함합니다.

- `apps/worker/dndn_worker/s3_uploader.py`

아래 2군데를 `apps/worker/dndn_worker/run_job.py`에 수동으로 추가하면 PR4가 완료됩니다.

## 1) import 추가

`run_job.py` 상단 import 섹션 어딘가에 추가:

```py
from dndn_worker.s3_uploader import upload_tree_to_s3
```

## 2) run_job_from_payload_file 마지막에 업로드 단계 추가

`run_job_from_payload_file` 맨 마지막 부분:

```py
result_path = norm_dir / ("event.json" if job_type == "EVENT" else "canonical.json")
dump_json(result_path, result)
return result_path
```

를 아래처럼 변경:

```py
result_path = norm_dir / ("event.json" if job_type == "EVENT" else "canonical.json")
dump_json(result_path, result)

# PR4: Upload raw/normalized artifacts to S3
bucket = payload["s3"]["bucket"]
prefix = payload["s3"]["prefix"].rstrip("/")

try:
    # storage_session은 "우리(DnDn) 계정" 권한으로 S3에 쓰는 세션.
    # (AssumeRole로 고객 계정에 들어갔더라도 S3는 우리 버킷에 저장해야 하므로 분리 권장)
    storage_session = boto3.Session()
    upload_tree_to_s3(storage_session, job_dir, bucket=bucket, prefix=prefix)
except Exception as e:
    raise RuntimeError(f"S3 upload failed: {e}") from e

return result_path
```

## 로컬 테스트

1) 테스트 버킷 생성 (예: ap-northeast-2)

```bash
aws s3 mb s3://<unique-bucket-name> --region ap-northeast-2
```

2) payload 파일의 s3.bucket / s3.prefix를 실제 값으로 변경

3) 실행 후 업로드 확인

```bash
aws s3 ls s3://<bucket>/<prefix>/ --recursive
```

- `raw/` 와 `normalized/`가 보이면 성공입니다.
