# DnDn-App 트러블슈팅 가이드

> `feature/integrate-backend` 브랜치 개발 중 발생한 이슈와 해결 방법 정리

---

## 1. apps/report — FastAPI 서버

### 1-1. `NameError: name 'ALLOWED_ORIGINS' is not defined`

**원인**
`app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS)` 호출이 변수 선언보다 앞에 위치.

**해결**
`ALLOWED_ORIGINS` 변수를 `add_middleware` 호출 이전에 선언.

```python
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, ...)
```

---

### 1-2. `ValidationException: invalid model identifier` (AWS Bedrock)

**원인**
`us-east-1` 리전 prefix(`us.anthropic...`)를 사용했으나 실제 리전은 `ap-northeast-2`.

**해결**
Cross-Region Inference prefix는 리전별로 다름.

| 리전 | prefix |
|------|--------|
| Seoul (ap-northeast-2) | `apac.` |
| US East | `us.` |

```python
MODEL_ID = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
REGION = "ap-northeast-2"
```

---

### 1-3. `ResourceNotFoundException: Legacy model` (AWS Bedrock)

**원인**
모델 ID `claude-3-5-sonnet-20240620-v1:0` — 더 이상 지원되지 않는 레거시 버전.

**해결**
최신 버전으로 교체.

```
apac.anthropic.claude-3-5-sonnet-20241022-v2:0
```

---

### 1-4. `JSONDecodeError: Invalid control character` (Claude 응답 파싱)

**원인**
Claude가 JSON 문자열 내부에 리터럴 줄바꿈(`\n`)을 포함해서 응답.
`json.loads()` 기본값은 `strict=True`이므로 제어 문자를 거부.

**해결**
```python
json.loads(clean, strict=False)
```

---

### 1-5. CORS 오류 — `TypeError: Failed to fetch` (OPTIONS 400)

**원인**
프론트엔드가 `localhost:3002`에서 실행 중인데 `.env`의 `ALLOWED_ORIGINS`에 포트 3002가 없음.

**해결**
`apps/report/.env`에 추가:
```
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3002,http://localhost:5173
```

---

### 1-6. `ModuleNotFoundError: No module named 'src'`

**원인**
uvicorn을 프로젝트 루트에서 실행했기 때문. `apps/report` 디렉토리에서 실행해야 함.

**해결**
```bash
cd apps/report
~/.local/bin/uv run uvicorn src.main:app --port 8000 --reload
```

---

### 1-7. MCP `_read()` 무한 블로킹

**원인**
`subprocess.stdout.readline()`이 데이터가 없을 때 무한 대기.

**해결**
`select.select()`로 타임아웃 적용:
```python
import select
ready = select.select([self.proc.stdout], [], [], 0.1)
if ready[0]:
    line = self.proc.stdout.readline()
```

---

## 2. apps/api — FastAPI 서버

### 2-1. `ImportError: cannot import name 'Task' from apps.api.src.models`

**원인**
`dashboard.py`가 `Task` 모델을 import하는데 `models.py`에 정의되지 않음.

**해결**
`apps/api/src/models.py`에 Task 모델 추가:
```python
class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="tasks")
```

---

### 2-2. `RuntimeError: 필수 환경변수 STS_EXTERNAL_ID가 설정되지 않았습니다`

**원인**
`aws_sts.py`가 모듈 로드 시점에 `_require_env()`를 즉시 실행.
`load_dotenv()`가 호출되기 전에 이미 환경변수를 읽으려 함.

**해결**
`apps/api/src/main.py` 최상단에서 먼저 dotenv 로딩:
```python
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")  # 다른 import보다 먼저

from fastapi import FastAPI, ...
```

그리고 `apps/api/.env`에 필수 변수 추가:
```
STS_ROLE_NAME=DnDnOpsAgentRole
STS_EXTERNAL_ID=dndn-ops-agent
PLATFORM_ACCOUNT_ID=451017115109
CFN_TEMPLATE_URL=https://console.aws.amazon.com/cloudformation/home
```

---

### 2-3. `ERROR: [Errno 48] Address already in use` (포트 8001)

