# Worker (apps/worker)

DnDn의 **Worker** 는 AWS 계정에서 변경 이력과 리소스 상태를 수집하고, 이를 **표준 JSON 결과물**로 정규화하여 S3에 저장하는 백엔드 실행 엔진입니다.

쉽게 말하면 Worker는 다음 역할을 합니다.

- **입력**: `contracts/payload/*.json` 형태의 작업 요청(payload)
- **수집**: CloudTrail, AWS Config, 이벤트 트리거(AWS Health / Security Hub 등) 관련 정보
- **정규화**: `canonical.json`(WEEKLY), `event.json`(EVENT)
- **저장**: `raw/`, `normalized/` 결과물을 S3에 업로드
- **확장**: AWS Health 기반 이벤트 보강, 주간 운영 점검(advisor checks), Config before/after 보강

---

## 1. 이 폴더가 하는 일

Worker는 DnDn에서 아래 흐름을 담당합니다.

1. API/스케줄러/EventBridge가 Worker에 payload를 전달
2. Worker가 대상 AWS 계정(필요시 AssumeRole)으로 접근
3. CloudTrail / Config / 이벤트 trigger 정보를 수집
4. 결과를 표준 포맷(JSON)으로 정리
5. `raw/`, `normalized/` 산출물을 S3에 저장
6. 이후 B 파트(Report)가 이 JSON과 raw evidence를 사용해 보고서, 계획서, evidence zip을 생성

즉, Worker는 **“수집 → 정규화 → 저장”** 의 중심입니다.

---

## 2. 현재 Worker가 지원하는 기능

### 2-1. 기본 실행 모드
- **WEEKLY**
  - 일정 기간(보통 지난 1주)의 변경 이력 수집
  - 결과: `canonical.json`
- **EVENT**
  - 특정 이벤트 시점(`event_time ± window_minutes`) 중심 수집
  - 결과: `event.json`

### 2-2. AWS 데이터 수집
- CloudTrail `LookupEvents`
- AWS Config recorder 상태 확인
- AWS Config history 기반 리소스별 before/after 보강(best-effort)

### 2-3. 이벤트 소스 확장
현재 EVENT 계열은 아래 소스를 다룰 수 있도록 확장되어 있습니다.

- `MANUAL`
- `SECURITYHUB`
- `AWS_HEALTH`

특히 AWS Health 이벤트는 다음 정보를 `extensions`에 정리합니다.

- `extensions.event_origin`
- `extensions.aws_health`
- `extensions.actionability`

이를 통해 **“이 이벤트가 Terraform 조치 후보인지”** 까지 Worker 단계에서 판단할 수 있습니다.

### 2-4. 주간 운영 점검(Advisor Checks)
WEEKLY 실행 시 아래와 같은 운영 점검 결과를 `extensions.advisor_checks[]` 로 생성할 수 있습니다.

- 미사용 Elastic IP
- 미연결 EBS 볼륨
- RDS 백업 미설정
- RDS Multi-AZ 미설정

그리고 실행 상태와 요약은 아래에 기록됩니다.

- `extensions.advisor_collection_status`
- `extensions.advisor_rollup`

### 2-5. 저장 방식
Worker는 로컬 산출물을 만든 뒤 아래처럼 S3에 업로드합니다.

- `raw/`
- `normalized/`

예시:
- `s3://<bucket>/<prefix>/raw/...`
- `s3://<bucket>/<prefix>/normalized/canonical.json`
- `s3://<bucket>/<prefix>/normalized/event.json`

---

## 3. 폴더 구조

```text
apps/worker/
  dndn_worker/
    __init__.py
    run_job.py          # Worker 핵심 실행 엔진
    s3_uploader.py      # S3 업로드 유틸
  tools/
    run_payload.py      # 로컬 payload 실행 도구
    smoke_assume_role.py
    smoke_cloudtrail.py
    render_iam_templates.py
  iam_templates/
    customer_trust_policy.json
    customer_permissions_policy.json
  pyproject.toml
  requirements.txt
  README.md
```

### 파일 설명
#### `dndn_worker/run_job.py`
Worker 핵심 로직입니다. 실제 수집/정규화/스키마 검증/S3 저장을 담당합니다.

#### `dndn_worker/s3_uploader.py`
로컬 `job_dir` 아래 산출물을 S3로 업로드하는 유틸입니다.

#### `tools/run_payload.py`
로컬에서 payload 파일 하나로 Worker를 실행할 때 사용합니다.
개발/디버깅용 진입점입니다.

#### `tools/smoke_assume_role.py`
AssumeRole이 실제로 되는지 빠르게 확인하는 도구입니다.

