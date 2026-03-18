FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY contracts /app/contracts
COPY apps/worker /app/apps/worker

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app/apps/worker \
    && useradd --create-home --shell /usr/sbin/nologin worker \
    && chown -R worker:worker /app

USER worker

ENTRYPOINT ["python", "-m", "dndn_worker.consumer"]
CMD ["--repo-root", "/app", "--out", "/tmp/dndn-out"]
