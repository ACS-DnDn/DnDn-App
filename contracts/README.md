# contracts/

> 📌 팀원용 요약: `TEAM_BRIEF.md`
>
> 📖 자세한 가이드: `CONTRACT_GUIDE.md`


DnDn 프로젝트에서 **A(데이터 공급망 오너)** 가 생성하는 표준 JSON의 **데이터 계약(Contract)** 입니다.  
B(문서 생성)는 이 계약만 믿고 `canonical.json` / `event.json`을 검증(`jsonschema validate`)한 뒤 문서화를 진행합니다.

## 핵심 목표

- **정확성**: 원천(raw) 근거를 S3에 보존하고, normalized JSON에는 **원천 포인터(S3 URI)** 를 남긴다.
- **일관성**: 스키마/규칙 기반으로 항상 같은 구조로 만든다.
- **재현성**: 동일 입력(기간/이벤트/룰셋) → 동일 출력(정렬/키/룰) 을 보장한다.

---

## 파일 구성

- `canonical_model.schema.json`  
  WEEKLY/EVENT 공통 **정규화 모델**(MVP P0) 스키마

- `event_model.schema.json`  
  EVENT 전용 스키마(**meta.type=EVENT + meta.trigger 필수** 강제)

- `na_rules.md`  
  수집 불가/미적용(NA) 표준 규칙(문구/코드)

- `error_codes.md`  
  A 파이프라인에서 사용하는 표준 에러 코드 목록

- `payload/`
  Worker 실행 입력(payload) 스키마 + 샘플

- `samples/`
  출력 예시(canonical/event) 샘플

---

## 스키마 버전

- `meta.schema_version`: `MAJOR.MINOR.PATCH` (예: `0.2.0`)
- 스키마가 바뀌면 **schema_version을 올리고**, B는 해당 버전에 맞는 문서 생성 로직을 적용합니다.

> 이번 버전(0.2.x) 변경점(추가):
> - EVENT 트리거가 **고객 선택형 Trigger Catalog / Custom Trigger / Manual API** 로 확장될 수 있도록
>   `meta.trigger.selector` 필드를 옵션으로 추가했습니다(하위호환).

---

## 검증 방법(예시)

### Python (jsonschema)

```bash
pip install jsonschema
python -c "import json; from jsonschema import validate; s=json.load(open('contracts/canonical_model.schema.json')); d=json.load(open('canonical.json')); validate(d,s); print('OK')"
```

### Node (ajv)

```bash
npm i ajv
node -e "const Ajv=require('ajv'); const fs=require('fs'); const ajv=new Ajv({strict:false,allErrors:true}); const schema=JSON.parse(fs.readFileSync('contracts/canonical_model.schema.json')); const data=JSON.parse(fs.readFileSync('canonical.json')); const ok=ajv.validate(schema,data); console.log(ok? 'OK': ajv.errors)"
```

---

## 모델 개념(중요)

### 1) 리포트 중심 단위는 `resources[]`

MVP 기준으로 B가 가장 원하는 단위는 “사용자 집계”보다  
**리소스 기준 묶음(`resources[]`)** 입니다.

- `events[]`: 수집한 (WRITE 중심) 이벤트 목록(정규화)
- `resources[]`: 이벤트에서 추출한 리소스를 **리소스 키로 그룹핑**한 결과
  - `resources[].events[]`: 해당 리소스에 연결된 이벤트 링크(가벼운 참조)
  - `resources[].config`: 가능할 때만 Config before/after를 붙임(best-effort)

사용자/서비스별 통계는 필요하면 `extensions.stats` 같은 확장 영역으로 둡니다.

---

## 확장 규칙: `extensions` (스키마를 최대한 안 바꾸기)

contracts는 core(메타/수집상태/이벤트/리소스)를 고정하고, **새 기능 데이터는 `extensions` 아래에 추가**합니다.

왜 이렇게 하냐면:
- 스키마를 자주 바꾸면 A/B/C/D가 동시에 수정해야 해서 개발 속도가 느려집니다.
- `extensions`는 “첨부서류” 같은 공간이라, **기능을 추가해도 하위호환**을 유지할 수 있습니다.

### 추천 키(초안)
- `extensions.advisor_checks[]` : Trusted Advisor 벤치마킹(주간 리포트용)
  - 예: 미사용 EIP, 미연결 EBS, RDS 백업 미설정, Service Quotas 사용률 등
- `extensions.advisor_collection_status` : CloudWatch/ServiceQuotas 수집 상태(선택)
  - 참고: core `collection_status`는 현재 assume_role/cloudtrail/config/normalized만 정의되어 있어, 추가 수집 단계는 extensions에 기록합니다.
