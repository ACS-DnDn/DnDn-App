# DnDn contracts 가이드 (팀 공용)

이 문서는 `contracts/` 폴더가 **왜 존재하는지**, 그리고 각 파트(A/B/C/D)가 **어떻게 사용하는지**를 쉽게 설명합니다.

---

## 1) contracts는 무엇인가요?

`contracts/`는 단순 “스키마 모음”이 아니라, 팀 분업을 안정화하는 **데이터 계약서(Contract)** 입니다.

- **약속(Contract)**: “A는 이런 모양으로 데이터를 줄게”
- **검사기(Validator)**: “그 모양이 맞는지 자동으로 검사해, B가 안 깨지게 함”
- **분업 안정성**: A/B/C/D가 동시에 개발해도 *데이터 형태 때문에* 서로 발목 잡히지 않게 함

---

## 2) 이 프로젝트에서 contracts가 중요한 이유

DnDn은 흐름이 깁니다.

```
(A) 수집/정규화 → (B) 문서 생성 → (C) 결재/웹 → (D) Terraform PR/Actions
```

여기서 A가 내보내는 JSON이 매번 모양이 달라지면, B 문서 생성이 계속 깨지고,
전체가 같이 멈춥니다.

그래서 원칙은 하나입니다.

> **스키마를 통과한 JSON만 “정상 입력”으로 취급한다.**

---

## 3) 폴더/파일 구성 한눈에 보기

### A 출력(정규화 결과물) 설계도
- `canonical_model.schema.json`  
  - WEEKLY/EVENT 공통 결과 모델
  - 결과 JSON의 코어 구조(`meta`, `collection_status`, `events`, `resources`)를 고정
- `event_model.schema.json`  
  - EVENT 전용 스키마
  - `meta.type = EVENT` + `meta.trigger` 필수(더 엄격)

### 상태 표준(왜 비었는지/왜 실패했는지)
- `na_rules.md`  
  - **NA(정상적으로 수집 불가/미적용)** 사유 코드 표준
- `error_codes.md`  
  - **FAILED(에러로 실패)** 에러 코드 표준

### Worker 실행 입력(payload) 설계도
- `payload/job_payload.schema.json`  
  - Worker를 호출할 때의 “주문서” 포맷
  - `type=WEEKLY`면 `time_range` 필수
  - `type=EVENT`면 `event_time`, `window_minutes` 필수

### 샘플(정답지)
- `samples/*.sample.json`  
  - A가 만들어야 하는 결과물 예시
  - B는 이 샘플로 문서 생성 로직을 먼저 개발 가능

---

## 4) 결과 JSON 구조를 “사람 말”로 풀어보기

결과물(canonical/event)은 큰 덩어리 4개로 이해하면 됩니다.

### 1) meta = “송장(작업 정보)”
이 결과물이:
- 어떤 계정에서(account_id)
- 어떤 기간을(time_range)
- 어떤 실행(run_id)로 돌았고
- raw/normalized 증거가 어디(S3 URI)에 있는지

를 기록합니다.

특히 EVENT는 **왜 실행됐는지**가 중요해서 `meta.trigger`가 필수입니다.

### 2) collection_status = “상태표(잘 됐나?)”
수집 단계별로 OK/NA/FAILED를 남깁니다.

- `assume_role`: 계정 접근(출입증 발급)
- `cloudtrail`: 변경 이벤트 수집
- `config`: 리소스 구성 이력(before/after) 수집
- `normalized`: 정규화/스키마 검증 및 결과 생성

핵심 규칙
- status가 `NA`면 → `na_reason`을 **반드시** 남김
- status가 `FAILED`면 → `error_code`를 **반드시** 남김

### 3) events[] = “타임라인(언제/누가/무슨 변경)”
CloudTrail 이벤트를 정규화한 목록입니다.  
보고서의 “변경 타임라인” 섹션의 원재료입니다.

### 4) resources[] = “리소스별 파일철(보고서 핵심)”
B가 문서 만들 때 가장 쓰기 쉬운 단위입니다.

- 동일 리소스(AWS::EC2::SecurityGroup 등) 기준으로 이벤트를 묶고
- 가능하면 Config before/after를 best-effort로 붙입니다.

---

