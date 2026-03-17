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

### 2-3. queue message도 payload 그대로 사용
현재 worker consumer는 SQS message body에 별도 envelope를 두지 않고
`job_payload.schema.json` 을 만족하는 JSON payload 자체를 넣는 것을 기준으로 합니다.

원칙:
- queue body = payload JSON
- consumer는 body를 그대로 파싱해 payload schema 검증 후 worker에 전달
- envelope는 정말 필요해질 때만 별도 schema를 추가합니다

즉, 지금 단계에서 queue message 전용 schema는 두지 않습니다.

### 2-4. 실행 상태 계약은 별도로 관리
worker 입력 payload와 결과 JSON 외에도,
플랫폼은 worker 실행 상태를 별도 계약으로 추적해야 합니다.

현재 기준 계약:
- `job_payload.schema.json`: worker 입력
- `canonical_model.schema.json` / `event_model.schema.json`: worker 결과
- `job_status.schema.json`: worker 실행 상태 및 멱등성 추적

---

## 3. 폴더 구조

```text
contracts/
  README.md
  canonical_model.schema.json
  event_model.schema.json
  job_status.schema.json
  worker_job_storage.md
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
    job_status.sample.json
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
또한 `meta.evidence` 아래의 artifact pointer 규칙도 이 스키마에 포함됩니다.

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

### 4-5. `job_status.schema.json`
worker 실행 상태를 플랫폼이 공통으로 추적하기 위한 계약입니다.

핵심 필드:
- `run_id`
- `job_type`
- `status`
- `attempt`
- `retryable`
- `executor_id`
- `requested_at`, `started_at`, `finished_at`

이 스키마는 멀티 pod 환경에서
- 어떤 job이 이미 실행 중인지
- 어떤 job이 성공/실패했는지
- 같은 `run_id`를 다시 실행해도 되는지
를 판단하는 기준이 됩니다.

---

### 4-6. `worker_job_storage.md`
`job_status.schema.json` 을 실제 플랫폼 저장 구조와 연결하는 설계 문서입니다.

핵심 내용:
- `worker_jobs` 테이블 초안
- 상태 전이 규칙
- 현재 구현 기준으로 API / Worker / Report가 무엇을 담당하는지
- `source_jsons` 와의 관계

즉, 이 문서는 멀티 pod 기준 멱등성을 RDS 중심으로 어떻게 구현할지 설명합니다.

---

### 4-7. `payload/job_payload.schema.json`
Worker 실행 요청(payload)의 구조를 정의합니다.
이 payload는 로컬 CLI 입력 파일이기도 하고,
동시에 SQS consumer가 받는 queue message body의 표준 형태이기도 합니다.

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

### 4-8. `payload/*.sample.json`
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

### 4-9. `samples/*.sample.json`
Worker 결과물과 실행 상태 계약을 포함한 샘플입니다.

예:
- `canonical.sample.json`
- `event.sample.json`
- `job_status.sample.json`
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

### `meta.evidence`에서 바로 볼 수 있는 것
- `raw_prefix_s3_uri`
- `normalized_prefix_s3_uri`
- `job_payload_s3_uri`
- `index_s3_uri`

여기서 중요한 건 `index_s3_uri` 입니다.
이 파일(`raw/index.json`)은 이번 실행에서 생성된 raw/normalized 파일 목록과 각 S3 URI를 모아둔 artifact inventory 입니다.

즉:
- B(Report)는 경로를 추측하지 말고 `meta.evidence.index_s3_uri` 를 우선 기준으로 쓰는 것이 좋습니다.
- evidence bundle zip을 만들 때도 이 index를 기준으로 포함 대상을 정하면 됩니다.

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

특히 `events[].raw.*_s3_uri` 는 해당 이벤트가 어떤 CloudTrail raw evidence를 근거로 정규화되었는지 보여주는 포인터입니다.

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

그리고 가능하면 trigger 원문도 `raw/trigger/aws_health_event.json` 으로 저장하고,
`meta.trigger.raw_event_s3_uri` 로 그 위치를 남깁니다.
원문 payload가 없는 경우에는 현재 trigger metadata가 저장될 수 있습니다.

즉 contracts는 이미 **AWS Health 이벤트 루트**를 염두에 둔 상태입니다.

---

### 6-2. Security Hub 이벤트
Security Hub Finding 기반 EVENT도 샘플로 제공됩니다.

즉 contracts는 단일 이벤트 소스가 아니라,
**여러 이벤트 소스를 EVENT라는 공통 구조로 다루는 방향**입니다.

Security Hub도 동일하게 trigger 원문 또는 trigger metadata가
`raw/trigger/securityhub_finding.json` 으로 저장될 수 있으며,
결과 JSON에서는 `meta.trigger.raw_event_s3_uri` 로 참조됩니다.
원문 payload가 없는 경우에는 현재 trigger metadata가 저장될 수 있습니다.

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

### 6-4. weekly Access Analyzer findings
WEEKLY 결과에서는 Access Analyzer finding도 `extensions` 아래에 넣을 수 있습니다.

예:
- `extensions.access_analyzer_collection_status`
- `extensions.access_analyzer_findings`
- `extensions.access_analyzer_rollup`

이 확장은 core schema를 깨지 않고 접근/권한 리스크를 추가하는 용도로 사용합니다.

---

## 7. contracts를 실제로 어떻게 쓰나

### A(Worker)
- payload 스키마에 맞는 입력을 받는다
- 결과 JSON이 schema를 통과하게 만든다
- raw evidence와 `raw/index.json` 을 일관된 구조로 생성한다
- 실행 상태는 `job_status.schema.json` 기준으로 플랫폼과 공유될 수 있어야 한다

worker lane:
- 로컬: payload file -> `run_job_from_payload_file(...)`
- 운영: SQS body(payload JSON) -> `run_job_from_payload(...)`

### B(Report)
- sample / schema를 보고 문서 생성 로직을 맞춘다
- `resources[]`, `extensions.*`를 활용한다
- evidence bundle이 필요하면 `meta.evidence.index_s3_uri` 와 각 raw pointer를 이용해 파일을 수집한다

### C(API/Front)
- `job_payload.schema.json` 기준으로 Worker 요청 payload를 만든다
- queue를 사용할 경우에도 동일 payload를 그대로 message body에 넣는다
- 별도 envelope를 임의로 추가하지 않는다

### D(Infra)
- EventBridge / IAM / S3 구조를 contracts와 맞춘다
- 특히 trigger payload와 evidence 위치가 중요하다
- SQS를 쓸 경우 queue transport만 담당하고 message body 구조는 payload contract를 그대로 따른다

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

### 원칙 5. queue envelope는 필요할 때만 도입한다
지금 단계에서는 queue message body를 payload 그대로 유지합니다.

- 장점: consumer 구현 단순화, schema 재사용, 디버깅 단순화
- trade-off: transport metadata가 많아지면 별도 envelope schema가 필요할 수 있음

그 시점이 오면:
- `queue_message.schema.json` 같은 별도 schema를 추가
- payload는 envelope 내부 field로 내립니다
- consumer와 producer를 함께 갱신합니다

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

### 10-4. evidence는 한 군데에 다 들어있지 않다
현재 contracts에서 evidence는 용도별로 분산되어 있습니다.

- 실행 전체 evidence → `meta.evidence`
- trigger evidence → `meta.trigger.raw_event_s3_uri`
- 이벤트별 CloudTrail evidence → `events[].raw.*_s3_uri`
- advisor evidence → `extensions.advisor_checks[].evidence`

그래서 사람이 전체를 한 번에 보려면 `raw/index.json` 을 같이 보는 것이 가장 빠릅니다.

### 10-5. queue message schema가 따로 없는 이유
현재 queue message는 transport envelope가 아니라 worker payload 자체입니다.

즉:
- 로컬 파일 실행도 payload
- SQS body도 payload
- worker 공용 진입점도 payload

이렇게 한 종류의 입력 계약으로 맞추는 것이 현재 단계의 원칙입니다.

### 10-6. 결과 스키마와 상태 스키마는 역할이 다르다
`canonical.json` / `event.json` 은 worker가 만든 결과물 계약입니다.
반면 `job_status.schema.json` 은 worker 실행 상태 계약입니다.

즉:
- 결과 스키마 = report/API가 읽는 산출물 구조
- 상태 스키마 = API/worker/운영 시스템이 읽는 실행 상태 구조

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
