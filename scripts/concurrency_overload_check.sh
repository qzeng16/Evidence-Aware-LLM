#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="${CONCURRENCY_CHECK_IMAGE:-evidence-llm-api:concurrency-check}"
CONTAINER_NAME="${CONCURRENCY_CHECK_CONTAINER:-evidence-llm-concurrency-check}"

HOST_PORT="${CONCURRENCY_CHECK_PORT:-8011}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

MAX_CONCURRENT="${MAX_CONCURRENT_VERIFICATIONS:-1}"
QUEUE_TIMEOUT="${VERIFICATION_QUEUE_TIMEOUT_SECONDS:-0.001}"

cleanup() {
  docker rm -f \
    "$CONTAINER_NAME" \
    >/dev/null 2>&1 || true
}

show_logs() {
  echo
  echo "===== Container logs ====="

  docker logs \
    "$CONTAINER_NAME" \
    2>&1 || true

  echo "=========================="
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
echo "1. Building concurrency-check image"
echo "========================================"

docker build \
  --tag "$IMAGE_NAME" \
  .

docker rm -f \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "2. Starting constrained container"
echo "========================================"
echo "Maximum concurrent verifications: ${MAX_CONCURRENT}"
echo "Queue timeout: ${QUEUE_TIMEOUT} seconds"

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:${HOST_PORT}:8000" \
  --cpus 2 \
  --memory 4g \
  --env VERIFIER_MODE=rule_only \
  --env "MAX_CONCURRENT_VERIFICATIONS=${MAX_CONCURRENT}" \
  --env "VERIFICATION_QUEUE_TIMEOUT_SECONDS=${QUEUE_TIMEOUT}" \
  "$IMAGE_NAME" \
  >/dev/null

ready="false"

for attempt in $(seq 1 180); do
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
echo "3. Generating concurrent overload"
echo "========================================"

export BASE_URL

python - <<'__CONCURRENCY_OVERLOAD_PY_EOF__'
import json
import os
import threading
import uuid
from collections import Counter
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prometheus_client.parser import (
    text_string_to_metric_families,
)


base_url = os.environ["BASE_URL"]
request_count = 12

start_barrier = threading.Barrier(
    request_count
)


def send_verification(index):
    request_id = uuid.uuid4().hex

    payload = json.dumps(
        {
            "claim": (
                "Retrieval augmented generation "
                "can improve factual reliability."
            ),
        }
    ).encode("utf-8")

    request = Request(
        base_url + "/verify",
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        },
    )

    start_barrier.wait(timeout=15.0)

    try:
        with urlopen(
            request,
            timeout=60.0,
        ) as response:
            body = json.loads(
                response.read().decode("utf-8")
            )

            return {
                "request_id": request_id,
                "status_code": response.status,
                "headers": {
                    key.lower(): value
                    for key, value
                    in response.headers.items()
                },
                "body": body,
            }

    except HTTPError as error:
        body = json.loads(
            error.read().decode("utf-8")
        )

        return {
            "request_id": request_id,
            "status_code": error.code,
            "headers": {
                key.lower(): value
                for key, value
                in error.headers.items()
            },
            "body": body,
        }


with ThreadPoolExecutor(
    max_workers=request_count
) as executor:
    futures = [
        executor.submit(
            send_verification,
            index,
        )
        for index in range(request_count)
    ]

    results = [
        future.result()
        for future in as_completed(futures)
    ]


status_counts = Counter(
    result["status_code"]
    for result in results
)

unexpected_statuses = set(
    status_counts
) - {
    200,
    429,
}

if unexpected_statuses:
    raise SystemExit(
        "Unexpected response statuses: {}".format(
            sorted(unexpected_statuses)
        )
    )

if status_counts[200] < 1:
    raise SystemExit(
        "No verification request completed successfully."
    )

if status_counts[429] < 1:
    raise SystemExit(
        "The constrained container did not reject "
        "any requests with HTTP 429."
    )