- `extensions.securityhub_finding` : SecurityHub Finding 요약(EVENT용, 선택)
  - 원본 Finding/Event는 `meta.trigger.raw_event_s3_uri`로 추적합니다.

### 샘플
- `samples/canonical.sample.json` : advisor_checks 예시 포함
- `samples/event.securityhub.sample.json` : SecurityHub Finding 기반 EVENT 예시
- `payload/event.securityhub.payload.sample.json` : Worker 호출 입력 예시

---

### 2) EVENT 타입은 `meta.trigger`가 필수

- `meta.type = "EVENT"` 인 경우, 반드시 `meta.trigger`가 포함되어야 합니다.
- 주의: **Event ID만으로는 Config before/after 조인이 불가능**합니다.  
  EVENT에서도 결국 CloudTrailEvent에서 `resourceType/resourceId` 추출이 필요합니다.

---

### 3) 고객 선택형 트리거(Trigger Catalog / Custom) 표현

우리는 고객 환경을 모르므로, EVENT 트리거는 보통 다음 중 하나로 구성됩니다.

- CATALOG: 우리가 제공한 “변경 유형 리스트(팩)”에서 고객이 선택
- CUSTOM: 고객이 `eventSource + eventName[]` 또는 EventBridge pattern을 직접 지정
- MANUAL_API: 룰 없이 고객이 API로 온디맨드 실행(1회성)

이를 normalized JSON에 남기고 싶으면, 아래 필드를 사용하세요.

- `meta.trigger.selector.mode`: `CATALOG | CUSTOM_EVENT | CUSTOM_PATTERN | MANUAL_API`
- `meta.trigger.selector.catalog`: (CATALOG일 때) catalog_id/pack_id/item_id/version
- `meta.trigger.selector.match`: event_source / event_names (권장)
- `meta.trigger.selector.rule_name/rule_arn`: EventBridge 룰 식별자(있으면)
- `meta.trigger.selector.event_pattern_hash/event_pattern_s3_uri`: custom pattern을 저장/추적할 때

> 운영에서 가장 중요한 건 “event.json이 어떤 트리거 규칙에서 왔는지” 역추적 가능한 것.
> (trigger.selector를 쓰거나, 최소한 raw_event_s3_uri를 남기는 것을 권장)

---

## 시간 기준(팀 합의 반영)

- 주간 기간(weekly)은 **KST(Asia/Seoul) 기준 월요일 00:00**을 시작으로 자릅니다.
- `meta.time_range.start/end`에는 **timezone 포함 ISO 8601**을 저장하세요.
  - 예: `2026-02-23T00:00:00+09:00` (KST)
- CloudTrail/Config API 호출 시에는 내부적으로 UTC 변환해서 조회하되,
  **표준 출력(JSON)에는 KST 포함 타임스탬프**를 유지하는 것을 권장합니다.

---

## S3 저장 규칙(요약)

A의 책임: raw/normalized를 S3에 정확히 저장하고, JSON에 포인터를 남김.

권장 Prefix (예시):

- WEEKLY  
  `s3://dndn-data/account_id=.../type=WEEKLY/year=YYYY/week=WW/run_id=.../raw/...`  
  `s3://dndn-data/account_id=.../type=WEEKLY/year=YYYY/week=WW/run_id=.../normalized/canonical.json`

- EVENT  
  `s3://dndn-data/account_id=.../type=EVENT/year=YYYY/month=MM/day=DD/run_id=.../raw/...`  
  `s3://dndn-data/account_id=.../type=EVENT/year=YYYY/month=MM/day=DD/run_id=.../normalized/event.json`

`meta.evidence.raw_prefix_s3_uri` / `meta.evidence.normalized_prefix_s3_uri` 로
B가 run_id 기반으로 원천을 역추적할 수 있어야 합니다.

---

## 결정론(Determinism) 규칙(강력 권장)

동일 입력 → 동일 출력 보장을 위해 아래를 지키는 것을 권장합니다.

- `events[]` 정렬: `(event_time ASC, event_id ASC)`
- `resources[]` 정렬: `(key ASC)`
- `resources[].events[]` 정렬: `(event_time ASC, event_id ASC)`
- JSON 직렬화: `utf-8`, `sort_keys=True`(또는 동등한 안정화), `indent` 고정
- `run_id`는 충돌 방지(ULID/UUIDv7 권장)

---

## 출력 최소 조건(MVP Done 기준)

- WEEKLY: `canonical.json` 1개가 생성되고 스키마 검증을 통과
- EVENT: `event.json` 1개가 생성되고 스키마 검증을 통과
- raw 증거(CloudTrail/Config/trigger payload)가 S3에 저장되고,
  normalized JSON에 S3 URI 포인터가 남아있음