#### `tools/smoke_cloudtrail.py`
CloudTrail 조회가 실제로 가능한지 빠르게 확인하는 도구입니다.

#### `tools/render_iam_templates.py`
고객사 온보딩용 IAM 템플릿의 placeholder를 실제 값(`principal ARN`, `external_id`)으로 치환합니다.

#### `iam_templates/`
고객사 계정 연동(AssumeRole)에 필요한 최소 IAM 템플릿입니다.

---

## 4. 실행에 필요한 개념

### 4-1. payload
Worker는 항상 payload(JSON)를 입력으로 받습니다.
payload 스펙은 `contracts/payload/job_payload.schema.json` 을 따릅니다.

핵심 필드:
- `type`: `WEEKLY | EVENT`
- `account_id`
- `regions`
- `assume_role`
- `s3`
- WEEKLY: `time_range`
- EVENT: `event_time`, `window_minutes`, `trigger`

### 4-2. SELF 모드
개발 단계에서는 `assume_role.role_arn = "SELF"` 로 두면,
AssumeRole 없이 현재 로컬 AWS 자격증명을 그대로 사용합니다.

이 모드는 다음 상황에서 유용합니다.
- 로컬 개발
- 스키마/정규화 테스트
- 실제 고객 계정 없이 구조 확인

### 4-3. AssumeRole 모드
운영/실전에서는 보통 고객 계정의 Read-only Role을 AssumeRole 해서 수집합니다.

Worker는 구조적으로 아래 두 세션을 분리합니다.

- **collector session**: 고객 계정에서 CloudTrail/Config를 읽는 세션
- **storage session**: 우리(DnDn) 계정 S3에 쓰는 세션

즉, **고객 계정 읽기와 우리 S3 저장을 분리**해서 운영할 수 있게 되어 있습니다.

---

## 5. 로컬 개발 시작 방법

### 5-1. 설치
```bash
cd <repo-root>
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e apps/worker
```

### 5-2. import 확인
```bash
python - <<'PY'
import dndn_worker
print(dndn_worker.__file__)
PY
```

### 5-3. AWS 자격증명 확인
```bash
aws sts get-caller-identity
```

---

## 6. 가장 자주 쓰는 실행 방법

### 6-1. WEEKLY 실행
```bash
python apps/worker/tools/run_payload.py \
  --payload /tmp/payload.weekly.json \
  --repo-root . \
  --out /tmp/dndn-out \
  --max-events 500
```

### 6-2. EVENT 실행
```bash
python apps/worker/tools/run_payload.py \
  --payload /tmp/payload.event.json \
  --repo-root . \
  --out /tmp/dndn-out \
  --max-events 200
```

### 6-3. 결과물
로컬에서는 대략 이런 구조로 생성됩니다.

```text
/tmp/dndn-out/<run_id>/
  raw/
    ...
  normalized/
    canonical.json   # WEEKLY
    event.json       # EVENT
```

---

## 7. Worker 결과물 구조

### 7-1. normalized 결과
- WEEKLY → `canonical.json`
- EVENT → `event.json`

### 7-2. 주요 필드
- `meta`
- `collection_status`
- `events`
- `resources`
- `extensions`

### 7-3. collection_status
각 단계의 수집 상태를 나타냅니다.

예:
- `assume_role`
- `cloudtrail`
- `config`
- `normalized`

상태 예:
- `OK`
- `NA`
- `FAILED`

### 7-4. resources
보고서 생성(B 파트)이 가장 많이 활용하는 단위입니다.
이벤트를 리소스 기준으로 묶어두고, 가능하면 Config 정보를 붙입니다.

### 7-5. extensions
contracts core를 깨지 않기 위해 확장 기능은 `extensions` 아래에 둡니다.

예:
- `event_origin`
- `aws_health`
- `actionability`
- `advisor_collection_status`
- `advisor_checks`
- `advisor_rollup`

---

## 8. 이벤트 소스(AWS Health / Security Hub)

### 8-1. AWS Health
AWS Health 이벤트는 EventBridge payload를 기반으로 정규화됩니다.

Worker는 Health payload에서 다음을 읽습니다.
- `trigger.detail_type`
- `trigger.logical_source`
- `trigger.health`
- `trigger.resources`
- `trigger.health.affectedEntities`

그리고 결과 JSON에 다음을 넣습니다.
- `extensions.event_origin.kind = AWS_HEALTH`
- `extensions.aws_health`
- `extensions.actionability`

