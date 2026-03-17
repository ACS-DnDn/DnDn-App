# Worker IAM / AssumeRole Onboarding

이 문서는 DnDn Worker가 고객 AWS 계정에 안전하게 연결되도록
AssumeRole 기반 IAM 설정과 검증 절차를 정리합니다.

핵심 원칙:
- 고객 계정에는 **읽기 전용 최소 권한 Role** 만 둡니다
- Worker는 고객 Role로 **수집만** 수행합니다
- S3 업로드는 고객 Role이 아니라 **DnDn 쪽 세션** 으로 수행합니다
- ExternalId 기반 AssumeRole을 사용해 confused deputy 리스크를 줄입니다

---

## 1. 현재 수집 범위와 필요한 권한

현재 Worker가 기본적으로 사용하는 AWS API는 아래와 같습니다.

| 기능 | AWS API | 권한 필요 여부 | 비고 |
| --- | --- | --- | --- |
| CloudTrail 변경 이력 수집 | `cloudtrail:LookupEvents` | 필수 | WEEKLY / EVENT 공통 |
| Config recorder 상태 확인 | `config:DescribeConfigurationRecorders` | 필수 | Config 비활성 여부 판단 |
| Config history 조회 | `config:GetResourceConfigHistory` | 필수 | before/after 보강 |
| 미사용 Elastic IP 점검 | `ec2:DescribeAddresses` | 선택 | advisor checks 사용 시 |
| 미연결 EBS 볼륨 점검 | `ec2:DescribeVolumes` | 선택 | advisor checks 사용 시 |
| RDS 백업/Multi-AZ 점검 | `rds:DescribeDBInstances` | 선택 | advisor checks 사용 시 |

현재 템플릿 기준:
- 필수 권한: CloudTrail + Config
- 운영 점검까지 사용할 경우: EC2 / RDS 조회 권한 포함

주의:
- Security Hub, AWS Health 이벤트는 현재 Worker가 **payload 기반 이벤트 정보** 를 받아 처리하는 경로가 중심입니다
- 즉 현재 MVP 기준으로는 고객 계정 Role에 Security Hub / Health 조회 권한을 기본 필수로 두지 않습니다
- 추후 Worker가 해당 서비스 API를 직접 조회하게 되면 별도 권한 표를 추가해야 합니다

---

## 2. 고객 계정에 필요한 리소스

고객 계정에는 아래 하나만 준비되면 됩니다.

- DnDn Worker가 AssumeRole 할 수 있는 Read-only IAM Role 1개

권장 이름 예:
- `DnDnCollectorReadRole`

이 Role은 아래 두 가지로 구성됩니다.

1. Trust Policy
- DnDn 측 principal ARN만 AssumeRole 가능
- `sts:ExternalId` 일치 조건 필수

2. Permissions Policy
- Worker가 실제로 호출하는 AWS 읽기 권한만 허용

템플릿 파일:
- [customer_trust_policy.json](iam_templates/customer_trust_policy.json)
- [customer_permissions_policy.json](iam_templates/customer_permissions_policy.json)

---

## 3. 온보딩 절차

### 3-1. DnDn 측 값 준비

고객사에 아래 값을 전달합니다.

- `dndn_principal_arn`
- `external_id`
- 권장 Role 이름

예:

```text
dndn_principal_arn = arn:aws:iam::123456789012:role/DnDnWorkerRole
external_id = dndn-tenant-abc
role_name = DnDnCollectorReadRole
```

### 3-2. 템플릿 렌더링

```bash
python apps/worker/tools/render_iam_templates.py \
  --dndn-principal-arn arn:aws:iam::123456789012:role/DnDnWorkerRole \
  --external-id dndn-tenant-abc
```

생성 파일:
- `out/iam_rendered/customer_trust_policy.rendered.json`
- `out/iam_rendered/customer_permissions_policy.rendered.json`

### 3-3. 고객 계정에 Role 생성

고객사는 렌더링된 Trust Policy / Permissions Policy를 사용해 Role을 생성합니다.

