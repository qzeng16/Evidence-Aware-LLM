#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="evidence-aware-llm:release-check"
CONTAINER_NAME="evidence-aware-llm-release-check"
HOST_PORT="${HOST_PORT:-8001}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

TEMP_DIR="$(mktemp -d)"
LIVE_FILE="${TEMP_DIR}/live.json"
READY_FILE="${TEMP_DIR}/ready.json"
HEALTH_FILE="${TEMP_DIR}/health.json"
VERIFY_FILE="${TEMP_DIR}/verify.json"

cleanup() {
  docker rm -f \
    "$CONTAINER_NAME" \
    >/dev/null 2>&1 || true

  rm -rf "$TEMP_DIR"
}

show_container_logs() {
  echo
  echo "===== Container logs ====="

  docker logs \
    "$CONTAINER_NAME" \
    2>&1 || true

  echo "=========================="
}

trap cleanup EXIT

echo "========================================"
echo "1. Running complete test suite"
echo "========================================"

make test

echo
echo "========================================"
echo "2. Building Docker image"
echo "========================================"

docker build \
  --tag "$IMAGE_NAME" \
  .

docker rm -f \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "3. Starting rule-only container"
echo "========================================"

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "${HOST_PORT}:8000" \
  --env VERIFIER_MODE=rule_only \
  "$IMAGE_NAME" \
  >/dev/null

echo
echo "Waiting for API readiness..."

READY="false"

for attempt in $(seq 1 120); do
  HTTP_STATUS="$(
    curl \
      --silent \
      --output "$READY_FILE" \
      --write-out "%{http_code}" \
      --max-time 5 \
      "${BASE_URL}/ready" \
      2>/dev/null \
      || true
  )"

  if [[ "$HTTP_STATUS" == "200" ]]; then
    READY="true"
    break
  fi

  if ! docker ps \
    --format '{{.Names}}' \
    | grep -qx "$CONTAINER_NAME"; then
    echo "Container stopped before becoming ready."
    show_container_logs
    exit 1
  fi

  sleep 2
done

if [[ "$READY" != "true" ]]; then
  echo "API did not become ready before timeout."
  show_container_logs
  exit 1
fi

echo
echo "========================================"
echo "4. Validating /live, /ready and /health"
echo "========================================"

curl \
  --fail \
  --silent \
  --show-error \
  --max-time 30 \
  "${BASE_URL}/live" \
  > "$LIVE_FILE"

curl \
  --fail \
  --silent \
  --show-error \
  --max-time 30 \
  "${BASE_URL}/health" \
  > "$HEALTH_FILE"

python3 - "$LIVE_FILE" "$READY_FILE" <<'PY'
import json
import sys
from pathlib import Path


live = json.loads(
    Path(sys.argv[1]).read_text(
        encoding="utf-8"
    )
)

ready = json.loads(
    Path(sys.argv[2]).read_text(
        encoding="utf-8"
    )
)

if live.get("status") != "alive":
    raise SystemExit(
        "/live did not report status=alive."
    )

if live.get("data", {}).get("alive") is not True:
    raise SystemExit(
        "/live did not report data.alive=true."
    )

if ready.get("status") != "ready":
    raise SystemExit(
        "/ready did not report status=ready."
    )

if ready.get("data", {}).get("ready") is not True:
    raise SystemExit(
        "/ready did not report data.ready=true."
    )

metadata = ready.get("metadata")

if not isinstance(metadata, dict):
    raise SystemExit(
        "/ready metadata is missing."
    )

expected = {
    "status": "ready",
    "ready": True,
    "verifier_mode": "rule_only",
    "active_verifier_mode": "rule",
    "llm_verifier_available": False,
}

for field_name, expected_value in expected.items():
    actual_value = metadata.get(field_name)

    if actual_value != expected_value:
        raise SystemExit(
            "/ready metadata {}: expected {!r}, "
            "got {!r}.".format(
                field_name,
                expected_value,
                actual_value,
            )
        )

if "initialization_error" in metadata:
    raise SystemExit(
        "/ready exposed initialization_error."
    )
PY

