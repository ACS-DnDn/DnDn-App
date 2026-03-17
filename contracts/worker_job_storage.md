# Worker Job Storage Design

이 문서는 worker 실행 상태를 플랫폼 저장소(RDS 기준)에 어떻게 기록할지 정의합니다.

목표:
- 멀티 pod 환경에서 같은 `run_id` 중복 실행 방지
- Producer / Worker / API / 운영 시스템이 같은 실행 상태를 공유
- `job_status.schema.json` 계약을 실제 저장 구조와 연결

---

## 1. 저장소 역할

worker 실행 상태의 source of truth는 단일 저장소가 가져야 합니다.
현재 플랫폼 구조에서는 RDS를 기준 저장소로 두는 것을 권장합니다.

이 저장소는 아래를 담당합니다.

- `run_id` 기준 중복 실행 방지
- 현재 상태 추적
- retryable 실패 추적
- 어떤 worker가 job을 점유했는지 추적
- 성공 시 생성된 source json 메타 연결

---

## 2. 권장 테이블: `worker_jobs`

예시 DDL:

```sql
CREATE TABLE IF NOT EXISTS worker_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'worker job 고유 ID',
    run_id VARCHAR(128) NOT NULL COMMENT '플랫폼 전역 dedupe 기준 ID',
    job_type VARCHAR(20) NOT NULL COMMENT 'WEEKLY 또는 EVENT',
    status VARCHAR(20) NOT NULL COMMENT 'QUEUED, RUNNING, SUCCEEDED, FAILED',
    attempt INT NOT NULL DEFAULT 0 COMMENT '실행 시작 시 증가하는 시도 횟수',
    retryable BOOLEAN NULL COMMENT '재시도 가능 여부',
    already_processed BOOLEAN NOT NULL DEFAULT FALSE COMMENT '이미 처리된 run_id 여부',
    error_code VARCHAR(64) NULL COMMENT '실패 시 표준 에러 코드',
    message TEXT NULL COMMENT '디버깅용 상태 메시지',
    executor_id VARCHAR(128) NULL COMMENT 'worker pod/container 식별자',
    source_json_s3_key VARCHAR(1024) NULL COMMENT '성공 시 생성된 canonical/event json S3 key',
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'job 생성 시각',
    started_at TIMESTAMP NULL DEFAULT NULL COMMENT 'worker 실행 시작 시각',
    finished_at TIMESTAMP NULL DEFAULT NULL COMMENT 'worker 실행 종료 시각',
    UNIQUE KEY uk_worker_jobs_run_id (run_id),
    CONSTRAINT chk_worker_jobs_type
        CHECK (job_type IN ('WEEKLY', 'EVENT')),
    CONSTRAINT chk_worker_jobs_status
        CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED'))
) ENGINE=InnoDB COMMENT='worker 실행 상태 및 멱등성 관리 테이블';
```

설명:
- `run_id` 는 전역 멱등성 기준입니다
- `job_type`, `status` 는 `job_status.schema.json` 의 enum과 동일한 값을 DB 제약으로 강제합니다
- `attempt` 는 실제 실행을 점유할 때마다 증가하는 시도 횟수입니다
- `executor_id` 는 어떤 pod가 job을 점유했는지 추적합니다
- `source_json_s3_key` 는 성공 후 `source_jsons` 와 연결할 때 사용합니다

---

## 3. 상태 전이

권장 상태 전이:

```text
QUEUED -> RUNNING -> SUCCEEDED
QUEUED -> RUNNING -> FAILED
FAILED(retryable=true) -> RUNNING
SUCCEEDED -> SUCCEEDED (중복 run_id 재수신 시 already_processed=true)
```

원칙:
- `RUNNING` 인 job은 다른 worker가 다시 실행하지 않습니다
- `SUCCEEDED` 인 `run_id` 는 중복 수신 시 재실행하지 않습니다
- `FAILED` 인 job은 `retryable` 기준으로 재시도 여부를 판단합니다

---

## 4. 역할별 책임

먼저 용어를 정리하면:

- `Job Producer` 는 별도 서버 이름이 아니라 **worker job 등록 역할 이름**입니다
- 현재 구현 기준에서는 **API가 이 역할을 담당**합니다
- Scheduler / Event trigger handler 는 필요 시 API의 job 생성 경로를 호출하는 방식으로 연동합니다

즉, 현재 구조를 가장 단순하게 표현하면 아래와 같습니다.

- API = job registration 주체
- Worker = job execution 주체
- Report / 후속 시스템 = 성공 결과 소비 주체

### 4-1. Job Producer
Job Producer는 worker job 등록을 시작하는 역할입니다.

가능한 producer:
- API
- Scheduler
- Event trigger handler

