# API

`apps/api`는 DnDn의 메인 백엔드 API입니다. 인증, 문서 결재, 워크스페이스, GitHub/Slack 연동, 보고서 생성 요청을 담당합니다.

## 실행

`apps/api` 내부 코드가 `apps.api.src.*` import를 사용하므로 레포 루트에서 실행하는 것을 권장합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
cp apps/api/.env.example apps/api/.env
set -a
source apps/api/.env
set +a
PYTHONPATH=. uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload
```

- Health check: `GET http://localhost:8000/health`
- 기본 API prefix: `/api`

## 주요 라우터

`apps/api/src/main.py` 기준 등록 순서:

- `/api/auth`
- `/api/dashboard`
- `/api/documents`
- `/api/org`
- `/api/github`
- `/api/report-settings`
- `/api/reports`
- `/api/workspaces`
- `/api/hr/users`
- `/api/hr/departments`
- `/api/hr/company`
- `/api/admin/companies`
- `/api/slack`
- `/internal`

## 환경변수

예시 파일은 `apps/api/.env.example`에 있습니다. 실제로 자주 쓰는 항목은 아래입니다.

주의: 현재 `apps/api`는 `.env`를 자동 로드하지 않습니다. 로컬 실행 전 셸에서 `source apps/api/.env`로 환경변수를 먼저 올려야 합니다.

- DB: `SQLALCHEMY_DATABASE_URL`
- AWS/S3: `AWS_REGION`, `S3_BUCKET`, `S3_PUBLIC_BUCKET`
- Cognito: `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`
- STS: `STS_ROLE_NAME`, `STS_EXTERNAL_ID`, `PLATFORM_ACCOUNT_ID`, `CFN_TEMPLATE_URL`
- EventBridge/Scheduler: `EVENT_BUS_ARN`, `SCHEDULER_GROUP_NAME`, `SCHEDULER_ROLE_ARN`, `SCHEDULER_TARGET_ARN`
- Queue/Internal: `REPORT_REQUEST_QUEUE_URL`, `INTERNAL_API_KEY`
- GitHub OAuth: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_WEBHOOK_URL`
- Slack OAuth: `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI`

## 구현 메모

- 서버 시작 시 SQLAlchemy `create_all`과 일부 컬럼 보정 로직이 함께 실행됩니다.
- 워크스페이스 `code` 백필 및 unique index 생성도 `main.py`에서 수행합니다.
- 인증은 Cognito JWT 기반이며, GitHub/Slack OAuth 연동 라우터가 포함되어 있습니다.

## 테스트

### 환경 준비

테스트는 **MySQL 없이** SQLite 인메모리 DB로 실행됩니다. 테스트 전용 패키지를 추가로 설치합니다.

```bash
# 레포 루트에서
pip install -r apps/api/requirements.txt
pip install -r apps/api/requirements-test.txt
```

### 실행

```bash
# 레포 루트에서 실행 (apps.api.src.* import 경로 유지)
python -m pytest apps/api/tests/ -v

# 특정 파일만
python -m pytest apps/api/tests/test_org.py -v

# 특정 테스트 클래스만
python -m pytest apps/api/tests/test_hr_users.py::TestCreateUser -v

# 실패한 테스트만 재실행
python -m pytest apps/api/tests/ --lf
```

### 구조

```text
apps/api/
├── pytest.ini               # testpaths, 출력 옵션
├── requirements-test.txt    # pytest, httpx
└── tests/
    ├── conftest.py          # 공통 픽스처 (DB, 인증 오버라이드)
    ├── test_org.py          # GET /api/org/members
    ├── test_hr_users.py     # /api/hr/users CRUD
    ├── test_hr_departments.py  # /api/hr/departments CRUD
    └── test_dashboard.py    # GET /api/dashboard
