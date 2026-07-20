# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/appuser/.cache/huggingface \
    PORT=8000

WORKDIR /app

# Create a non-root user for running the API.
RUN groupadd --system appuser \
    && useradd --system --gid appuser --create-home appuser

# Copy dependency definitions first so Docker can reuse this layer
# when only application code changes.
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

# Copy the complete project into the image.
COPY --chown=appuser:appuser . /app

# Prepare writable locations for downloaded models, generated
# embeddings, logs, and other runtime files.
RUN mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /home/appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=120s --retries=3 \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:" + os.environ.get("PORT", "8000") + "/live", timeout=3).read()'

CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT}\""]
