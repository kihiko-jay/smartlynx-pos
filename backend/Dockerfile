# Smartlynx Backend — Production Dockerfile

FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r smartlynx && useradd -r -g smartlynx -d /app -s /bin/false smartlynx

COPY --from=builder /install /usr/local
COPY . .

RUN rm -rf \
    tests/ \
    .env \
    .env.example \
    .env.production.example \
    __pycache__ \
    alembic/versions_legacy/__pycache__ \
    alembic/versions_bootstrap/__pycache__ \
    alembic/versions_common/__pycache__ \
    && find . -name "*.pyc" -delete \
    && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

RUN chown -R smartlynx:smartlynx /app

USER smartlynx

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -f \
             --connect-timeout 3 \
             --max-time 8 \
             --no-progress-meter \
             http://localhost:8000/ready \
        || exit 1

CMD ["sh", "-c", \
     "uvicorn app.main:app \
      --host 0.0.0.0 \
      --port 8000 \
      --workers ${WORKERS:-4} \
      --log-level ${LOG_LEVEL:-info} \
      --no-access-log"]
