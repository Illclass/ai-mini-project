FROM python:3.11-slim-bookworm AS base
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/models
RUN apt-get update && apt-get install -y --no-install-recommends bash ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir 'torch==2.6.0' --index-url https://download.pytorch.org/whl/cpu
COPY frontend/deploy/healthcheck.py /app/deploy/healthcheck.py

FROM base AS rag
COPY rag-service/requirements-e.txt /app/requirements.txt
# JWT is already declared by the project's voice requirements; reuse its version.
RUN pip install --no-cache-dir -r requirements.txt 'python-jose[cryptography]==3.3.0' \
    && python -m venv --system-site-packages /app/.venv
COPY rag-service /app/rag-service
COPY frontend/deploy/init-index.sh /app/deploy/init-index.sh

FROM base AS voice
COPY voice-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY voice-service /app/voice-service
