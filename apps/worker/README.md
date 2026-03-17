# Worker (apps/worker)

DnDn의 **Worker** 는 AWS 계정에서 변경 이력과 리소스 상태를 수집하고, 이를 **표준 JSON 결과물**로 정규화하여 S3에 저장하는 백엔드 실행 엔진입니다.

현재 구조에서 Worker는 단순 라이브러리가 아니라,
**신호(payload)를 받으면 최종 결과 JSON을 생산하는 독립 실행 서비스**를 목표로 합니다.

쉽게 말하면 Worker는 다음 역할을 합니다.

- **입력**: `contracts/payload/*.json` 형태의 작업 요청(payload)
- **수집**: CloudTrail, AWS Config, 이벤트 트리거(AWS Health / Security Hub 등) 관련 정보
- **정규화**: `canonical.json`(WEEKLY), `event.json`(EVENT)
- **저장**: `raw/`, `normalized/` 결과물을 S3에 업로드
- **확장**: AWS Health 기반 이벤트 보강, 주간 운영 점검(advisor checks), Config before/after 보강

---

## 1. 이 폴더가 하는 일

Worker는 DnDn에서 아래 흐름을 담당합니다.

1. API가 Worker payload를 생성하고 전달한다
   스케줄러/EventBridge 계열 트리거는 현재 구현 기준으로 API의 job 생성 경로를 통해 Worker 실행으로 연결된다
2. Worker가 대상 AWS 계정(필요시 AssumeRole)으로 접근
3. CloudTrail / Config / 이벤트 trigger 정보를 수집
4. 결과를 표준 포맷(JSON)으로 정리
5. `raw/`, `normalized/` 산출물을 S3에 저장
6. 이후 B 파트(Report)가 이 JSON과 raw evidence를 사용해 보고서, 계획서, evidence zip을 생성

즉, Worker는 **“수집 → 정규화 → 저장”** 의 중심입니다.
운영에서는 SQS consumer로 계속 실행되고,
로컬에서는 payload 파일 기반으로 동일 로직을 실행합니다.

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

추가로 Worker는 `raw/index.json` 을 생성해서
이번 실행에서 남긴 evidence/normalized 파일 목록과 S3 URI를 inventory 형태로 기록합니다.

---

## 3. 폴더 구조

