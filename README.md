# DnDn-App

DnDn-App은 DnDn 서비스의 애플리케이션 모노레포입니다. 현재 이 레포에는 사용자 웹, 백엔드 API, AWS 수집 Worker, 보고서 생성 서비스가 함께 들어 있습니다.

실제 Kubernetes 배포 정의, 환경별 값, Argo CD 연동은 이 레포가 아니라 `DnDn-Infra`에서 관리합니다.

## 구성

| 경로 | 역할 | 주요 기술 |
| --- | --- | --- |
| `apps/web` | 사용자 웹 프론트엔드 | React, TypeScript, Vite |
| `apps/api` | 인증, 문서, 워크스페이스, 연동 API | FastAPI, SQLAlchemy, MariaDB |
| `apps/worker` | AWS 데이터 수집 및 정규화 | Python, boto3, jsonschema |
| `apps/report` | 보고서/계획서 생성 API + SQS worker | FastAPI, Bedrock, S3, MariaDB |
| `contracts` | Worker/Report 공통 스키마와 샘플 | JSON Schema |
| `docs` | 운영 메모, 트러블슈팅 | Markdown |

## 빠른 시작

### 1. Web

```bash
cd apps/web
npm ci
npm run dev
```

- 기본 주소: `http://localhost:3000`
- Vite proxy 기본값:
  - `/api` -> `http://localhost:8000`
  - `/report-api` -> `http://localhost:8001`

### 2. API

`apps/api`는 import 경로가 `apps.api.src.*` 형태라서 레포 루트에서 실행하는 것이 가장 안전합니다.

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

### 3. Report

`apps/report`는 웹에서 `/report-api`로 호출되므로 로컬에서는 `8001` 포트로 띄우는 편이 맞습니다.

```bash
cd apps/report
cp .env.example .env
uv sync
uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

`uv`를 쓰지 않는다면 `pip install -e .` 뒤에 `uvicorn src.main:app ...`으로 실행해도 됩니다.

### 4. Worker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e apps/worker
python apps/worker/tools/run_payload.py \
  --payload contracts/payload/weekly.payload.sample.json \
  --repo-root . \
  --out /tmp/dndn-out
```

## 디렉터리 구조

```text
.
├── apps/
│   ├── api/
│   ├── report/
│   ├── web/
│   └── worker/
├── contracts/
├── docs/
└── .github/workflows/deploy-app.yml
```

## 문서 안내

- [apps/web/README.md](./apps/web/README.md)
- [apps/api/README.md](./apps/api/README.md)
- [apps/report/README.md](./apps/report/README.md)
- [apps/worker/README.md](./apps/worker/README.md)
- [apps/worker/IAM_ONBOARDING.md](./apps/worker/IAM_ONBOARDING.md)
- [contracts/README.md](./contracts/README.md)
- [docs/TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md)

## 이미지 빌드와 배포

이미지 빌드 workflow는 `.github/workflows/deploy-app.yml`에 있습니다.

- `dndn-prd-web`
- `dndn-prd-api`
- `dndn-prd-worker`
- `dndn-prd-report`

기본 ECR registry:

- `387721658341.dkr.ecr.ap-northeast-2.amazonaws.com`

`main` 브랜치 push 또는 수동 `workflow_dispatch`로 앱별 빌드가 실행되고, 성공 시 `DnDn-Infra`의 GitOps 이미지 태그도 함께 갱신합니다.

## 이 레포가 하는 일

- 애플리케이션 코드 관리
- 로컬 개발과 테스트
- Dockerfile 관리
- GitHub Actions 기반 이미지 빌드
- ECR 푸시

## 이 레포가 하지 않는 일

- Helm/Kustomize 템플릿 관리
- Argo CD 애플리케이션 정의
- 환경별 Secret/Config/Ingress 관리
- EKS 직접 배포 운영