**원인**
이전 uvicorn 프로세스가 백그라운드에서 계속 실행 중.

**해결**
```bash
kill $(lsof -ti:8001)
```

---

### 2-4. Cognito JWT 인증 — 개발 환경 bypass

**원인**
`GET /documents` 등 모든 엔드포인트가 유효한 Cognito Bearer 토큰을 요구.
로컬 개발 환경에서는 Cognito 토큰 없이 테스트해야 함.

**해결**
`apps/api/.env`에 DEV_MODE 추가:
```
DEV_MODE=true
DEV_USER_ID=user-001
```

`get_current_user` 함수에 bypass 로직 추가:
```python
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

async def get_current_user(...):
    if DEV_MODE:
        user = db.query(User).filter(User.id == DEV_USER_ID).first()
        return user
    # ... 기존 JWT 검증 로직
```

> ⚠️ 프로덕션에서는 반드시 `DEV_MODE=false`.

---

### 2-5. MySQL 연결 실패 — DB/유저 미생성

**원인**
`database.py`에 하드코딩된 `aiuser:aipassword@localhost:3306/aiproject`에 해당하는 DB와 유저가 없음.

**해결**
MySQL에서 직접 생성:
```sql
CREATE DATABASE IF NOT EXISTS aiproject CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'aiuser'@'localhost' IDENTIFIED BY 'aipassword';
GRANT ALL PRIVILEGES ON aiproject.* TO 'aiuser'@'localhost';
FLUSH PRIVILEGES;
```

테이블은 서버 시작 시 SQLAlchemy가 자동 생성 (`Base.metadata.create_all`).

---

### 2-6. apps/api 실행 시 `ModuleNotFoundError`

**원인**
import 경로가 `apps.api.src.*` 형식이라 프로젝트 루트에서 실행해야 함.

**해결**
```bash
cd /path/to/DnDn-App  # 프로젝트 루트
PYTHONPATH=/path/to/DnDn-App \
  apps/api/.venv/bin/uvicorn apps.api.src.main:app --port 8001 --reload
```

---

## 3. 서버 실행 명령어 요약

```bash
# Terminal 1 — apps/report (AI 생성 + S3)
cd apps/report
~/.local/bin/uv run uvicorn src.main:app --port 8000 --reload

# Terminal 2 — apps/api (문서 관리 + 인증)
cd /path/to/DnDn-App
PYTHONPATH=$(pwd) apps/api/.venv/bin/uvicorn apps.api.src.main:app --port 8001 --reload

# Terminal 3 — apps/web (프론트엔드)
cd apps/web
npm run dev
```

---

## 4. 환경변수 체크리스트

### apps/report/.env
| 변수 | 설명 | 예시 |
|------|------|------|
| `AWS_REGION` | Bedrock/S3 리전 | `ap-northeast-2` |
| `BEDROCK_MODEL_ID` | Claude 모델 ID | `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `S3_BUCKET` | 보고서 저장 버킷 | `dndn-reports` |
| `GITHUB_TOKEN` | Terraform 스타일 참조용 | `ghp_xxxx` |
| `GITHUB_REPO` | Terraform 레포 | `org/repo` |
| `ALLOWED_ORIGINS` | CORS 허용 Origin | `http://localhost:3000,http://localhost:3002` |

### apps/api/.env
| 변수 | 설명 | 예시 |
|------|------|------|
| `AWS_REGION` | Cognito 리전 | `ap-northeast-2` |
| `COGNITO_USER_POOL_ID` | Cognito User Pool | `ap-northeast-2_xxx` |
| `COGNITO_CLIENT_ID` | Cognito App Client | `xxxxx` |
| `STS_EXTERNAL_ID` | STS 교차계정 External ID | `dndn-ops-agent` |
| `PLATFORM_ACCOUNT_ID` | 플랫폼 AWS 계정 ID | `451017115109` |
| `CFN_TEMPLATE_URL` | CloudFormation 템플릿 URL | `https://...` |
| `DEV_MODE` | 개발 환경 auth bypass | `true` / `false` |
| `DEV_USER_ID` | DEV_MODE 사용자 ID | `user-001` |
