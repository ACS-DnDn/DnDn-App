# Error Codes (A pipeline)

A 파이프라인에서 `status="FAILED"` 인 경우 `error_code`는 아래 중 하나를 사용합니다.
(확장 가능하지만, MVP에서는 이 목록을 우선 사용)

## 공통 규칙

- `collection_status.<stage>.status = "FAILED"` 면 `error_code` 필수
- 가능하면 `retryable`을 함께 채웁니다.
- worker는 결과/예외 모델에서도 `retryable`을 명시적으로 전달합니다.
- consumer의 delete / no-delete 판단은 예외 타입이 아니라 `retryable` 기준으로 맞춥니다.

---

## 인증/권한

- `ASSUME_ROLE_FAILED`  
  대상 계정 Role Assume 실패 (trust/external id/권한/정책 문제)

- `ACCESS_DENIED`  
  AWS API 호출 권한 부족 (예: cloudtrail:LookupEvents, config:GetResourceConfigHistory)

- `INVALID_EXTERNAL_ID`  
  External ID 불일치로 AssumeRole 거부된 것으로 추정되는 경우

---

## 호출/쿼리/쓰로틀링

- `THROTTLED`  
  AWS API Throttling (재시도 필요)

- `RATE_LIMITED`  
  호출량 제한(서비스별)로 실패 (재시도 필요)

- `NETWORK_ERROR`  
  네트워크/일시 장애(재시도 필요)

---

## Trigger / 입력(고객 선택형 트리거 포함)

- `INVALID_PAYLOAD`  
  run_job(payload) 입력이 필수값 누락/형식 오류

- `TRIGGER_CATALOG_NOT_FOUND`  
  selector.mode=CATALOG 인데 catalog/pack/item을 찾지 못함(설정 오류)

- `TRIGGER_PATTERN_INVALID`  
  CUSTOM_PATTERN JSON이 파싱/검증에 실패

- `TRIGGER_PATTERN_TOO_BROAD`  
  너무 광범위한 패턴(폭주 위험)으로 정책상 거부

---

## CloudTrail

- `CLOUDTRAIL_LOOKUP_FAILED`  
  LookupEvents 실패

- `CLOUDTRAIL_EVENT_PARSE_FAILED`  
  CloudTrailEvent(JSON string) 파싱 실패

- `CLOUDTRAIL_UNAVAILABLE`  
  CloudTrail 이벤트 조회 불가(계정/리전 정책상)

---

## AWS Config

- `CONFIG_GET_HISTORY_FAILED`  
  get_resource_config_history 실패

- `CONFIG_DISABLED`  
  Config Recorder/Delivery 비활성 (정책에 따라 NA로도 처리 가능)

- `CONFIG_NOT_SUPPORTED`  
  해당 resource_type이 Config에서 조회 불가

## Access Analyzer

- `ACCESS_ANALYZER_LIST_ANALYZERS_FAILED`
  Access Analyzer analyzer 목록 조회 실패

- `ACCESS_ANALYZER_UNEXPECTED`
  Access Analyzer 수집 중 예상하지 못한 예외 발생

## Cost Explorer / CloudWatch

- `COST_EXPLORER_GET_COST_AND_USAGE_FAILED`
  Cost Explorer 비용 조회 실패

- `COST_EXPLORER_UNEXPECTED`
  Cost Explorer 수집 중 예상하지 못한 예외 발생

- `CLOUDWATCH_DESCRIBE_ALARMS_FAILED`
  CloudWatch alarm 조회 실패

- `CLOUDWATCH_UNEXPECTED`
  CloudWatch 수집 중 예상하지 못한 예외 발생

---

## 저장/검증

- `S3_PUT_FAILED`  
  S3 저장 실패

- `SCHEMA_VALIDATION_FAILED`  
  스키마 검증 실패(버그 가능성 높음)

---

## retryable 권장값(가이드)

- 재시도 O(대체로): `THROTTLED`, `RATE_LIMITED`, `NETWORK_ERROR`, 일시적 `S3_PUT_FAILED`
- 재시도 X(대체로): `ASSUME_ROLE_FAILED`, `ACCESS_DENIED`, `INVALID_PAYLOAD`, `SCHEMA_VALIDATION_FAILED`, `TRIGGER_*`

## 멱등성 기준

- 동일 `run_id` 재수신 시, worker는 기존 로컬 결과 파일이 있으면 `already_processed=True` 로 즉시 반환합니다.
- 이 기준은 동일 worker 인스턴스/로컬 볼륨 범위의 멱등성입니다.
- 분산 환경 전역 멱등성은 별도 저장소 또는 락 전략이 필요합니다.

## 플랫폼 job 상태 기준

worker 실행 상태는 플랫폼 관점에서 아래 네 상태를 기준으로 추적하는 것을 권장합니다.

- `QUEUED`: payload가 생성되었고 아직 worker가 점유하지 않음
- `RUNNING`: worker가 현재 실행 중
- `SUCCEEDED`: 결과 JSON 생성 및 최종 저장 완료
- `FAILED`: 실행 실패

권장 매핑:
- `already_processed=True` 는 플랫폼 상태상 중복 실행을 막기 위한 `SUCCEEDED` 재확인으로 취급
- `retryable=True` 인 `FAILED` 는 재시도 후보
- `retryable=False` 인 `FAILED` 는 운영자 확인 또는 입력 수정 대상
