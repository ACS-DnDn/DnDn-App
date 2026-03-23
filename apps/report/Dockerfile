FROM python:3.12-slim

# uv 설치
RUN pip install uv

WORKDIR /app

# 의존성 먼저 복사 (캐시 활용)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# non-root 실행을 위해 venv 권한 설정
RUN chmod -R o+rx /app/.venv

# 소스 복사
COPY src/ ./src/

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
