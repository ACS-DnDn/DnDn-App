FROM python:3.12-slim

# OPA 바이너리 설치
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -L -o /usr/local/bin/opa \
       https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static \
    && chmod +x /usr/local/bin/opa \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install uv

WORKDIR /app

# 의존성 먼저 복사 (캐시 활용)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# Checkov + MCP 서버 사전 설치 (런타임 다운로드 방지)
RUN /app/.venv/bin/pip install checkov \
    && uv tool install awslabs.terraform-mcp-server

# non-root 실행을 위해 venv 권한 설정
RUN chmod -R o+rx /app/.venv

# import 경로가 apps.report.src.* 이므로 컨테이너 안에서도 동일한 경로를 유지
COPY src ./apps/report/src

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "apps.report.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