### 8-2. Security Hub
Security Hub도 EVENT 루트에서 다룰 수 있도록 설계되어 있습니다.
Worker는 trigger/finding 정보를 기반으로 resource ref를 보강하고,
필요한 경우 보고서/계획서 연결을 쉽게 할 수 있게 확장 필드를 유지합니다.

---

## 9. 주간 운영 점검(advisor checks)

WEEKLY 실행 시 Worker는 주간 점검 항목을 수집해서 `extensions.advisor_checks[]`에 넣을 수 있습니다.

현재 기본 항목:
- 미사용 EIP
- 미연결 EBS
- RDS 백업 미설정
- RDS Multi-AZ 미설정

이 체크들은 “항상 결과가 있어야” 하는 건 아닙니다.
예를 들어 실제로 문제 리소스가 없으면:
- `advisor_checks = []`
- `advisor_rollup.total_checks = 0`

이어도 정상입니다.

중요한 것은:
- 체크가 실행되었는지
- `advisor_collection_status`가 채워졌는지
- raw evidence가 남았는지
입니다.

---

## 10. IAM 템플릿 / 온보딩

Worker는 고객사 계정 연동을 위해 AssumeRole을 사용합니다.
이를 위해 `iam_templates/` 와 `render_iam_templates.py` 를 제공합니다.

### 10-1. 템플릿 렌더링
```bash
python apps/worker/tools/render_iam_templates.py \
  --dndn-principal-arn arn:aws:iam::123456789012:role/DnDnWorkerRole \
  --external-id dndn-tenant-abc
```

출력:
- `out/iam_rendered/customer_trust_policy.rendered.json`
- `out/iam_rendered/customer_permissions_policy.rendered.json`

### 10-2. 운영 원칙
- 고객 계정 Role은 **읽기 전용 최소 권한**
- 우리 S3 업로드는 **고객 Role 권한이 아니라 DnDn 쪽 세션으로 수행**
- ExternalId 기반 AssumeRole로 confused deputy 리스크를 줄임

---

## 11. 자주 발생하는 문제

### 11-1. `ModuleNotFoundError: dndn_worker`
대부분 editable install이 안 되어 있을 때 발생합니다.

해결:
```bash
pip install -e apps/worker
```

### 11-2. `datetime is not JSON serializable`
CloudTrail/EventTime 등을 raw JSON으로 쓸 때 자주 발생합니다.
현재 Worker에는 `_json_default()`가 들어 있어 이 문제를 처리합니다.

### 11-3. Config가 항상 NA로 나온다
계정/리전에 AWS Config recorder가 꺼져 있으면 정상입니다.
이 경우 Worker는 실패 대신:
- `NA(SERVICE_DISABLED)`
로 처리합니다.

### 11-4. AssumeRole은 되는데 S3 업로드가 안 된다
고객 Role과 우리 S3 저장 세션이 분리되지 않았을 때 자주 생깁니다.
현재 Worker는 collector/storage session을 분리하는 구조를 사용합니다.

---

## 12. 팀 연동 포인트

### B(Report)
B는 Worker 결과 중 주로 아래를 사용합니다.
- `resources[]`
- `events[]`
- `extensions.aws_health`
- `extensions.actionability`
- `extensions.advisor_checks`
- `resources[].config`

### C(API/Front)
C는 Worker 실행에 필요한 payload를 생성합니다.
핵심 필드:
- `type`
- `linked account 정보(account_id / role_arn / external_id)`
- `time_range` 또는 `event_time / trigger`

### D(Infra)
D는 EventBridge, IAM, 배포, 저장 구조와 연동합니다.
특히:
- AssumeRole principal ARN
- ExternalId
- S3 저장 구조
를 같이 맞춰야 합니다.

---

## 13. 이 README를 보고 어디서 시작하면 되나

### 로컬 디버깅이 목적이면
1. `pip install -e apps/worker`
2. `aws sts get-caller-identity`
3. `run_payload.py`로 EVENT 또는 WEEKLY 실행

### AssumeRole 검증이 목적이면
1. `smoke_assume_role.py`
2. `smoke_cloudtrail.py`
3. `run_payload.py` with role_arn

### 주간 점검 확인이 목적이면
1. WEEKLY payload 생성
2. `run_payload.py`
3. `extensions.advisor_checks` 확인

---

## 14. 마지막 정리

이 Worker는 현재 DnDn에서 다음을 담당합니다.

- 변경 이력 수집
- 이벤트 보고서용 정규화
- 주간 보고서용 정규화
- AWS Health / SecurityHub 같은 이벤트 소스 보강
- 운영 점검(advisor checks)
- S3 저장
- AssumeRole 기반 고객 계정 수집