```text
apps/worker/
  dndn_worker/
    __init__.py
    run_job.py          # Worker 핵심 실행 엔진
    consumer.py         # SQS payload consumer
    s3_uploader.py      # S3 업로드 유틸
  Dockerfile            # Worker consumer container image
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
공용 실행 진입점은 아래 두 함수입니다.

- `run_job_from_payload(payload: dict, ...)`
- `run_job_from_payload_file(path, ...)`

#### `dndn_worker/s3_uploader.py`
로컬 `job_dir` 아래 산출물을 S3로 업로드하는 유틸입니다.

#### `dndn_worker/consumer.py`
SQS 메시지 body를 payload JSON으로 받아 schema 검증 후
`run_job_from_payload(...)` 를 호출하는 운영용 consumer 진입점입니다.

#### `Dockerfile`
`python -m dndn_worker.consumer` 를 기본 진입점으로 실행하는
Worker 컨테이너 이미지 정의입니다.

#### `tools/run_payload.py`
로컬에서 payload 파일 하나로 Worker를 실행할 때 사용합니다.
파일을 읽은 뒤 `run_job_from_payload_file(...)` 만 호출하는 개발/디버깅용 CLI 진입점입니다.

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

EVENT의 `trigger` 는 단순 메타데이터일 수도 있고,
상위 계층이 raw trigger event 자체를 넣어줄 수도 있습니다.
Worker는 가능한 경우 이 trigger 내용을 `raw/trigger/*.json` 으로 저장하고
`meta.trigger.raw_event_s3_uri` 를 결과에 남깁니다.

### 4-2. 에러 모델 / retryable
Worker는 실행 결과와 예외에 `retryable` 기준을 명시합니다.

- 실행 결과: `WorkerExecutionResult`
- 실행 예외: `WorkerExecutionError`

원칙:
- `retryable=False` 이면 consumer는 메시지를 delete
- `retryable=True` 이면 consumer는 메시지를 남겨 재시도
- validation 실패는 `INVALID_PAYLOAD`, `retryable=False`
- S3 업로드 실패는 `S3_PUT_FAILED`, `retryable=True`

### 4-3. SELF 모드
개발 단계에서는 `assume_role.role_arn = "SELF"` 로 두면,
AssumeRole 없이 현재 로컬 AWS 자격증명을 그대로 사용합니다.

이 모드는 다음 상황에서 유용합니다.
- 로컬 개발
- 스키마/정규화 테스트
- 실제 고객 계정 없이 구조 확인

### 4-4. 멱등성 기준
같은 `run_id`가 다시 들어오면 로컬 `out/<run_id>/normalized/{canonical|event}.json` 존재 여부를 먼저 확인합니다.

- 이미 결과 파일이 있으면 재수집하지 않고 `already_processed=True` 로 즉시 반환
- 즉, 동일 worker 인스턴스/볼륨 기준에서는 `run_id` 재처리를 막습니다
- 분산 환경 전역 멱등성(S3/DB 락 기반)은 후속 운영 설계 범위입니다

### 4-5. AssumeRole 모드
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

운영/consumer 경로와 로컬 실행 경로를 같은 코드로 맞추기 위해,
실제 job 실행은 `dndn_worker.run_job.run_job_from_payload(...)` 를 기준으로 두고
파일 기반 실행만 `run_job_from_payload_file(...)` / `tools/run_payload.py` 로 감쌉니다.

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
    index.json
    meta/
      job_payload.json
    cloudtrail/
      lookup_events.jsonl
      event_<event_id>.json
    config/
      <resource_key>/
        history.json
        before.json
        after.json
    advisor/
      ...
    trigger/
      eventbridge.json
      securityhub_finding.json
      aws_health_event.json
  normalized/
    canonical.json   # WEEKLY
    event.json       # EVENT
```

설명:
- `raw/` 는 evidence 원본 보관소입니다.
- `normalized/` 는 report가 바로 읽을 표준 결과물입니다.
- `raw/index.json` 은 이번 실행에서 어떤 파일이 생성됐는지 한 번에 보여주는 inventory 입니다.

### 6-4. SQS consumer 실행
queue message body는 완성된 payload JSON이라고 가정합니다.

```bash
python -m dndn_worker.consumer \
  --queue-url https://sqs.ap-northeast-2.amazonaws.com/123456789012/dndn-worker \
  --repo-root . \
  --out /tmp/dndn-out \
  --once
```

consumer 동작:
- 메시지 수신
- JSON 파싱
- payload schema 검증
- `run_job_from_payload(...)` 호출
- `retryable=False` 결과/예외면 delete
- `retryable=True` 예외면 delete 하지 않고 재시도 대상으로 남김
- 같은 `run_id` 재수신으로 `already_processed=True` 가 오면 delete

### 6-5. 컨테이너 실행
빌드:

```bash
docker build -f apps/worker/Dockerfile -t dndn-worker:local .
```

실행 예시:

```bash
docker run --rm \
  -e AWS_REGION=ap-northeast-2 \
  -e DNDN_WORKER_QUEUE_URL=https://sqs.ap-northeast-2.amazonaws.com/123456789012/dndn-worker \
  -e DNDN_WORKER_MAX_EVENTS=500 \
  -e DNDN_WORKER_WAIT_TIME_SECONDS=20 \
  -e DNDN_WORKER_MAX_MESSAGES=1 \
  -v "$HOME/.aws:/home/worker/.aws:ro" \
  dndn-worker:local
```

기본 entrypoint:

```bash
python -m dndn_worker.consumer --repo-root /app --out /tmp/dndn-out
```

한 번만 poll 하고 종료하려면:

```bash
docker run --rm \
  -e AWS_REGION=ap-northeast-2 \
  -e DNDN_WORKER_QUEUE_URL=https://sqs.ap-northeast-2.amazonaws.com/123456789012/dndn-worker \
  -v "$HOME/.aws:/home/worker/.aws:ro" \
  dndn-worker:local \
  --once
```

### 6-6. 운영 환경 변수
consumer 실행 시 주로 아래 env를 사용합니다.

- `DNDN_WORKER_QUEUE_URL`: SQS queue URL. CLI `--queue-url` 보다 기본값으로 사용
- `DNDN_WORKER_MAX_EVENTS`: job당 최대 CloudTrail event 수
- `DNDN_WORKER_WAIT_TIME_SECONDS`: SQS long polling wait time
- `DNDN_WORKER_MAX_MESSAGES`: poll당 최대 수신 메시지 수
- `AWS_REGION` 또는 `AWS_DEFAULT_REGION`: boto3 기본 리전
- AWS credential chain 관련 env 또는 IAM role: 컨테이너/런타임에서 boto3가 사용하는 기본 인증 정보

### 6-7. 재시도 정책 운영 가이드
현재 consumer는 worker의 `retryable` 기준에 맞춰 메시지 삭제 여부를 결정합니다.

- `retryable=False`
  - 예: `INVALID_PAYLOAD`, `ASSUME_ROLE_FAILED`
  - consumer는 메시지를 delete
- `retryable=True`
  - 예: `S3_PUT_FAILED`, 일시적 AWS/network 오류
  - consumer는 메시지를 남겨 재시도
- `already_processed=True`
  - 같은 `run_id`가 이미 처리된 상태
  - consumer는 메시지를 delete

운영 권장:

- SQS redrive policy(DLQ)로 최대 수신 횟수 제한
- visibility timeout은 평균 job 실행 시간보다 길게 설정
- `DNDN_WORKER_MAX_MESSAGES=1` 부터 시작해 안정화 후 조정
- retryable 실패는 CloudWatch/SQS metric 기반 알림 연결

### 6-8. 실제 AWS 계정으로 SELF 테스트
고객 계정 AssumeRole 전 단계에서 Worker 기능 자체를 검증하려면,
현재 로그인된 AWS 계정을 수집 대상로 사용하고 S3도 DnDn 쪽 테스트 버킷으로 두는 방식이 가장 단순합니다.

검증 순서:
1. 현재 AWS 자격증명으로 STS 호출이 되는지 확인
2. 현재 AWS 자격증명으로 CloudTrail 조회가 되는지 확인
3. `role_arn=SELF` payload로 WEEKLY 실행
4. `role_arn=SELF` payload로 EVENT 실행
5. 로컬 산출물과 S3 업로드 결과 확인

예시 명령:
```bash
cd /Users/mh/Desktop/DnDn-App
source .venv/bin/activate
export PYTHONPATH=apps/worker

python apps/worker/tools/smoke_assume_role.py --role-arn SELF
python apps/worker/tools/smoke_cloudtrail.py --role-arn SELF --region ap-northeast-2 --hours 24 --max 5

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

cat >/tmp/worker-weekly.json <<EOF
{
  "account_id": "${ACCOUNT_ID}",
  "assume_role": {
    "external_id": "local-test",
    "role_arn": "SELF"
  },
  "regions": ["ap-northeast-2"],
  "rule_set_version": "eks-mvp-0.1",
  "run_id": "manual-weekly-test-001",
  "s3": {
    "bucket": "dndn-data-dev-20260304",
    "prefix": "manual-tests/weekly/manual-weekly-test-001"
  },
  "time_range": {
    "start": "2026-03-01T00:00:00+09:00",
    "end": "2026-03-08T00:00:00+09:00",
    "timezone": "Asia/Seoul"
  },
  "type": "WEEKLY"
}
EOF

python apps/worker/tools/run_payload.py \
  --payload /tmp/worker-weekly.json \
  --repo-root . \
  --out /tmp/dndn-out \
  --max-events 20

cat >/tmp/worker-event.json <<EOF
{
  "account_id": "${ACCOUNT_ID}",
  "assume_role": {
    "external_id": "local-test",
    "role_arn": "SELF"
  },
  "event_time": "2026-03-11T10:30:00+09:00",
  "hint": {
    "resource": {
      "region": "ap-northeast-2",
      "resource_id": "my-eks-cluster",
      "resource_type": "AWS::EKS::Cluster"
    }
  },
  "regions": ["ap-northeast-2"],
  "rule_set_version": "eks-mvp-0.1",
  "run_id": "manual-event-test-001",
  "s3": {
    "bucket": "dndn-data-dev-20260304",
    "prefix": "manual-tests/event/manual-event-test-001"
  },
  "trigger": {
    "event_id": "manual-event-001",
    "source": "EVENTBRIDGE"
  },
  "type": "EVENT",
  "window_minutes": 60
}
EOF

python apps/worker/tools/run_payload.py \
  --payload /tmp/worker-event.json \
  --repo-root . \
  --out /tmp/dndn-out \
  --max-events 20

aws s3 ls s3://dndn-data-dev-20260304/manual-tests/weekly/manual-weekly-test-001/ --recursive
aws s3 ls s3://dndn-data-dev-20260304/manual-tests/event/manual-event-test-001/ --recursive
```

이 테스트로 확인되는 것:
- 현재 AWS 자격증명 기반 `SELF` 실행 가능 여부
- CloudTrail 실제 조회 가능 여부
- Worker 정규화 결과 생성 여부
- 로컬 raw/normalized 산출물 생성 여부
- DnDn S3 버킷 업로드 여부

이 테스트로 확인되지 않는 것:
- 고객 계정 AssumeRole trust policy
- 고객 계정 권한 정책
- 고객 환경별 리전/서비스 차이

즉, 이 절차는 **"내 계정으로 Worker 자체가 실제로 도는지"** 를 보는 실동작 테스트입니다.

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

특히 `meta.evidence` 에는 다음 pointer가 들어갑니다.
- `raw_prefix_s3_uri`
- `normalized_prefix_s3_uri`
- `job_payload_s3_uri`
- `index_s3_uri`

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

### 7-6. evidence를 어디서 보면 되나
Worker evidence는 한 필드에 전부 모이지 않고 목적별로 나뉩니다.

- 실행 전체 artifact 위치: `meta.evidence`
- trigger 원문 위치: `meta.trigger.raw_event_s3_uri`
- CloudTrail raw 위치: `events[].raw`
- Config snapshot raw 위치: `resources[].config.before_s3_uri`, `after_s3_uri`, `extensions.history_s3_uri`
- advisor raw 위치: `extensions.advisor_checks[].evidence`

사람이 한 번에 보기 가장 쉬운 entrypoint는 `raw/index.json` 입니다.

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

운영용 온보딩 절차와 권한 표는 별도 문서에 정리했습니다.
- [IAM_ONBOARDING.md](/Users/mh/Desktop/DnDn-App/apps/worker/IAM_ONBOARDING.md)

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

### 11-5. evidence가 어디 있는지 한 번에 안 보인다
정상입니다. Worker는 raw evidence를 목적별 폴더에 분산 저장하고,
normalized JSON에는 pointer만 남깁니다.

빠르게 확인하는 순서:
1. `meta.evidence.index_s3_uri`
2. `meta.trigger.raw_event_s3_uri`
3. `events[].raw`
4. `resources[].config`

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

### Worker 실동작만 빠르게 확인하고 싶다면
1. `smoke_assume_role.py --role-arn SELF`
2. `smoke_cloudtrail.py --role-arn SELF`
3. 위 `6-8. 실제 AWS 계정으로 SELF 테스트` 절차 실행

### 컨테이너 consumer가 목적이면
1. `docker build -f apps/worker/Dockerfile -t dndn-worker:local .`
2. `DNDN_WORKER_QUEUE_URL` 설정
3. `python -m dndn_worker.consumer` 또는 Docker 실행 예시 사용

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