책임:
- `run_id` 생성 또는 검증
- `worker_jobs.status = QUEUED` row 생성
- payload에 같은 `run_id`를 넣어 SQS publish

중복 등록 원칙:
- `run_id` 또는 별도 dedupe 기준으로 기존 row가 이미 존재하면 새 row를 만들지 않습니다
- 중복 등록이 감지되면 SQS에 다시 publish 하지 않고 기존 `run_id` 와 상태를 반환합니다
- 같은 요청에 대해 producer마다 다른 등록 결과가 나오지 않도록 공용 registration 규칙을 사용해야 합니다

중요:
- producer는 여러 개일 수 있지만, job 등록 규칙은 하나여야 합니다
- 즉 각 producer가 직접 제각각 구현하기보다 공용 job registration 경로를 공유하는 것이 좋습니다

현재 구현 기준 권장:
- 별도 Job Producer 서버를 두지 않고 API가 단일 job registration 주체를 담당합니다
- Scheduler와 Event trigger handler는 직접 DB/SQS를 다루기보다 API의 job 생성 경로를 호출합니다

### 4-2. API
API는 현재 구현에서 job registration을 담당하는 주체이자 상태 조회 주체입니다.

책임:
- 즉시 실행 요청을 producer 규칙에 맞게 등록
- Scheduler / Event trigger handler가 위임한 job 생성 요청 처리
- `run_id` 생성
- `worker_jobs` row 생성
- payload 생성 및 SQS publish
- `worker_jobs` 상태 조회 API 제공
- 프론트/운영 시스템에 현재 상태 전달

등록 규칙:
- `worker_jobs` 생성이 성공한 경우에만 SQS publish 를 수행합니다
- `uk_worker_jobs_run_id` 충돌 시에는 새 publish 대신 기존 job 상태를 조회해 반환합니다
- 즉, API는 "새 job 생성" 또는 "기존 job 반환" 중 하나로 동작해야 합니다

### 4-3. Worker
- 메시지 수신 후 `run_id` 로 상태 조회
- `RUNNING` 또는 `SUCCEEDED` 면 중복 실행 차단
- 실행 점유 성공 시 `RUNNING` 으로 전이
- 종료 시 `SUCCEEDED` / `FAILED` 로 업데이트

점유 전이는 원자적으로 처리해야 합니다.
멀티 pod 환경에서는 단순 조회 후 업데이트만으로는 동시 점유 경쟁이 발생할 수 있으므로,
아래처럼 조건부 업데이트 또는 `SELECT ... FOR UPDATE` 기반 규칙을 사용해야 합니다.

예시:

```sql
UPDATE worker_jobs
SET
    status = 'RUNNING',
    executor_id = :executor_id,
    started_at = NOW(),
    attempt = attempt + 1
WHERE run_id = :run_id
  AND status IN ('QUEUED', 'FAILED')
  AND (status <> 'FAILED' OR retryable = TRUE);
```

원칙:
- `rows_affected = 1` 인 경우에만 점유 성공으로 간주합니다
- `rows_affected = 0` 이면 이미 다른 worker가 점유했거나 재시도 불가 상태로 간주합니다
- 점유 성공 이후에만 실제 AWS 수집과 S3 업로드를 시작합니다
- `attempt` 는 `QUEUED` 생성 시점이 아니라 `RUNNING` 점유 성공 시점에 증가합니다

### 4-4. Report / 후속 시스템
- `SUCCEEDED` 상태와 `source_json_s3_key` 를 기준으로 후속 처리

---

## 5. source_jsons 와의 관계

`worker_jobs` 와 `source_jsons` 는 역할이 다릅니다.

- `worker_jobs`
  - 실행 상태 추적
  - 멱등성 판단
  - retry / failure 추적

- `source_jsons`
  - 실행 성공 후 생성된 결과 JSON 메타 저장

권장 흐름:

1. API가 `run_id` 를 만든다
2. API가 `worker_jobs` row 생성 (`QUEUED`)
3. `run_id` 중복이 없을 때만 API가 같은 `run_id` 를 포함한 payload를 SQS에 publish
4. worker가 실행 후 `SUCCEEDED` 로 업데이트
5. 성공 시 `source_jsons` row 생성
6. `worker_jobs.source_json_s3_key` 와 `source_jsons.source_json_s3_key` 를 맞춰 연결

---

## 6. 멀티 pod 기준에서 중요한 이유

로컬 파일 기반 멱등성만 있으면 pod A와 pod B가 서로 상태를 모릅니다.
반면 `worker_jobs` 를 공용 상태판으로 쓰면 모든 pod가 같은 기준을 봅니다.

즉:
- pod A가 `RUNNING` 기록
- pod B가 같은 `run_id` 수신
- DB 조회 후 중복 실행 차단

이 구조가 멀티 pod 환경의 최소 멱등성 기반입니다.
