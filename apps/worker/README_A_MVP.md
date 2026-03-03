\
# A(Collector) 다음 단계: Worker MVP (로컬 실행)

이 묶음은 **contracts/가 main에 들어간 다음**, A가 바로 다음으로 진행할 수 있게 만든 “최소 동작(MVP) Worker” 뼈대입니다.

목표는 딱 하나:

> `contracts/payload/*.json`(주간/이벤트 payload)을 입력으로 받아서  
> `canonical.json`(WEEKLY) 또는 `event.json`(EVENT)을 생성하고, **스키마 검증까지 통과**시키기

---

## 0) 어디에 두면 되나?

이 zip을 **레포 루트(= contracts/ 폴더가 있는 위치)** 에 풀면 아래처럼 됩니다:

```
contracts/
apps/worker/
  dndn_worker/
  tools/
```

---

## 1) 설치 (로컬)

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r apps/worker/requirements.txt
```

AWS 자격증명은 기본 프로파일로 잡혀 있어야 합니다:

```bash
aws configure
```

---

## 2) (개발 단축) AssumeRole 없이 바로 돌려보고 싶으면

payload에서 `assume_role.role_arn` 값을 **SELF**로 두면 됩니다.
(코드는 SELF면 assume_role을 생략하고 현재 AWS 자격증명으로 실행합니다.)

> 프로덕션에서는 AssumeRole이 필수지만, “일단 CloudTrail 조회/정규화 감 잡기”엔 SELF가 편합니다.

---

## 3) 스모크 테스트 2개 (먼저 이것부터)

### 3-1) AssumeRole(또는 SELF) 확인

```bash
python apps/worker/tools/smoke_assume_role.py --role-arn SELF
```

실제 role로 테스트하려면:

```bash
python apps/worker/tools/smoke_assume_role.py \
  --role-arn arn:aws:iam::<YOUR_ACCOUNT_ID>:role/DnDnCollectorReadRole \
  --external-id dndn-dev
```

### 3-2) CloudTrail 조회 확인

```bash
python apps/worker/tools/smoke_cloudtrail.py --role-arn SELF --region ap-northeast-2 --hours 24
```

---

## 4) WEEKLY 실행(주간 canonical.json 생성)

1) 샘플 payload 복사:
- `contracts/payload/weekly.payload.sample.json` 를 복사해서 `payload.weekly.local.json` 만들기

2) 최소로 수정:
- `account_id`: 내 AWS 계정 12자리
- `assume_role.role_arn`: SELF (또는 테스트 role arn)
- `s3.bucket`, `s3.prefix`: 아무 문자열이어도 되지만, 스키마가 s3 uri를 요구해서 채우는 용도

3) 실행:

```bash
python apps/worker/tools/run_payload.py \
  --payload payload.weekly.local.json \
  --repo-root . \
  --out out
```

결과:
- `out/<run_id>/normalized/canonical.json`

---

## 5) EVENT 실행(event.json 생성)

1) 샘플 payload 복사:
- `contracts/payload/event.payload.sample.json` → `payload.event.local.json`

2) 최소 수정:
- `account_id`
- `assume_role.role_arn` (SELF or role arn)
- `event_time`: 지금 시간 근처로(±60분이면 최근 1~2시간 이벤트 잡힘)
- `window_minutes`

3) 실행:

```bash
python apps/worker/tools/run_payload.py \
  --payload payload.event.local.json \
  --repo-root . \
  --out out
```

결과:
- `out/<run_id>/normalized/event.json`

---

## 6) “성공” 기준 (A MVP 완료 체크)

- [ ] WEEKLY 실행 → `canonical.json` 생성
- [ ] EVENT 실행 → `event.json` 생성
- [ ] 두 결과 모두 contracts 스키마 검증 통과
  - WEEKLY: `contracts/canonical_model.schema.json`
  - EVENT: `contracts/event_model.schema.json`

---

## 7) 흔한 막힘 & 해결

### CloudTrail 이벤트가 0개다
- 정상일 수 있어요. “그 기간에 변경이 없었다”면 0개입니다.
- 테스트하려면 AWS 콘솔에서 작은 변경 1개만 해도 됩니다.
  - 예: S3 버킷 만들었다가 지우기, Security Group 룰 추가/삭제 등

### Config는 왜 NA로 나오지?
- 대부분 계정은 Config가 꺼져 있습니다 → 이건 실패가 아니라 **NA(SERVICE_DISABLED)**가 정상입니다.

### 프로덕션에선 S3 저장이 필수 아닌가?
- 맞아요. 이 MVP는 “먼저 JSON 생성 + 스키마 통과”를 목표로 로컬(out/)에 저장합니다.
- 다음 단계에서 S3 put_object로 raw/normalized 업로드를 붙이면 됩니다.
