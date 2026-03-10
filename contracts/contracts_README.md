# contracts

`contracts/`는 DnDn 프로젝트에서 **데이터 계약(Contract)** 을 정의하는 폴더입니다.

쉽게 말하면:

- A(Worker)가 어떤 JSON을 만들어서 내보내는지
- C/API가 Worker를 어떤 payload로 호출하는지
- B(Report)가 어떤 구조를 믿고 보고서를 생성하는지

를 **명확하게 고정하는 기준 문서와 스키마 모음**입니다.

즉, `contracts/`는 단순한 샘플 파일 모음이 아니라  
**A ↔ B ↔ C ↔ D 사이의 합의 문서**라고 보면 됩니다.

---

## 1. 왜 contracts가 필요한가

프로젝트에서 각 파트가 동시에 움직일 때 가장 자주 깨지는 게 이거야:

- A는 JSON 구조를 조금 바꿈
- B는 예전 구조를 가정하고 문서 생성
- C는 payload 형식을 다르게 보냄
- 결과적으로 “작동은 하는데 서로 안 맞는” 상태가 됨

`contracts/`는 이 문제를 막기 위한 장치입니다.

### contracts가 해주는 일
1. **표준화**
   - 결과 JSON 구조를 고정
2. **검증**
   - 스키마로 `canonical.json`, `event.json` 검증 가능
3. **분업 안정화**
   - A/B/C가 동시에 개발해도 구조 충돌을 줄임
4. **확장성**
   - 새 기능은 가급적 `extensions` 아래로 넣어 하위호환 유지

---

## 2. 이 폴더의 핵심 개념

### 2-1. 결과 JSON은 2종류
- `canonical.json` → WEEKLY 결과
- `event.json` → EVENT 결과

### 2-2. Worker 실행 입력도 계약 대상
Worker에 들어가는 payload도 자유 형식이 아니라  
`job_payload.schema.json` 을 따릅니다.

즉 contracts는 크게 두 종류를 정의합니다.

- **입력 계약**
  - Worker payload
- **출력 계약**
  - canonical/event JSON

---

## 3. 폴더 구조

```text
contracts/
  README.md
  canonical_model.schema.json
  event_model.schema.json
  na_rules.md
  error_codes.md
  payload/
    job_payload.schema.json
    weekly.payload.sample.json
    event.payload.sample.json
    event.securityhub.payload.sample.json
    event.aws_health.payload.sample.json
  samples/
    canonical.sample.json
    event.sample.json
    event.securityhub.sample.json
    event.aws_health.sample.json
```

---

## 4. 각 파일 설명

### 4-1. `canonical_model.schema.json`
WEEKLY / EVENT 공통으로 쓰는 **핵심 normalized 결과 모델 스키마**입니다.

여기서 보통 강제하는 것:
- `meta`
- `collection_status`
- `events`
- `resources`
- `extensions`

즉, Worker 결과 JSON의 뼈대는 이 스키마가 결정합니다.

---

### 4-2. `event_model.schema.json`
EVENT 전용 스키마입니다.

핵심 차이:
- `meta.type = EVENT`
- `meta.trigger` 필수

즉, **이벤트 보고서용 결과물은 반드시 trigger 정보가 있어야 한다**는 걸 강제합니다.

---

### 4-3. `na_rules.md`
Worker가 “수집 불가 / 미적용” 상태를 어떤 식으로 표현하는지 정의한 문서입니다.

예:
- `SERVICE_DISABLED`
- `PERMISSION_DENIED`
- `NO_DATA`

이 문서가 중요한 이유는:
- Config 꺼져 있는 계정
- 권한이 없는 서비스
- 기간 내 이벤트 없음

같은 상황을 **실패가 아니라 N/A로 표현할 기준**을 팀이 공유해야 하기 때문입니다.

---

### 4-4. `error_codes.md`
실제 오류(`FAILED`)가 났을 때 어떤 에러 코드를 쓰는지 정의합니다.

예:
- `ASSUME_ROLE_FAILED`
- `CLOUDTRAIL_LOOKUP_FAILED`
- `SCHEMA_VALIDATION_FAILED`

즉:
- `NA`는 “정상적으로 못 하는 상태”
- `FAILED`는 “실제 오류 상태”

를 구분해주는 기준입니다.

---

### 4-5. `payload/job_payload.schema.json`
Worker 실행 요청(payload)의 구조를 정의합니다.