python3 - "$HEALTH_FILE" <<'PY'
import json
import sys
from pathlib import Path


path = Path(sys.argv[1])

status = json.loads(
    path.read_text(encoding="utf-8")
)

expected = {
    "status": "ready",
    "verifier_mode": "rule_only",
    "active_verifier_mode": "rule",
    "llm_verifier_available": False,
}

errors = []

if "initialization_error" in status:
    errors.append(
        "/health exposed initialization_error."
    )

for field_name, expected_value in expected.items():
    actual_value = status.get(field_name)

    if actual_value != expected_value:
        errors.append(
            f"{field_name}: expected "
            f"{expected_value!r}, got "
            f"{actual_value!r}"
        )

serialized = json.dumps(status)

for forbidden_pattern in (
    "OPENAI_API_KEY",
    "sk-proj-",
):
    if forbidden_pattern in serialized:
        errors.append(
            "Health response exposed forbidden "
            f"content: {forbidden_pattern}"
        )

if errors:
    print(
        json.dumps(
            status,
            indent=2,
            ensure_ascii=False,
        )
    )

    raise SystemExit(
        "Health validation failed:\n- "
        + "\n- ".join(errors)
    )

print(
    json.dumps(
        status,
        indent=2,
        ensure_ascii=False,
    )
)
PY

echo
echo "========================================"
echo "5. Validating /verify"
echo "========================================"

curl \
  --fail \
  --silent \
  --show-error \
  --max-time 60 \
  --request POST \
  "${BASE_URL}/verify" \
  --header "Content-Type: application/json" \
  --data '{
    "claim": "Retrieval augmented generation can improve factual reliability."
  }' \
  > "$VERIFY_FILE"

python3 - "$VERIFY_FILE" <<'PY'
import json
import sys
from pathlib import Path


path = Path(sys.argv[1])

response = json.loads(
    path.read_text(encoding="utf-8")
)

errors = []

if response.get("status") != "success":
    errors.append(
        "Response status is not success."
    )

data = response.get("data")

if not isinstance(data, dict):
    errors.append(
        "Response data is missing."
    )
    data = {}

verification = data.get("verification")

if not isinstance(verification, dict):
    errors.append(
        "Unified verification result is missing."
    )
    verification = {}

if verification.get(
    "verifier_type"
) != "rule":
    errors.append(
        "Expected verifier_type='rule', got "
        f"{verification.get('verifier_type')!r}."
    )

if verification.get("label") not in {
    "Supported",
    "Refuted",
    "Uncertain",
}:
    errors.append(
        "Verification label is invalid."
    )

metadata = response.get("metadata")

if not isinstance(metadata, dict):
    errors.append(
        "Response metadata is missing."
    )
    metadata = {}

if metadata.get(
    "active_verifier_mode"
) != "rule":
    errors.append(
        "Expected active_verifier_mode='rule'."
    )

serialized = json.dumps(response)

for forbidden_pattern in (
    "OPENAI_API_KEY",
    "sk-proj-",
):
    if forbidden_pattern in serialized:
        errors.append(
            "Verification response exposed "
            f"forbidden content: {forbidden_pattern}"
        )

if errors:
    print(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
        )
    )

    raise SystemExit(
        "Verification validation failed:\n- "
        + "\n- ".join(errors)
    )

safe_summary = {
    "status": response["status"],
    "label": verification.get("label"),
    "confidence": verification.get(
        "confidence"
    ),
    "verifier_type": verification.get(
        "verifier_type"
    ),
    "matched_evidence_ids": verification.get(
        "matched_evidence_ids"
    ),
    "active_verifier_mode": metadata.get(
        "active_verifier_mode"
    ),
}

print(
    json.dumps(
        safe_summary,
        indent=2,
        ensure_ascii=False,
    )
)
PY

echo
echo "========================================"
echo "Release check passed"
echo "========================================"
echo
echo "Verified:"
echo "- complete Python test suite"
echo "- Docker image build"
echo "- container startup"
echo "- rule_only health endpoint"
echo "- rule_only verification endpoint"
echo "- unified verification response"
echo "- no API-key exposure"