for result in results:
    body = result["body"]
    headers = result["headers"]

    if result["status_code"] == 200:
        if body.get("status") != "success":
            raise SystemExit(
                "HTTP 200 response did not use "
                "the success contract."
            )

        continue

    error = body.get("error", {})

    if error.get("type") != "service_overloaded":
        raise SystemExit(
            "HTTP 429 response used an unexpected "
            "error type."
        )

    if error.get("code") != "service_overloaded":
        raise SystemExit(
            "HTTP 429 response did not include "
            "the stable overload code."
        )

    if error.get("retryable") is not True:
        raise SystemExit(
            "HTTP 429 response was not marked retryable."
        )

    if (
        body.get("request_id")
        != result["request_id"]
    ):
        raise SystemExit(
            "HTTP 429 body request ID was inconsistent."
        )

    if (
        headers.get("x-request-id")
        != result["request_id"]
    ):
        raise SystemExit(
            "HTTP 429 header request ID was inconsistent."
        )

    if headers.get("retry-after") != "1":
        raise SystemExit(
            "HTTP 429 response did not include "
            "Retry-After: 1."
        )


def get_json(path):
    with urlopen(
        base_url + path,
        timeout=10.0,
    ) as response:
        return (
            response.status,
            json.loads(
                response.read().decode("utf-8")
            ),
        )


live_status, live_body = get_json("/live")
ready_status, ready_body = get_json("/ready")

if live_status != 200:
    raise SystemExit(
        "/live failed after overload."
    )

if ready_status != 200:
    raise SystemExit(
        "/ready failed after overload."
    )

if live_body.get("status") != "alive":
    raise SystemExit(
        "/live returned an unexpected body."
    )

if ready_body.get("status") != "ready":
    raise SystemExit(
        "/ready returned an unexpected body."
    )

with urlopen(
    base_url + "/metrics",
    timeout=10.0,
) as response:
    metrics_text = response.read().decode(
        "utf-8"
    )


metric_samples = []

for family in text_string_to_metric_families(
    metrics_text
):
    metric_samples.extend(
        family.samples
    )


def metric_value(name, labels=None):
    expected_labels = labels or {}

    for sample in metric_samples:
        if (
            sample.name == name
            and sample.labels == expected_labels
        ):
            return float(sample.value)

    return 0.0


rejected_total = metric_value(
    "evidence_verification_rejected_total"
)

in_flight = metric_value(
    "evidence_verification_in_flight"
)

queue_wait_count = metric_value(
    (
        "evidence_verification_"
        "queue_wait_seconds_count"
    )
)

overload_errors = metric_value(
    "evidence_verification_errors_total",
    {
        "error_type": "service_overloaded",
    },
)

if rejected_total < status_counts[429]:
    raise SystemExit(
        "Rejected-request metric did not include "
        "all HTTP 429 responses."
    )

if overload_errors < status_counts[429]:
    raise SystemExit(
        "Overload error metric did not include "
        "all HTTP 429 responses."
    )

if queue_wait_count < request_count:
    raise SystemExit(
        "Queue-wait histogram did not observe "
        "all verification attempts."
    )

if in_flight != 0.0:
    raise SystemExit(
        "In-flight gauge did not return to zero."
    )

print()
print("Concurrency overload results")
print("----------------------------")
print(
    "HTTP 200 responses: {}".format(
        status_counts[200]
    )
)
print(
    "HTTP 429 responses: {}".format(
        status_counts[429]
    )
)
print(
    "Rejected metric: {}".format(
        rejected_total
    )
)
print(
    "Overload error metric: {}".format(
        overload_errors
    )
)
print(
    "Queue wait observations: {}".format(
        queue_wait_count
    )
)
print(
    "In-flight after completion: {}".format(
        in_flight
    )
)
print("Liveness after overload: HTTP 200")
print("Readiness after overload: HTTP 200")
print()
print("Concurrency overload check passed")
__CONCURRENCY_OVERLOAD_PY_EOF__

echo
echo "========================================"
echo "Docker concurrency check completed"
echo "========================================"