핵심 필드:
- `type`
- `account_id`
- `regions`
- `assume_role`
- `s3`

추가 필드:
- WEEKLY → `time_range`
- EVENT → `event_time`, `window_minutes`, `trigger`

이 스키마 덕분에 API/C 파트는  
**어떤 형식으로 Worker를 호출해야 하는지** 명확히 알 수 있습니다.

---

### 4-6. `payload/*.sample.json`
실행 예시 payload입니다.

예:
- `weekly.payload.sample.json`
- `event.payload.sample.json`
- `event.securityhub.payload.sample.json`
- `event.aws_health.payload.sample.json`

이 샘플들은 단순 예제가 아니라,
- 로컬 테스트
- 디버깅
- 팀 간 기능 설명

에 바로 쓸 수 있는 기준본입니다.

---

### 4-7. `samples/*.sample.json`
Worker가 만들어야 하는 결과물의 샘플입니다.

예:
- `canonical.sample.json`
- `event.sample.json`
- `event.securityhub.sample.json`
- `event.aws_health.sample.json`

이 샘플은 특히 B(Report)에게 중요합니다.
B는 이 샘플을 보고:
- 어떤 필드가 들어오는지
- 어디서 무엇을 읽어 문서를 만들지
를 바로 이해할 수 있습니다.

---

## 5. 데이터 모델 핵심 설명

## 5-1. `meta`
결과물의 메타데이터입니다.

예:
- `schema_version`
- `type`
- `run_id`
- `account_id`
- `regions`
- `time_range`
- `generated_at`
- `collector`
- `evidence`

EVENT일 경우에는 여기에 `trigger`가 추가됩니다.

즉, `meta`는 결과물의 “송장/표지” 역할을 합니다.

---

## 5-2. `collection_status`
수집 단계별 상태입니다.

예:
- `assume_role`
- `cloudtrail`
- `config`
- `normalized`

각 단계는 대체로 아래 셋 중 하나를 가집니다.
- `OK`
- `NA`
- `FAILED`

이 구조 덕분에:
- 실행은 성공했지만 Config는 비활성화 → `NA`
- AWS API가 실제로 터짐 → `FAILED`

같은 상황을 구분할 수 있습니다.

---

## 5-3. `events`
정규화된 이벤트 목록입니다.

주로 CloudTrail 기반으로 만들어지며:
- `event_id`
- `event_time`
- `event_source`
- `event_name`
- `resources`
- `raw`

같은 정보를 포함합니다.

즉, `events[]`는 **타임라인 중심 데이터**입니다.

---

## 5-4. `resources`
보고서/분석에 더 유용한 단위입니다.

Worker는 이벤트를 리소스 기준으로 묶어서 `resources[]`를 만듭니다.

리소스 항목은 보통:
- `resource`
- `events`
- `change_summary`
- `config`

를 가집니다.

즉, `resources[]`는 **리소스 중심 요약 뷰**라고 보면 됩니다.

### 왜 중요하냐
B(Report)는 보통 `events[]`보다 `resources[]`를 더 많이 씁니다.
왜냐면 사람은 “이벤트 500개”보다 “어떤 리소스가 어떻게 바뀌었는지”를 더 보고 싶어하니까요.

---

## 5-5. `extensions`
이 폴더/스키마의 가장 중요한 철학 중 하나입니다.

contracts는 핵심 구조(`meta`, `collection_status`, `events`, `resources`)는 고정하고,  
**새 기능은 가급적 `extensions` 아래에 넣습니다.**

왜냐면:
- core 구조를 자주 바꾸면 B/C/D가 다 깨짐
- 새 기능은 하위호환이 중요함

예:
- `extensions.event_origin`
- `extensions.aws_health`
- `extensions.actionability`
- `extensions.advisor_collection_status`
- `extensions.advisor_checks`
- `extensions.advisor_rollup`

즉, `extensions`는 **실험/확장/신규 기능을 담는 안전한 공간**입니다.

---

## 6. 현재 contracts가 지원하는 주요 확장

### 6-1. AWS Health 이벤트
EVENT payload와 output sample에 Health 예시가 들어 있습니다.

Worker는 Health payload를 받아:
- `extensions.event_origin.kind = AWS_HEALTH`
- `extensions.aws_health`
- `extensions.actionability`

로 확장합니다.

즉 contracts는 이미 **AWS Health 이벤트 루트**를 염두에 둔 상태입니다.