## 5) NA vs FAILED (이거 하나만 정확히 통일하면 팀이 편해집니다)

**NA = 정상인데 원천적으로 못함**
- 예: Config가 꺼져있음 → `SERVICE_DISABLED`
- 예: 권한이 원천적으로 없음 → `PERMISSION_DENIED`
- 예: 기간 내 데이터 없음 → `NO_DATA`

**FAILED = 원래 됐어야 하는데 에러로 실패**
- 예: AssumeRole 실패
- 예: CloudTrail API 호출 오류
- 예: 저장 실패, 스키마 검증 실패 등

문서 처리 관점
- NA → 보고서에 `N/A(사유)`로 표준 표기(“수집 불가”이지만 정상 결과)
- FAILED → 운영/구현 문제로 추적해야 함(알람/재시도 대상)

---

## 6) 역할별 사용법(정리)

### A(Collector/Normalizer)
A의 Done 기준은 단순합니다.

- `canonical.json`(주간) 또는 `event.json`(이벤트)을 만든다
- **스키마 검증을 통과**시킨다
- raw/근거는 S3에 저장하고, 결과 JSON에는 S3 포인터를 남긴다
- EVENT면 `meta.trigger`를 반드시 채운다

### B(Report Builder)
B의 기본 원칙:

1) 결과 JSON을 스키마로 검증한다(통과한 것만 신뢰)
2) 문서 생성은 `resources[]` 중심으로 한다
3) 타임라인 섹션은 `events[]`로 만든다
4) `collection_status`를 보고 “N/A/실패”를 자동 표기한다

### C(API/Front)
C는 Worker 실행 요청(payload)을 만들 때,
`payload/job_payload.schema.json`을 따르면 됩니다.

- WEEKLY: `time_range`를 넣어 호출
- EVENT: `event_time`, `window_minutes`(+ trigger 정보)를 넣어 호출

### D(Infra/GitHub)
D는 주로 배포/CI/CD/terraform plan/apply를 담당하지만,
- CI에서 samples가 스키마 통과하는지 자동 검증하는 단계 추가 등
품질 자동화에 이 contracts를 활용할 수 있습니다.

---

## 7) 확장 규칙: extensions (스키마를 자주 안 바꾸기)

새 기능(Trusted Advisor 벤치마킹, 추가 체크 결과 등)은
가능하면 core를 깨지 않게 `extensions.*` 아래에 추가합니다.

예시
- `extensions.advisor_checks[]` : “TA 벤치마킹 체크 결과”
  - 미사용 EIP, 미연결 EBS, CPU 낮은 EC2, RDS 백업 미설정, Service Quotas 사용률 등
- `extensions.securityhub_finding` : “SecurityHub Finding 요약(EVENT용)”

이렇게 하면:
- A/B/C/D가 스키마 수정으로 동시에 멈추는 일을 줄일 수 있습니다.

---

## 8) 스키마 검증 방법(팀 공통)

Python(jsonschema) 예시:

```bash
pip install jsonschema

# canonical 검증
python -c "import json; from jsonschema import validate; s=json.load(open('contracts/canonical_model.schema.json')); d=json.load(open('contracts/samples/canonical.sample.json')); validate(d,s); print('OK canonical')"

# event 검증
python -c "import json; from jsonschema import validate; s=json.load(open('contracts/event_model.schema.json')); d=json.load(open('contracts/samples/event.sample.json')); validate(d,s); print('OK event')"
```

---

## 9) 자주 묻는 질문(FAQ)

### Q1. 왜 EVENT는 meta.trigger가 필수인가요?
이벤트 보고서는 “왜 생성됐는지(어떤 Finding/Rule/Manual 호출인지)”를 추적할 수 있어야 합니다.  
그래야 운영/감사에서 역추적이 가능합니다.

### Q2. 주간(WEEKLY)과 이벤트(EVENT)는 뭐가 다른가요?
- WEEKLY: 정기 스케줄(지난 1주) 기반으로 `canonical.json`
- EVENT: 트리거 발생 시점 전후(±window) 기반으로 `event.json`
- 내부 수집 로직은 유사하지만, EVENT는 trigger가 필수입니다.

---

이 문서와 샘플(JSON)을 기준으로 팀이 동일한 언어로 개발하는 것이 목표입니다.
