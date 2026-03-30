# Report

`apps/report`는 DnDn의 보고서/계획서 생성 서비스입니다. HTTP API와 SQS worker가 함께 들어 있으며, AI 생성 결과를 S3와 MariaDB에 저장합니다.

## 실행 모드

### 1. HTTP API

웹에서 직접 호출하는 서버입니다.

```bash
cd apps/report
cp .env.example .env
uv sync
uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

- Health check: `GET http://localhost:8001/health`
- 로컬 웹 연동 기준 포트: `8001`

`uv`를 쓰지 않는다면 아래처럼 실행해도 됩니다.

```bash
pip install -e .
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

### 2. SQS worker

Worker가 올린 canonical JSON 또는 보고서 생성 요청을 받아 비동기 생성 작업을 수행합니다.

```bash
cd apps/report
uv run python -m src.sqs_worker
```

`docker-compose.yml`에는 `api`, `sqs-worker` 두 서비스가 정의되어 있습니다.

## 주요 엔드포인트

`src/main.py` 기준:

- `POST /api/report/event`
- `POST /api/report/health-event`
- `POST /api/report/weekly`
- `POST /api/report/render`
- `POST /report-api/documents/generate/plan`
- `POST /report-api/documents/generate/terraform`
- `GET /report-api/documents/generate/{job_id}`
- `POST /report-api/documents/generate/terraform/validate`
- `POST /report-api/documents/generate/terraform/fix`
- `PUT /report-api/documents/html/save`
- `PUT /report-api/documents/generate/terraform/save`
- `GET /health`

## 환경변수

예시 파일은 `apps/report/.env.example`에 있습니다.

- 필수: `DATABASE_URL`
- AI/AWS: `AWS_REGION`, `BEDROCK_MODEL_ID`, `S3_BUCKET`
- GitHub: `GITHUB_TOKEN`, `GITHUB_REPO`
- SQS worker: `SQS_QUEUE_URL`, `POLL_INTERVAL`
- 내부 통신: `DNDN_API_URL`, `INTERNAL_API_KEY`
- 브라우저 허용 origin: `ALLOWED_ORIGINS`

## 구조

```text
apps/report/
├── src/
│   ├── ai_generator.py
│   ├── terraform_generator.py
│   ├── opa_engine.py
│   ├── sqs_worker.py
│   ├── s3_client.py
│   ├── database.py
│   ├── models.py
│   └── main.py
├── tests/
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
├── .env.example
└── Dockerfile
```

## 참고

- 로컬 웹 프론트와 맞추려면 `apps/web/vite.config.ts` 기준으로 Report API를 `8001`에서 실행하는 것이 편합니다.
- 컨테이너 이미지는 `Dockerfile`에서 기본적으로 `8000` 포트를 노출합니다.