---

### 6-2. Security Hub 이벤트
Security Hub Finding 기반 EVENT도 샘플로 제공됩니다.

즉 contracts는 단일 이벤트 소스가 아니라,
**여러 이벤트 소스를 EVENT라는 공통 구조로 다루는 방향**입니다.

---

### 6-3. weekly advisor checks
WEEKLY 결과에서는 운영 점검 결과를 `extensions.advisor_checks[]`에 넣는 방향을 사용합니다.

예:
- 미사용 EIP
- 미연결 EBS
- RDS 백업 미설정
- RDS Multi-AZ 미설정

즉 주간 보고서는 단순 변경 이력뿐 아니라 **운영 점검 결과**도 포함할 수 있게 설계되어 있습니다.

---

## 7. contracts를 실제로 어떻게 쓰나

### A(Worker)
- payload 스키마에 맞는 입력을 받는다
- 결과 JSON이 schema를 통과하게 만든다

### B(Report)
- sample / schema를 보고 문서 생성 로직을 맞춘다
- `resources[]`, `extensions.*`를 활용한다

### C(API/Front)
- `job_payload.schema.json` 기준으로 Worker 요청 payload를 만든다

### D(Infra)
- EventBridge / IAM / S3 구조를 contracts와 맞춘다
- 특히 trigger payload와 evidence 위치가 중요하다

---

## 8. 검증 방법

### 8-1. Python(jsonschema)
```bash
pip install jsonschema
python - <<'PY'
import json
from jsonschema import validate

schema = json.load(open("contracts/canonical_model.schema.json"))
data = json.load(open("contracts/samples/canonical.sample.json"))
validate(data, schema)
print("OK canonical")
PY
```

EVENT 검증:
```bash
python - <<'PY'
import json
from jsonschema import validate

schema = json.load(open("contracts/event_model.schema.json"))
data = json.load(open("contracts/samples/event.sample.json"))
validate(data, schema)
print("OK event")
PY
```

---

## 9. contracts를 수정할 때 원칙

### 원칙 1. core는 자주 흔들지 않는다
- `meta`
- `collection_status`
- `events`
- `resources`

이 구조는 웬만하면 유지

### 원칙 2. 새 기능은 extensions 우선
예:
- 새 이벤트 소스
- 새 운영 점검
- 새 리포트 보조 데이터

이건 먼저 `extensions`에 넣어서 하위호환을 유지

### 원칙 3. 샘플도 같이 갱신한다
스키마만 바꾸면 안 되고:
- payload sample
- result sample
도 같이 갱신해야 B/C가 바로 이해할 수 있음

### 원칙 4. PR에서 검증 결과를 같이 남긴다
가능하면 PR 본문에:
- 어떤 샘플로 검증했는지
- 어떤 결과가 나왔는지
를 남기는 게 좋다.

---

## 10. 자주 헷갈리는 포인트

### 10-1. `source`와 `logical_source`
예를 들어 AWS Health는:
- transport source는 `EVENTBRIDGE`
- logical source는 `AWS_HEALTH`

이렇게 분리해서 볼 수 있습니다.

즉:
- `source` = 들어온 채널
- `logical_source` = 실제 이벤트 의미상 출처

### 10-2. `NA`와 `FAILED`
- `NA` = 수집 대상/조건이 맞지 않아 정상적으로 수집 불가
- `FAILED` = 코드/권한/API 등 실제 오류

### 10-3. `advisor_checks`가 0건이어도 정상
실제 계정에 문제 리소스가 없으면 당연히 0건일 수 있습니다.
핵심은 로직과 상태/rollup가 생기는지입니다.

---

## 11. 이 폴더를 처음 보는 팀원이 읽는 순서 추천
1. `README.md`
4. `payload/job_payload.schema.json`
5. `payload/*.sample.json`
6. `samples/*.sample.json`

이 순서로 보면 전체 그림이 잘 보입니다.

---

## 12. 마지막 정리

`contracts/`는 DnDn에서:
- Worker 입력
- Worker 출력
- 상태 표현
- 확장 방식
을 고정하는 **공식 인터페이스 문서**입니다.

즉, 이 폴더를 이해하면
- Worker가 무슨 JSON을 만드는지
- Report가 뭘 읽어야 하는지
- API가 어떤 payload를 보내야 하는지
를 한 번에 이해할 수 있습니다.
