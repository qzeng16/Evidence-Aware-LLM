#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="${PERFORMANCE_SMOKE_IMAGE:-evidence-llm-api:ci}"
CONTAINER_NAME="${PERFORMANCE_SMOKE_CONTAINER:-evidence-llm-performance-smoke}"

HOST_PORT="${PERFORMANCE_SMOKE_PORT:-8010}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

REQUESTS="${PERFORMANCE_SMOKE_REQUESTS:-20}"
CONCURRENCY="${PERFORMANCE_SMOKE_CONCURRENCY:-4}"
WARMUP="${PERFORMANCE_SMOKE_WARMUP:-3}"
TIMEOUT_SECONDS="${PERFORMANCE_SMOKE_TIMEOUT:-30}"

MIN_SUCCESS_RATE="${PERFORMANCE_SMOKE_MIN_SUCCESS_RATE:-1.0}"
MIN_RPS="${PERFORMANCE_SMOKE_MIN_RPS:-1.0}"
MAX_P95_MS="${PERFORMANCE_SMOKE_MAX_P95_MS:-5000}"

CPU_LIMIT="${PERFORMANCE_SMOKE_CPU_LIMIT:-2}"
MEMORY_LIMIT="${PERFORMANCE_SMOKE_MEMORY_LIMIT:-4g}"

TEMP_DIR="$(mktemp -d)"
REPORT_FILE="${TEMP_DIR}/performance-smoke.json"

cleanup() {
  docker rm -f \
    "$CONTAINER_NAME" \
    >/dev/null 2>&1 || true

  rm -rf "$TEMP_DIR"
}

show_logs() {
  echo
  echo "===== Performance smoke container logs ====="

  docker logs \
    "$CONTAINER_NAME" \
    2>&1 || true

  echo "============================================"
}

trap cleanup EXIT

for command_name in docker curl python; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "${command_name} is not available." >&2
    exit 1
  fi
done

if ! docker image inspect \
  "$IMAGE_NAME" \
  >/dev/null 2>&1
then
  echo "Docker image is not available: ${IMAGE_NAME}" >&2
  exit 1
fi

docker rm -f \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "Starting performance smoke container"
echo "========================================"
echo "Image: ${IMAGE_NAME}"
echo "Resources: ${CPU_LIMIT} CPU / ${MEMORY_LIMIT}"
echo

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:${HOST_PORT}:8000" \
  --cpus "$CPU_LIMIT" \
  --memory "$MEMORY_LIMIT" \
  --env VERIFIER_MODE=rule_only \
  "$IMAGE_NAME" \
  >/dev/null

ready="false"

for attempt in $(seq 1 90); do
  status_code="$(
    curl \
      --silent \
      --output /dev/null \
      --write-out "%{http_code}" \
      --max-time 5 \
      "${BASE_URL}/ready" \
      2>/dev/null \
      || true
  )"

  if [[ "$status_code" == "200" ]]; then
    ready="true"
    break
  fi

  if ! docker ps \
    --format '{{.Names}}' \
    | grep -qx "$CONTAINER_NAME"
  then
    echo "Container stopped before becoming ready." >&2
    show_logs
    exit 1
  fi

  sleep 2
done

if [[ "$ready" != "true" ]]; then
  echo "Service did not become ready before timeout." >&2
  show_logs
  exit 1
fi

echo
echo "========================================"
echo "Running /verify performance smoke test"
echo "========================================"

python scripts/load_test_api.py \
  --base-url "$BASE_URL" \
  --endpoint verify \
  --requests "$REQUESTS" \
  --concurrency "$CONCURRENCY" \
  --warmup "$WARMUP" \
  --timeout "$TIMEOUT_SECONDS" \
  --min-success-rate 0.0 \
  --output "$REPORT_FILE" \
  >/dev/null

export REPORT_FILE
export REQUESTS
export MIN_SUCCESS_RATE
export MIN_RPS
export MAX_P95_MS

python - <<'__PERFORMANCE_SMOKE_VALIDATE_EOF__'
import json
import os
from pathlib import Path

from app.performance_gate import (
    evaluate_performance_gate,
)


report_path = Path(
    os.environ["REPORT_FILE"]
)

try:
    report = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    summary = report["results"]

    errors = evaluate_performance_gate(
        summary,
        expected_requests=int(
            os.environ["REQUESTS"]
        ),
        min_success_rate=float(
            os.environ["MIN_SUCCESS_RATE"]
        ),
        min_throughput_rps=float(
            os.environ["MIN_RPS"]
        ),
        max_p95_latency_ms=float(
            os.environ["MAX_P95_MS"]
        ),
    )

except (
    KeyError,
    TypeError,
    ValueError,
    json.JSONDecodeError,
) as error:
    raise SystemExit(
        "Performance smoke report is malformed: "
        + type(error).__name__
    )

print()
print("Performance smoke results")
print("-------------------------")
print(
    "Completed requests: {}".format(
        summary["completed_requests"]
    )
)
print(
    "Success rate: {:.1%}".format(
        summary["success_rate"]
    )
)
print(
    "Throughput: {:.3f} requests/second".format(
        summary["throughput_rps"]
    )
)
print(
    "Average latency: {:.3f} ms".format(
        summary["latency_ms"]["average"]
    )
)
print(
    "P95 latency: {:.3f} ms".format(
        summary["latency_ms"]["p95"]
    )
)

if errors:
    print()
    print("Performance smoke gate failed:")

    for error in errors:
        print("- " + error)

    raise SystemExit(1)

print()
print("Performance smoke gate passed")
__PERFORMANCE_SMOKE_VALIDATE_EOF__
