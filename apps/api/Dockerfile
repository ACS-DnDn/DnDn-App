FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# import 경로가 apps.api.src.* 이므로 repo root 기준 구조 유지
COPY apps/api/src ./apps/api/src

EXPOSE 8000

CMD ["uvicorn", "apps.api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
