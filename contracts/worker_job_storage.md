# Worker Job Storage Design

이 문서는 worker 실행 상태를 플랫폼 저장소(RDS 기준)에 어떻게 기록할지 정의합니다.

목표:
- 멀티 pod 환경에서 같은 `run_id` 중복 실행 방지
- API / Worker / 운영 시스템이 같은 실행 상태를 공유
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
    attempt INT NOT NULL DEFAULT 1 COMMENT '현재 실행 시도 횟수',
    retryable BOOLEAN NULL COMMENT '재시도 가능 여부',
    already_processed BOOLEAN NOT NULL DEFAULT FALSE COMMENT '이미 처리된 run_id 여부',
    error_code VARCHAR(64) NULL COMMENT '실패 시 표준 에러 코드',
    message TEXT NULL COMMENT '디버깅용 상태 메시지',
    executor_id VARCHAR(128) NULL COMMENT 'worker pod/container 식별자',
    source_json_s3_key VARCHAR(255) NULL COMMENT '성공 시 생성된 canonical/event json S3 key',
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'job 생성 시각',
    started_at TIMESTAMP NULL DEFAULT NULL COMMENT 'worker 실행 시작 시각',
    finished_at TIMESTAMP NULL DEFAULT NULL COMMENT 'worker 실행 종료 시각',
    UNIQUE KEY uk_worker_jobs_run_id (run_id)
) ENGINE=InnoDB COMMENT='worker 실행 상태 및 멱등성 관리 테이블';
```

설명:
- `run_id` 는 전역 멱등성 기준입니다
- `status` 는 `job_status.schema.json` 의 enum과 동일하게 유지합니다
- `attempt` 는 재시도 횟수 추적용입니다
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

## 4. 읽고 쓰는 주체

### API / Scheduler
- 새 job 생성 시 `worker_jobs.status = QUEUED`
- payload를 SQS에 publish
- 상태 조회 API에서 `worker_jobs` 를 읽음

### Worker
- 메시지 수신 후 `run_id` 로 상태 조회
- `RUNNING` 또는 `SUCCEEDED` 면 중복 실행 차단
- 실행 점유 성공 시 `RUNNING` 으로 전이
- 종료 시 `SUCCEEDED` / `FAILED` 로 업데이트

### Report / 후속 시스템
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

1. API가 `worker_jobs` row 생성 (`QUEUED`)
2. worker가 실행 후 `SUCCEEDED` 로 업데이트
3. 성공 시 `source_jsons` row 생성
4. `worker_jobs.source_json_s3_key` 와 `source_jsons.source_json_s3_key` 를 맞춰 연결

---

## 6. 멀티 pod 기준에서 중요한 이유

로컬 파일 기반 멱등성만 있으면 pod A와 pod B가 서로 상태를 모릅니다.
반면 `worker_jobs` 를 공용 상태판으로 쓰면 모든 pod가 같은 기준을 봅니다.

즉:
- pod A가 `RUNNING` 기록
- pod B가 같은 `run_id` 수신
- DB 조회 후 중복 실행 차단

이 구조가 멀티 pod 환경의 최소 멱등성 기반입니다.
