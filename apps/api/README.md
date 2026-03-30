# API

`apps/api`는 DnDn의 메인 백엔드 API입니다. 인증, 문서 결재, 워크스페이스, GitHub/Slack 연동, 보고서 생성 요청을 담당합니다.

## 실행

`apps/api` 내부 코드가 `apps.api.src.*` import를 사용하므로 레포 루트에서 실행하는 것을 권장합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
cp apps/api/.env.example apps/api/.env
set -a
source apps/api/.env
set +a
PYTHONPATH=. uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload
```

- Health check: `GET http://localhost:8000/health`
- 기본 API prefix: `/api`

## 주요 라우터

`apps/api/src/main.py` 기준 등록 순서:

- `/api/auth`
- `/api/dashboard`
- `/api/documents`
- `/api/org`
- `/api/github`
- `/api/report-settings`
- `/api/reports`
- `/api/workspaces`
- `/api/hr/users`
- `/api/hr/departments`
- `/api/hr/company`
- `/api/admin/companies`
- `/api/slack`
- `/internal`

## 환경변수

예시 파일은 `apps/api/.env.example`에 있습니다. 실제로 자주 쓰는 항목은 아래입니다.

주의: 현재 `apps/api`는 `.env`를 자동 로드하지 않습니다. 로컬 실행 전 셸에서 `source apps/api/.env`로 환경변수를 먼저 올려야 합니다.

- DB: `SQLALCHEMY_DATABASE_URL`
- AWS/S3: `AWS_REGION`, `S3_BUCKET`, `S3_PUBLIC_BUCKET`
- Cognito: `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`
- STS: `STS_ROLE_NAME`, `STS_EXTERNAL_ID`, `PLATFORM_ACCOUNT_ID`, `CFN_TEMPLATE_URL`
- EventBridge/Scheduler: `EVENT_BUS_ARN`, `SCHEDULER_GROUP_NAME`, `SCHEDULER_ROLE_ARN`, `SCHEDULER_TARGET_ARN`
- Queue/Internal: `REPORT_REQUEST_QUEUE_URL`, `INTERNAL_API_KEY`
- GitHub OAuth: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_WEBHOOK_URL`
- Slack OAuth: `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI`

## 구현 메모

- 서버 시작 시 SQLAlchemy `create_all`과 일부 컬럼 보정 로직이 함께 실행됩니다.
- 워크스페이스 `code` 백필 및 unique index 생성도 `main.py`에서 수행합니다.
- 인증은 Cognito JWT 기반이며, GitHub/Slack OAuth 연동 라우터가 포함되어 있습니다.

## 구조

```text
apps/api/
├── src/
│   ├── routers/
│   ├── schemas/
│   ├── security/
│   ├── database.py
│   ├── main.py
│   └── models.py
├── requirements.txt
├── .env.example
└── Dockerfile
```
