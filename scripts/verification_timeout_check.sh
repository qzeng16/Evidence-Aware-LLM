#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="${TIMEOUT_CHECK_IMAGE:-evidence-llm-api:timeout-check}"
CONTAINER_NAME="${TIMEOUT_CHECK_CONTAINER:-evidence-llm-timeout-check}"

HOST_PORT="${TIMEOUT_CHECK_PORT:-8013}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

PRIVATE_CLAIM="layer92-private-slow-claim-sk-proj-secret"

TEMP_DIR="$(mktemp -d)"

cleanup() {
  docker rm -f \
    "$CONTAINER_NAME" \
    >/dev/null 2>&1 || true

  rm -rf "$TEMP_DIR"
}

show_logs() {
  echo
  echo "===== Timeout container logs ====="

  docker logs \
    "$CONTAINER_NAME" \
    2>&1 || true

  echo "=================================="
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
echo "1. Building timeout-check image"
echo "========================================"

docker build \
  --tag "$IMAGE_NAME" \
  .

docker rm -f \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "2. Starting deterministic slow verifier"
echo "========================================"
echo "Concurrent execution limit: 1"
echo "Execution timeout: 0.05 seconds"
echo "Slow task duration: 1.0 second"

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:${HOST_PORT}:8000" \
  --cpus 2 \
  --memory 4g \
  --env VERIFIER_MODE=rule_only \
  "$IMAGE_NAME" \
  sh -c \
  'exec python -m uvicorn timeout_integration_app:app --app-dir /app/scripts --host 0.0.0.0 --port 8000' \
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
  echo "Timeout test service did not become ready." >&2
  show_logs
  exit 1
fi

echo
echo "========================================"
echo "3. Exercising timeout and slot retention"
echo "========================================"

export BASE_URL
export PRIVATE_CLAIM

python - <<'__TIMEOUT_HTTP_VALIDATION_EOF__'
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prometheus_client.parser import (
    text_string_to_metric_families,
)


base_url = os.environ["BASE_URL"]
private_claim = os.environ["PRIVATE_CLAIM"]


def http_request(
    method,
    path,
    *,
    claim=None,
    request_id=None,
):
    """Send one JSON request and preserve error responses."""

    payload = None

    headers = {
        "Accept": "application/json",
    }

    if claim is not None:
        payload = json.dumps(
            {
                "claim": claim,
            }
        ).encode("utf-8")

        headers[
            "Content-Type"
        ] = "application/json"

    if request_id is not None:
        headers[
            "X-Request-ID"
        ] = request_id

    request = Request(
        base_url + path,
        data=payload,
        method=method,
        headers=headers,
    )

    try:
        with urlopen(
            request,
            timeout=10.0,
        ) as response:
            raw_body = response.read()

            return {
                "status_code": response.status,
                "headers": {
                    key.lower(): value
                    for key, value
                    in response.headers.items()
                },
                "raw_body": raw_body,
                "body": json.loads(
                    raw_body.decode("utf-8")
                ),
            }

    except HTTPError as error:
        raw_body = error.read()

        return {
            "status_code": error.code,
            "headers": {
                key.lower(): value
                for key, value
                in error.headers.items()
            },
            "raw_body": raw_body,
            "body": json.loads(
                raw_body.decode("utf-8")
            ),
        }


def expect_request_id(
    result,
    expected_request_id,
):
    """Validate response/header request-ID consistency."""

    if (
        result["body"].get("request_id")
        != expected_request_id
    ):
        raise SystemExit(
            "Response body request ID was inconsistent."
        )

    if (
        result["headers"].get("x-request-id")
        != expected_request_id
    ):
        raise SystemExit(
            "Response header request ID was inconsistent."
        )


timeout_request_id = "layer92-timeout-001"

started_at = time.monotonic()

timed_out = http_request(
    "POST",
    "/verify",
    claim=private_claim,
    request_id=timeout_request_id,
)

timeout_elapsed = (
    time.monotonic()
    - started_at
)

if timed_out["status_code"] != 504:
    raise SystemExit(
        "Slow verification did not return HTTP 504."
    )

timeout_error = timed_out[
    "body"
].get(
    "error",
    {},
)

if (
    timeout_error.get("type")
    != "verification_timeout"
):
    raise SystemExit(
        "HTTP 504 used an unexpected error type."
    )

if (
    timeout_error.get("code")
    != "verification_timeout"
):
    raise SystemExit(
        "HTTP 504 did not include the stable timeout code."
    )

if timeout_error.get("retryable") is not True:
    raise SystemExit(
        "Verification timeout was not marked retryable."
    )

expect_request_id(
    timed_out,
    timeout_request_id,
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

if timeout_elapsed >= 0.8:
    raise SystemExit(
        "HTTP timeout response waited for the "
        "background task to finish."
    )


overload_request_id = "layer92-overload-001"

overloaded = http_request(
    "POST",
    "/verify",
    claim="Second verification claim.",
    request_id=overload_request_id,
)

if overloaded["status_code"] != 429:
    raise SystemExit(
        "Second request did not return HTTP 429 "
        "while the timed-out task was still running."
    )

overload_error = overloaded[
    "body"
].get(
    "error",
    {},
)

if (
    overload_error.get("type")
    != "service_overloaded"
):
    raise SystemExit(
        "HTTP 429 used an unexpected error type."
    )

if (
    overloaded["headers"].get(
        "retry-after"
    )
    != "1"
):
    raise SystemExit(
        "HTTP 429 did not include Retry-After: 1."
    )

expect_request_id(
    overloaded,
    overload_request_id,
)


live = http_request(
    "GET",
    "/live",
)

ready = http_request(
    "GET",
    "/ready",
)

if live["status_code"] != 200:
    raise SystemExit(
        "/live failed while the background task ran."
    )

if ready["status_code"] != 200:
    raise SystemExit(
        "/ready failed while the background task ran."
    )


time.sleep(1.2)

completed_request_id = "layer92-completed-001"

completed = http_request(
    "POST",
    "/verify",
    claim="Third verification claim.",
    request_id=completed_request_id,
)

if completed["status_code"] != 200:
    raise SystemExit(
        "Verification slot was not released after "
        "the background task completed."
    )

if completed["body"].get("status") != "success":
    raise SystemExit(
        "Third request did not use the success contract."
    )

expect_request_id(
    completed,
    completed_request_id,
)


metrics_response = http_request(
    "GET",
    "/metrics",
)

metrics_text = metrics_response[
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
    """Return one Prometheus metric sample."""

    expected_labels = labels or {}

    for sample in samples:
        if (
            sample.name == name
            and sample.labels == expected_labels
        ):
            return float(sample.value)

    return 0.0


timeout_total = metric_value(
    "evidence_verification_timeouts_total"
)

execution_count = metric_value(
    (
        "evidence_verification_"
        "execution_duration_seconds_count"
    )
)

rejected_total = metric_value(
    "evidence_verification_rejected_total"
)

timeout_errors = metric_value(
    "evidence_verification_errors_total",
    {
        "error_type": "verification_timeout",
    },
)

overload_errors = metric_value(
    "evidence_verification_errors_total",
    {
        "error_type": "service_overloaded",
    },
)

in_flight = metric_value(
    "evidence_verification_in_flight"
)

if timeout_total < 1.0:
    raise SystemExit(
        "Timeout counter was not updated."
    )

if execution_count < 2.0:
    raise SystemExit(
        "Execution duration did not observe "
        "completed background tasks."
    )

if rejected_total < 1.0:
    raise SystemExit(
        "Rejected-request counter was not updated."
    )

if timeout_errors < 1.0:
    raise SystemExit(
        "Timeout error metric was not updated."
    )

if overload_errors < 1.0:
    raise SystemExit(
        "Overload error metric was not updated."
    )

if in_flight != 0.0:
    raise SystemExit(
        "In-flight gauge did not return to zero."
    )


print()
print("Verification timeout results")
print("----------------------------")
print(
    "Slow request: HTTP 504 in {:.3f} seconds".format(
        timeout_elapsed
    )
)
print(
    "Request during background execution: HTTP 429"
)
print(
    "Request after background completion: HTTP 200"
)
print("Liveness during execution: HTTP 200")
print("Readiness during execution: HTTP 200")
print(
    "Timeout counter: {}".format(
        timeout_total
    )
)
print(
    "Execution duration observations: {}".format(
        execution_count
    )
)
print(
    "Rejected counter: {}".format(
        rejected_total
    )
)
print(
    "In-flight after completion: {}".format(
        in_flight
    )
)
__TIMEOUT_HTTP_VALIDATION_EOF__

sleep 1

docker logs \
  "$CONTAINER_NAME" \
  > "${TEMP_DIR}/container.log" \
  2>&1

if grep \
  --fixed-strings \
  --quiet \
  "$PRIVATE_CLAIM" \
  "${TEMP_DIR}/container.log"
then
  echo \
    "Private claim appeared in container logs." \
    >&2

  exit 1
fi

echo "Private claim absent from logs"
echo
echo "Verification timeout check passed"

echo
echo "========================================"
echo "Docker timeout check completed"
echo "========================================"