확정되어야 하는 값:
- `account_id`
- `role_arn`
- `external_id`

이 세 값은 이후 API payload와 linked account 설정의 핵심 입력이 됩니다.

### 3-4. AssumeRole 검증

먼저 STS AssumeRole 자체가 되는지 확인합니다.

```bash
python apps/worker/tools/smoke_assume_role.py \
  --role-arn arn:aws:iam::123456789012:role/DnDnCollectorReadRole \
  --external-id dndn-tenant-abc
```

성공 기준:
- `sts:GetCallerIdentity` 결과가 대상 고객 계정으로 나옴

### 3-5. CloudTrail 조회 검증

```bash
python apps/worker/tools/smoke_cloudtrail.py \
  --role-arn arn:aws:iam::123456789012:role/DnDnCollectorReadRole \
  --external-id dndn-tenant-abc \
  --region ap-northeast-2
```

성공 기준:
- `LookupEvents` 호출이 AccessDenied 없이 수행됨

### 3-6. Worker payload 스모크

이후에는 실제 payload 실행으로 연결합니다.

권장 확인 순서:
1. `run_payload.py` 로 EVENT payload 실행
2. `run_payload.py` 로 WEEKLY payload 실행
3. `normalized/canonical.json` 또는 `normalized/event.json` 생성 확인
4. `collection_status.assume_role/cloudtrail/config` 상태 확인

---

## 4. 권한 실패 시 해석 기준

권한 또는 서비스 상태는 아래 기준으로 해석합니다.

### 실패(FAILED)로 보는 경우
- Role Assume 자체 실패
- 외부 ID 불일치
- Worker 실행 자체를 더 진행할 수 없는 인증 단계 실패

대표 코드:
- `ASSUME_ROLE_FAILED`
- `INVALID_EXTERNAL_ID`

### N/A로 보는 경우
- 서비스 자체가 비활성화되어 수집이 원천적으로 불가능
- 해당 리전이 비활성/옵트인 미사용
- 지정 기간에 데이터가 없음
- CloudTrail / Config 단계에서 고객 계정 권한 부족으로 수집이 불가능

관련 기준:
- [na_rules.md](../../contracts/na_rules.md)
- [error_codes.md](../../contracts/error_codes.md)

예:
- Config recorder 비활성 -> `NA(SERVICE_DISABLED)`
- 기간 내 CloudTrail WRITE 이벤트 없음 -> `NA(NO_DATA)`
- CloudTrail / Config AccessDenied -> `NA(PERMISSION_DENIED)`

---

## 5. 운영 체크리스트

- [ ] 고객 계정 Role 이름 확정
- [ ] Trust Policy에 DnDn principal ARN 반영
- [ ] Trust Policy에 ExternalId 조건 반영
- [ ] Permissions Policy가 최소 권한 기준과 일치
- [ ] `smoke_assume_role.py` 통과
- [ ] `smoke_cloudtrail.py` 통과
- [ ] EVENT payload 스모크 통과
- [ ] WEEKLY payload 스모크 통과

---

## 6. D / API 팀과 맞춰야 하는 값

다음 값은 Worker 단독 정보가 아니라 다른 파트와 반드시 맞춰야 합니다.

- `account_id`
- `role_arn`
- `external_id`
- 수집 대상 `regions`
- 결과 저장 `s3.bucket`, `s3.prefix`

특히 API 팀은 Worker payload를 만들 때 아래 값을 정확히 채워야 합니다.

- `account_id`
- `assume_role.role_arn`
- `assume_role.external_id`
- `regions`

---

## 7. 후속 확장 시 업데이트가 필요한 항목

아래 기능이 실제 수집 API 호출로 추가되면 이 문서를 같이 갱신해야 합니다.

- Security Hub 직접 조회
- Access Analyzer 직접 조회
- Cost Explorer 직접 조회
- CloudWatch 직접 조회

즉, 권한 정책은 Worker 기능 확장과 항상 같이 버전 관리해야 합니다.
