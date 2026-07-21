#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="${GRACEFUL_IMAGE:-evidence-llm-api:graceful-shutdown-check}"

CONTAINER_NAME="${
  GRACEFUL_CONTAINER:-
  evidence-llm-graceful-shutdown-check
}"

HOST_PORT="${GRACEFUL_PORT:-8015}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

PRIVATE_SLOW_CLAIM="layer94-private-slow-claim-sk-proj-secret"

TEMP_DIR="$(mktemp -d)"

cleanup() {
  docker rm -f \
    "$CONTAINER_NAME" \
    >/dev/null 2>&1 || true

  rm -rf "$TEMP_DIR"
}

show_logs() {
  echo
  echo "===== Graceful-shutdown container logs ====="

  docker logs \
    "$CONTAINER_NAME" \
    2>&1 || true

  echo "============================================"
}

trap cleanup EXIT

for command_name in docker curl python; do
  if ! command -v \
    "$command_name" \
    >/dev/null 2>&1
  then
    echo "${command_name} is not available." >&2
    exit 1
  fi
done

echo
echo "========================================"
echo "1. Building graceful-shutdown image"
echo "========================================"

docker build \
  --tag "$IMAGE_NAME" \
  .

docker rm -f \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "2. Starting deterministic application"
echo "========================================"
echo "HTTP verification timeout: 0.05 seconds"
echo "Background execution time: 2.0 seconds"
echo "Graceful shutdown timeout: 5.0 seconds"

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:${HOST_PORT}:8000" \
  --cpus 2 \
  --memory 4g \
  --env VERIFIER_MODE=rule_only \
  "$IMAGE_NAME" \
  sh -c \
  'exec python -m uvicorn graceful_shutdown_integration_app:app --app-dir /app/scripts --host 0.0.0.0 --port 8000' \
  >/dev/null

ready="false"

for attempt in $(seq 1 120); do
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

  sleep 1
done

if [[ "$ready" != "true" ]]; then
  echo "Service did not become ready." >&2
  show_logs
  exit 1
fi

echo
echo "========================================"
echo "3. Creating timed-out background work"
echo "========================================"

export BASE_URL
export PRIVATE_SLOW_CLAIM

python - <<'__LAYER94_HTTP_EOF__'
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prometheus_client.parser import (
    text_string_to_metric_families,
)


base_url = os.environ["BASE_URL"]
private_claim = os.environ[
    "PRIVATE_SLOW_CLAIM"
]


def request(
    path,
    *,
    method="GET",
    payload=None,
    request_id=None,
):
    """Send one HTTP request and preserve 4xx/5xx bodies."""

    data = None

    headers = {
        "Accept": "application/json",
    }

    if payload is not None:
        data = json.dumps(
            payload
        ).encode("utf-8")

        headers[
            "Content-Type"
        ] = "application/json"

    if request_id is not None:
        headers[
            "X-Request-ID"
        ] = request_id

    outbound = Request(
        base_url + path,
        data=data,
        method=method,
        headers=headers,
    )

    try:
        response = urlopen(
            outbound,
            timeout=10.0,
        )
    except HTTPError as error:
        response = error

    raw_body = response.read()

    result = {
        "status_code": response.status,
        "headers": {
            name.lower(): value
            for name, value
            in response.headers.items()
        },
        "raw_body": raw_body,
    }

    response.close()

    return result


request_id = "layer94-timeout-001"

started_at = time.monotonic()

timed_out = request(
    "/verify",
    method="POST",
    payload={
        "claim": private_claim,
    },
    request_id=request_id,
)

elapsed = (
    time.monotonic()
    - started_at
)

if timed_out["status_code"] != 504:
    raise SystemExit(
        "Slow request did not return HTTP 504."
    )

body = json.loads(
    timed_out["raw_body"].decode("utf-8")
)

error = body.get(
    "error",
    {},
)

if error.get("type") != "verification_timeout":
    raise SystemExit(
        "HTTP 504 used an unexpected error type."
    )

if error.get("retryable") is not True:
    raise SystemExit(
        "Timeout response was not retryable."
    )

if body.get("request_id") != request_id:
    raise SystemExit(
        "Timeout response body lost its request ID."
    )

if (
    timed_out["headers"].get("x-request-id")
    != request_id
):
    raise SystemExit(
        "Timeout response header lost its request ID."
    )

if elapsed >= 0.8:
    raise SystemExit(
        "HTTP response waited for the background "
        "task to complete."
    )

if private_claim in timed_out[
    "raw_body"
].decode(
    "utf-8",
    errors="replace",
):
    raise SystemExit(
        "Private claim entered the timeout response."
    )


metrics = request(
    "/metrics"
)

if metrics["status_code"] != 200:
    raise SystemExit(
        "/metrics did not return HTTP 200."
    )

