# DnDn-App

DnDn-App은 DnDn 서비스의 애플리케이션 레포지토리입니다.
이 레포는 `web`, `api`, `worker`, `report` 코드를 소유하며, 각 앱의 로컬 실행, 테스트, 컨테이너 이미지 빌드, ECR push까지를 담당합니다.

실제 Kubernetes 배포 정의와 환경별 운영 설정은 이 레포가 아니라 `DnDn-Infra`에서 관리합니다.

## 구성

| 앱 | 역할 | 기술 스택 | 이미지 |
| --- | --- | --- | --- |
| `apps/web` | 사용자용 프론트엔드 | React, TypeScript, Vite | `dndn-prd-web` |
| `apps/api` | 인증, 문서, 워크스페이스, 리포트 설정 API | FastAPI, SQLAlchemy, MariaDB | `dndn-prd-api` |
| `apps/worker` | AWS 데이터 수집 및 정규화 엔진 | Python, boto3 | `dndn-prd-worker` |
| `apps/report` | 보고서/계획서 생성 API 및 worker | FastAPI, Python | `dndn-prd-report` |

`report`는 이미지 1개를 빌드하고, 배포 시 `report-api`, `report-worker`가 서로 다른 command로 나눠 사용하는 구조를 전제로 합니다.

## 레포 책임 범위

DnDn-App이 담당하는 일:

- 애플리케이션 코드 관리
- 로컬 개발 및 테스트
- Dockerfile 관리
- GitHub Actions 기반 이미지 빌드
- ECR push

DnDn-App이 담당하지 않는 일:

- Helm / Kustomize 차트 관리
- Argo CD 애플리케이션 정의
- 환경별 values
- Secret / Config / Ingress 관리
- EKS 직접 배포

위 항목은 `DnDn-Infra`의 책임입니다.

## 관련 레포

- `DnDn-App`: 애플리케이션 코드 + 이미지 발행
- `DnDn-HR`: HR 프론트 코드 + 이미지 발행
- `DnDn-Infra`: Terraform, GitOps, Argo CD, EKS 배포 정의

운영 흐름은 다음과 같습니다.

1. `DnDn-App` 또는 `DnDn-HR`가 이미지를 빌드하고 ECR에 push
2. `DnDn-Infra`가 이미지 태그를 반영
3. Argo CD가 EKS에 동기화

## 디렉터리 구조

```text
.
├── apps/
│   ├── api/        # FastAPI 백엔드
│   ├── report/     # 보고서/계획서 생성 서비스
│   ├── web/        # 사용자 웹 프론트엔드
│   └── worker/     # AWS 수집 및 정규화 엔진
├── contracts/      # worker/report 공통 payload, schema
├── docs/           # 트러블슈팅 및 보조 문서
└── .github/
    └── workflows/
        └── deploy-app.yml
```

추가 문서:

- [worker README](./apps/worker/README.md)
- [worker IAM onboarding](./apps/worker/IAM_ONBOARDING.md)
- [payload / schema 안내](./contracts/README.md)

## 로컬 개발

### 1. Web

```bash
cd apps/web
npm ci
npm run dev
```

프로덕션 빌드:

```bash
cd apps/web
npm run build
```

### 2. API

필수 환경 변수 예시는 [apps/api/.env.example](./apps/api/.env.example)에 있습니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
PYTHONPATH=. uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8001 --reload
```

### 3. Report

환경 변수 예시는 [apps/report/.env.example](./apps/report/.env.example)에 있습니다.

```bash
cd apps/report
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Worker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e apps/worker
python apps/worker/tools/run_payload.py --payload /path/to/payload.json --repo-root . --out /tmp/dndn-out
```

상세 실행 방법은 [apps/worker/README.md](./apps/worker/README.md)를 참고합니다.

## 이미지 발행

앱 이미지 발행 workflow는 [deploy-app.yml](./.github/workflows/deploy-app.yml)에 정의되어 있습니다.

현재 발행 대상 이미지:

- `dndn-prd-web`
- `dndn-prd-api`
- `dndn-prd-worker`
- `dndn-prd-report`

기본 ECR registry:

- `387721658341.dkr.ecr.ap-northeast-2.amazonaws.com`

예시:

- `387721658341.dkr.ecr.ap-northeast-2.amazonaws.com/dndn-prd-web:<git-sha>`
- `387721658341.dkr.ecr.ap-northeast-2.amazonaws.com/dndn-prd-api:<git-sha>`
- `387721658341.dkr.ecr.ap-northeast-2.amazonaws.com/dndn-prd-worker:<git-sha>`
- `387721658341.dkr.ecr.ap-northeast-2.amazonaws.com/dndn-prd-report:<git-sha>`

## 운영 전제

GitHub Actions에서 이미지 발행을 수행하려면 AWS 계정에 다음 설정이 필요합니다.

- GitHub Actions OIDC provider
- `aws-actions/configure-aws-credentials`가 AssumeRole 할 수 있는 IAM role
- ECR push 권한

즉, 이 레포의 workflow가 정상 동작하려면 앱 코드 외에도 AWS IAM / OIDC 설정이 함께 준비되어 있어야 합니다.
