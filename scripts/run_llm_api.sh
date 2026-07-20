#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$ROOT_DIR"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  read -r -s -p "Paste OpenAI API key: " OPENAI_API_KEY
  printf "\n"
fi

if [[ -z "${OPENAI_API_KEY}" ]]; then
  echo "OPENAI_API_KEY cannot be empty." >&2
  exit 1
fi

export OPENAI_API_KEY
export VERIFIER_MODE="llm_only"
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-5-mini}"
export OPENAI_TIMEOUT_SECONDS="${OPENAI_TIMEOUT_SECONDS:-30}"
export OPENAI_MAX_RETRIES="${OPENAI_MAX_RETRIES:-0}"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "Starting evidence verification API..."
echo "Verifier mode: ${VERIFIER_MODE}"
echo "OpenAI model: ${OPENAI_MODEL}"
echo "API key configured: true"
echo "Address: http://${HOST}:${PORT}"

exec python3 -m uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT"