metrics_text = metrics[
    "raw_body"
].decode("utf-8")

samples = []

for family in text_string_to_metric_families(
    metrics_text
):
    samples.extend(
        family.samples
    )


def metric_value(
    name,
    labels=None,
):
    expected_labels = labels or {}

    for sample in samples:
        if (
            sample.name == name
            and sample.labels == expected_labels
        ):
            return float(sample.value)

    return 0.0


in_flight = metric_value(
    "evidence_verification_in_flight"
)

timeout_total = metric_value(
    "evidence_verification_timeouts_total"
)

if in_flight != 1.0:
    raise SystemExit(
        "Timed-out background work did not "
        "retain its concurrency slot."
    )

if timeout_total < 1.0:
    raise SystemExit(
        "Timeout metric was not recorded."
    )


print()
print("Pre-shutdown state")
print("------------------")
print(
    "Slow request: HTTP 504 in {:.3f} seconds"
    .format(
        elapsed
    )
)
print(
    "In-flight background tasks: {}"
    .format(
        in_flight
    )
)
print(
    "Timeout counter: {}"
    .format(
        timeout_total
    )
)
__LAYER94_HTTP_EOF__

echo
echo "========================================"
echo "4. Sending SIGTERM to the container"
echo "========================================"

signal_started_at="$(
  python -c \
    'import time; print(time.monotonic())'
)"

docker kill \
  --signal=TERM \
  "$CONTAINER_NAME" \
  >/dev/null

stopped="false"

for attempt in $(seq 1 160); do
  running="$(
    docker inspect \
      --format '{{.State.Running}}' \
      "$CONTAINER_NAME" \
      2>/dev/null \
      || true
  )"

  if [[ "$running" == "false" ]]; then
    stopped="true"
    break
  fi

  sleep 0.1
done

signal_finished_at="$(
  python -c \
    'import time; print(time.monotonic())'
)"

if [[ "$stopped" != "true" ]]; then
  echo "Container did not stop before timeout." >&2
  show_logs
  exit 1
fi

exit_code="$(
  docker inspect \
    --format '{{.State.ExitCode}}' \
    "$CONTAINER_NAME"
)"

docker logs \
  "$CONTAINER_NAME" \
  > "${TEMP_DIR}/container.log" \
  2>&1

python - \
  "$signal_started_at" \
  "$signal_finished_at" \
  "$exit_code" \
  "${TEMP_DIR}/container.log" \
  "$PRIVATE_SLOW_CLAIM" \
  <<'__LAYER94_LOG_EOF__'
import sys
from pathlib import Path


started_at = float(
    sys.argv[1]
)

finished_at = float(
    sys.argv[2]
)

exit_code = int(
    sys.argv[3]
)

log_path = Path(
    sys.argv[4]
)

private_claim = sys.argv[5]

elapsed = (
    finished_at
    - started_at
)

logs = log_path.read_text(
    encoding="utf-8",
    errors="replace",
)

required_markers = (
    "LAYER94_RUNTIME_INITIALIZED",
    "LAYER94_BACKGROUND_STARTED",
    "LAYER94_BACKGROUND_COMPLETED",
    "LAYER94_SERVICE_STATE_RESET",
)

for marker in required_markers:
    if marker not in logs:
        raise SystemExit(
            "Container logs are missing {}."
            .format(
                marker
            )
        )


started_index = logs.index(
    "LAYER94_BACKGROUND_STARTED"
)

completed_index = logs.index(
    "LAYER94_BACKGROUND_COMPLETED"
)

reset_index = logs.index(
    "LAYER94_SERVICE_STATE_RESET"
)

if not (
    started_index
    < completed_index
    < reset_index
):
    raise SystemExit(
        "Shutdown cleanup occurred before "
        "background execution completed."
    )

if private_claim in logs:
    raise SystemExit(
        "Private claim appeared in container logs."
    )

if exit_code != 0:
    raise SystemExit(
        "Container exited with code {}."
        .format(
            exit_code
        )
    )

if elapsed < 1.0:
    raise SystemExit(
        "Container exited too quickly to have "
        "drained background work."
    )

if elapsed > 8.0:
    raise SystemExit(
        "Graceful shutdown exceeded the "
        "expected deadline."
    )


print()
print("Graceful-shutdown results")
print("-------------------------")
print(
    "SIGTERM-to-exit duration: {:.3f} seconds"
    .format(
        elapsed
    )
)
print("Background task completed before cleanup")
print("Service state reset after task completion")
print("Container exit code: 0")
print("Private claim absent from logs")
__LAYER94_LOG_EOF__

echo
echo "Graceful shutdown check passed"

echo
echo "========================================"
echo "Docker graceful-shutdown check completed"
echo "========================================"
