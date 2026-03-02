# NA 규칙 (N/A Standard)

A 파이프라인은 어떤 단계가 “정상적으로 수집할 수 없는 상태”일 때 **실패(FAILED)** 와 **미적용(NA)** 를 구분합니다.

- FAILED: 시스템/코드/일시 오류 등 “원래 가능해야 하는데 못함”
- NA: 해당 계정/리전/기간에서 “원천적으로 적용 불가” 또는 “데이터가 존재하지 않음”

## 공통 규칙

- `collection_status.<stage>.status = "NA"` 인 경우 `na_reason`을 반드시 채웁니다.
- `message`는 디버깅용이며, B가 보고서 문구로 쓰고 싶으면 별도 매핑(문서 템플릿)에서 처리합니다.
- NA는 **정상적인 결과**로 취급됩니다(문서에는 “미적용/데이터 없음”으로 표현).

---

## na_reason 코드와 권장 message 템플릿

### 1) SERVICE_DISABLED
- 의미: 서비스가 꺼져있어 수집이 불가능
- 예: AWS Config Recorder 비활성, CloudTrail Trail 미설정 등
- 권장 message 예:
  - `AWS Config is not recording in this region/account`

### 2) PERMISSION_DENIED
- 의미: 권한 부족(AssumeRole 성공/실패 모두 포함 가능)
- 권장 message 예:
  - `AccessDenied: missing permissions for config:GetResourceConfigHistory`

### 3) NO_DATA
- 의미: 지정 기간/윈도우에 데이터가 없음(변경 이벤트 없음)
- 권장 message 예:
  - `No WRITE events in time window`

### 4) REGION_DISABLED
- 의미: 리전이 비활성/옵트인 미사용/정책상 사용 불가
- 권장 message 예:
  - `Region is not enabled/opted-in`

### 5) NOT_SUPPORTED
- 의미: MVP에서 해당 리소스/이벤트 파싱을 지원하지 않음
- 권장 message 예:
  - `Resource type not supported in MVP extractor`

### 6) OUT_OF_SCOPE
- 의미: 스코프 정책으로 의도적으로 제외(예: 특정 리소스 패턴 제외)
- 권장 message 예:
  - `Filtered out by scope policy`

### 7) UNKNOWN
- 의미: 위 코드로 분류하기 애매한 NA
- 권장 message 예:
  - `NA for unknown reason (needs investigation)`

---

## 어디에 NA를 기록하나?

1) 파이프라인 단계 단위(권장)
- `collection_status.assume_role/cloudtrail/config/normalized`

2) 리소스 단위(선택)
- `resources[].config.status = "NA"` + `na_reason`  
  (특정 리소스만 Config join이 불가한 경우)

---

## 주의: “트리거 미설정”은 NA가 아니라 INVALID_PAYLOAD 권장

고객이 EVENT 트리거 룰을 설정하지 않았거나, 잘못된 룰/패턴을 입력해 EVENT가 오지 않는 경우는
수집 데이터 자체가 생성되지 않으므로, 보통은 A 단계의 NA가 아니라 **설정/입력 오류(Invalid payload/config)** 로 처리합니다.