```

### 설계 원칙

| 항목 | 방식 |
|------|------|
| DB | SQLite 인메모리 + `StaticPool` (커밋 후에도 단일 커넥션 유지) |
| 인증 | `get_current_user` 의존성 오버라이드로 JWT 우회 |
| Cognito | `unittest.mock.patch`로 `admin_create_user` 등 목 처리 |
| 테스트 격리 | 함수마다 새 엔진/세션 생성, 테스트 간 데이터 오염 없음 |

### 테스트 명세

#### `test_org.py` — 조직도 멤버 조회 (9개)

| 테스트 | 검증 내용 |
|--------|-----------|
| `test_returns_own_company_users` | 같은 회사 직원이 목록에 포함된다 |
| `test_excludes_other_company_users` | 다른 회사 직원은 목록에 없다 |
| `test_keyword_filter_by_name` | 이름으로 검색 시 일치하는 사람만 반환 |
| `test_keyword_filter_by_department` | 부서명으로 검색 시 해당 부서만 반환 |
| `test_users_grouped_by_department` | 직원이 소속 부서 그룹에 묶인다 |
| `test_no_department_falls_back_to_default` | 부서 없는 직원은 기본 부서명 그룹에 속한다 |
| `test_member_item_has_required_fields` | 응답 항목에 id·name·rank 필드가 있다 |
| `test_position_used_as_rank` | position 값이 rank로 내려온다 |
| `test_no_position_falls_back_to_default_rank` | position 없으면 rank가 "연구원"이다 |

#### `test_hr_users.py` — HR 사원 관리 (25개)

| 클래스 | 테스트 | 검증 내용 |
|--------|--------|-----------|
| `TestListUsers` | `test_hr_lists_own_company_users` | HR 담당자는 같은 회사 사원 목록 조회 가능 |
| | `test_member_cannot_list_users` | 일반 사원은 403 HR_ONLY |
| | `test_excludes_other_company_users` | 다른 회사 사원은 목록에 없다 |
| | `test_response_ordered_by_name` | 이름 오름차순 정렬 |
| `TestGetUser` | `test_get_existing_user` | 존재하는 사원 조회 성공 |
| | `test_get_nonexistent_user_returns_404` | 없는 사원은 404 USER_NOT_FOUND |
| | `test_cannot_get_other_company_user` | 다른 회사 사원 조회 시 404 |
| | `test_response_has_required_fields` | 응답에 필수 필드 포함 |
| `TestCreateUser` | `test_create_member_user` | 일반 사원 정상 생성 (Cognito 목) |
| | `test_create_hr_user` | HR 역할 사원 생성 가능 |
| | `test_create_with_leader_role_rejected` | leader 역할 직접 지정 불가 → 400 INVALID_ROLE |
| | `test_create_duplicate_email_returns_409` | 중복 이메일 → 409 EMAIL_ALREADY_EXISTS |
| | `test_cognito_error_propagates` | Cognito 오류 시 해당 상태코드 반환 |
| | `test_member_cannot_create_user` | 일반 사원은 403 |
| `TestUpdateUser` | `test_update_name` | 이름 변경 |
| | `test_update_position` | 직급 변경 |
| | `test_update_role_member_to_hr` | member → hr 역할 변경 가능 |
| | `test_update_role_to_leader_rejected` | leader 역할로 직접 변경 불가 |
| | `test_update_existing_leader_role_rejected` | leader 사용자 역할은 부서관리에서만 변경 |
| | `test_update_nonexistent_user` | 없는 사원 수정 → 404 |
| | `test_member_cannot_update_user` | 일반 사원은 403 |
| `TestDeleteUser` | `test_delete_user_success` | 사원 정상 삭제 |
| | `test_delete_nonexistent_user` | 없는 사원 삭제 → 404 |
| | `test_delete_workspace_owner_blocked` | 워크스페이스 소유자 삭제 불가 → 409 |
| | `test_member_cannot_delete_user` | 일반 사원은 403 |
| `TestResetPassword` | `test_reset_password_success` | 임시 비밀번호 발급 성공 |
| | `test_reset_password_user_not_found` | 없는 사원 → 404 |
| | `test_reset_password_cognito_error` | Cognito 오류 시 500 |

#### `test_hr_departments.py` — HR 부서 관리 (20개)

| 클래스 | 테스트 | 검증 내용 |
|--------|--------|-----------|
| `TestListDepartments` | `test_returns_own_company_departments` | 같은 회사 부서 목록 반환 |
| | `test_excludes_other_company_departments` | 다른 회사 부서는 없다 |
| | `test_member_can_list_departments` | 일반 사원도 부서 목록 조회 가능 |
| | `test_response_has_required_fields` | 응답에 id·name·parentId·leaderId·leaderName 포함 |
| `TestCreateDepartment` | `test_create_root_department` | 최상위 부서 생성 |
| | `test_create_child_department` | 하위 부서 생성 (parentId 지정) |
| | `test_create_with_nonexistent_parent_returns_404` | 없는 부모 부서 → 404 PARENT_NOT_FOUND |
| | `test_member_cannot_create_department` | 일반 사원은 403 |
| `TestDeleteDepartment` | `test_delete_leaf_department` | 자식 없는 부서 삭제 성공 |
| | `test_delete_nonexistent_department` | 없는 부서 → 404 DEPT_NOT_FOUND |
| | `test_delete_department_with_children_blocked` | 하위 부서 있으면 삭제 불가 → 400 HAS_CHILDREN |
| | `test_member_cannot_delete_department` | 일반 사원은 403 |
| `TestSetLeader` | `test_set_leader_promotes_to_leader_role` | 부서장 지정 시 role이 leader로 변경 |
| | `test_set_leader_demotes_old_leader` | 부서장 교체 시 이전 부서장은 member로 강등 |
| | `test_set_leader_hr_role_unchanged` | hr 역할 사용자 부서장 지정 시 role은 hr 유지 |
| | `test_set_leader_nonexistent_department` | 없는 부서 → 404 DEPT_NOT_FOUND |
| | `test_set_leader_nonexistent_user` | 없는 사용자 → 404 USER_NOT_FOUND |
| | `test_unset_leader` | leaderId=null로 부서장 해제 |
| | `test_member_cannot_set_leader` | 일반 사원은 403 |

#### `test_dashboard.py` — 대시보드 (15개)

| 테스트 | 검증 내용 |
|--------|-----------|
| `test_response_structure` | 응답에 docStats·pendingDocs·completedDocs·notices 포함 |
| `test_doc_stats_has_required_fields` | docStats에 pending·ongoing·newDoc 포함 |
| `test_pending_count_includes_approval_waiting` | 결재 대기(current) 건수가 pending에 반영 |
| `test_pending_count_includes_rejected_docs` | 내 반려 문서가 pending에 포함 |
| `test_pending_count_includes_deploy_failed` | 내 배포 실패 문서가 pending에 포함 |
| `test_ongoing_count_counts_progress_docs` | 진행 중 문서 수가 ongoing에 반영 |
| `test_pending_docs_contains_current_approval` | 결재 대기 문서가 pendingDocs에 나타난다 |
| `test_pending_docs_rejected_shown_to_author` | 반려된 내 문서가 pendingDocs에 나타난다 |
| `test_completed_docs_shows_my_docs` | 내 비초안 문서가 completedDocs에 나타난다 |
| `test_completed_docs_excludes_draft` | 임시저장 문서는 completedDocs에 없다 |
| `test_completed_docs_max_5` | completedDocs는 최대 5개 |
| `test_notices_always_present` | 공지사항은 항상 반환된다 |
| `test_new_doc_count_excludes_read_docs` | 이미 읽은 문서는 newDoc 카운트에서 제외 |

---

## 구조

```text
apps/api/
├── src/
│   ├── routers/
│   ├── schemas/
│   ├── security/
│   ├── database.py
│   ├── main.py
│   └── models.py
├── tests/
│   ├── conftest.py
│   ├── test_org.py
│   ├── test_hr_users.py
│   ├── test_hr_departments.py
│   └── test_dashboard.py
├── requirements.txt
├── requirements-test.txt
├── pytest.ini
├── .env.example
└── Dockerfile
```
