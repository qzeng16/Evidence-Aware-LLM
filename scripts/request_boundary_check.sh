#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="${REQUEST_BOUNDARY_IMAGE:-evidence-llm-api:request-boundary-check}"
CONTAINER_NAME="${REQUEST_BOUNDARY_CONTAINER:-evidence-llm-request-boundary-check}"

HOST_PORT="${REQUEST_BOUNDARY_PORT:-8012}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

MAX_REQUEST_BODY_BYTES="${MAX_REQUEST_BODY_BYTES:-256}"
MAX_CLAIM_LENGTH="${MAX_CLAIM_LENGTH:-100}"

PRIVATE_MEDIA_VALUE="layer91-private-media-sk-proj-secret"
PRIVATE_OVERSIZED_MARKER="layer91-private-oversized-hf_private_token"

TEMP_DIR="$(mktemp -d)"

cleanup() {
  docker rm -f \
    "$CONTAINER_NAME" \
    >/dev/null 2>&1 || true

  rm -rf "$TEMP_DIR"
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
echo "1. Building request-boundary image"
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
echo "Maximum request body: ${MAX_REQUEST_BODY_BYTES} bytes"
echo "Maximum claim length: ${MAX_CLAIM_LENGTH} characters"

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:${HOST_PORT}:8000" \
  --cpus 2 \
  --memory 4g \
  --env VERIFIER_MODE=rule_only \
  --env "MAX_REQUEST_BODY_BYTES=${MAX_REQUEST_BODY_BYTES}" \
  --env "MAX_CLAIM_LENGTH=${MAX_CLAIM_LENGTH}" \
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
echo "3. Exercising HTTP request boundaries"
echo "========================================"

export BASE_URL
export PRIVATE_MEDIA_VALUE
export PRIVATE_OVERSIZED_MARKER

python - <<'__REQUEST_BOUNDARY_VALIDATION_EOF__'
import http.client
import json
import os
from urllib.parse import urlsplit

from prometheus_client.parser import (
    text_string_to_metric_families,
)


base_url = os.environ["BASE_URL"]
parsed_url = urlsplit(base_url)

private_media_value = os.environ[
    "PRIVATE_MEDIA_VALUE"
]

private_oversized_marker = os.environ[
    "PRIVATE_OVERSIZED_MARKER"
]


def raw_request(
    method,
    path,
    *,
    body=None,
    headers=None,
):
    """Send one HTTP request with exact headers."""

    connection = http.client.HTTPConnection(
        parsed_url.hostname,
        parsed_url.port,
        timeout=60.0,
    )

    connection.request(
        method,
        path,
        body=body,
        headers=headers or {},
    )

    response = connection.getresponse()
    payload = response.read()

    result = {
        "status_code": response.status,
        "headers": {
            name.lower(): value
            for name, value
            in response.getheaders()
        },
        "raw_body": payload,
    }

    connection.close()

    return result


def json_request(
    method,
    path,
    *,
    body=None,
    headers=None,
):
    """Send a request and decode its JSON response."""

    result = raw_request(
        method,
        path,
        body=body,
        headers=headers,
    )

    try:
        result["body"] = json.loads(
            result["raw_body"].decode("utf-8")
        )
    except json.JSONDecodeError as error:
        raise SystemExit(
            "{} {} returned non-JSON content: {}".format(
                method,
                path,
                type(error).__name__,
            )
        )

    return result


def json_body(claim):
    return json.dumps(
        {
            "claim": claim,
        }
    ).encode("utf-8")


def expect_request_id(
    result,
    expected_request_id,
):
    body = result["body"]
    headers = result["headers"]

    if body.get("request_id") != expected_request_id:
        raise SystemExit(
            "Response body request ID was inconsistent."
        )

    if (
        headers.get("x-request-id")
        != expected_request_id
    ):
        raise SystemExit(
            "Response header request ID was inconsistent."
        )


def expect_error(
    result,
    *,
    status_code,
    error_type,
    request_id,
    code=None,
):
    if result["status_code"] != status_code:
        raise SystemExit(
            "Expected HTTP {} for {}, received HTTP {}."
            .format(
                status_code,
                error_type,
                result["status_code"],
            )
        )

    body = result["body"]
    error = body.get("error", {})

    if body.get("status") != "error":
        raise SystemExit(
            "{} did not use the error contract.".format(
                error_type
            )
        )

    if error.get("type") != error_type:
        raise SystemExit(
            "Expected error type {}, received {}."
            .format(
                error_type,
                error.get("type"),
            )
        )

    if code is not None and error.get("code") != code:
        raise SystemExit(
            "Expected error code {}, received {}."
            .format(
                code,
                error.get("code"),
            )
        )

    if error.get("retryable") is not False:
        raise SystemExit(
            "{} should not be retryable.".format(
                error_type
            )
        )

    expect_request_id(
        result,
        request_id,
    )


success_id = "layer91-success-001"

success = json_request(
    "POST",
    "/verify",
    body=json_body(
        (
            "Retrieval augmented generation can "
            "improve factual reliability."
        )
    ),
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": success_id,
    },
)

if success["status_code"] != 200:
    raise SystemExit(
        "Valid JSON request did not return HTTP 200."
    )

if success["body"].get("status") != "success":
    raise SystemExit(
        "Valid request did not use the success contract."
    )

expect_request_id(
    success,
    success_id,
)


empty_id = "layer91-empty-claim-001"

empty_claim = json_request(
    "POST",
    "/verify",
    body=json_body("   "),
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": empty_id,
    },
)

expect_error(
    empty_claim,
    status_code=400,
    error_type="invalid_claim",
    request_id=empty_id,
)


long_id = "layer91-long-claim-001"

long_claim = json_request(
    "POST",
    "/verify",
    body=json_body("x" * 101),
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": long_id,
    },
)

expect_error(
    long_claim,
    status_code=400,
    error_type="invalid_claim",
    request_id=long_id,
    code="claim_too_long",
)


media_id = "layer91-media-type-001"

unsupported_media = json_request(
    "POST",
    "/verify",
    body=private_media_value.encode("utf-8"),
    headers={
        "Content-Type": "text/plain",
        "X-Request-ID": media_id,
    },
)

expect_error(
    unsupported_media,
    status_code=415,
    error_type="unsupported_media_type",
    request_id=media_id,
    code="unsupported_media_type",
)


missing_type_id = "layer91-missing-type-001"

missing_content_type = json_request(
    "POST",
    "/verify",
    body=json_body("A valid claim."),
    headers={
        "X-Request-ID": missing_type_id,
    },
)

expect_error(
    missing_content_type,
    status_code=415,
    error_type="unsupported_media_type",
    request_id=missing_type_id,
    code="unsupported_media_type",
)


oversized_id = "layer91-oversized-001"

oversized_claim = (
    private_oversized_marker
    + "-"
    + ("z" * 500)
)

oversized = json_request(
    "POST",
    "/verify",
    body=json_body(oversized_claim),
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": oversized_id,
    },
)

expect_error(
    oversized,
    status_code=413,
    error_type="payload_too_large",
    request_id=oversized_id,
    code="payload_too_large",
)


malformed_id = "layer91-malformed-json-001"

malformed = json_request(
    "POST",
    "/verify",
    body=b'{"claim": ',
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": malformed_id,
    },
)

expect_error(
    malformed,
    status_code=422,
    error_type="invalid_request",
    request_id=malformed_id,
)


for secret in (
    private_media_value,
    private_oversized_marker,
    "sk-proj-secret",
    "hf_private_token",
):
    for result in (
        unsupported_media,
        oversized,
    ):
        response_text = result[
            "raw_body"
        ].decode(
            "utf-8",
            errors="replace",
        )

        if secret in response_text:
            raise SystemExit(
                "A private request value entered "
                "an error response."
            )


live = json_request(
    "GET",
    "/live",
)

ready = json_request(
    "GET",
    "/ready",
)

if live["status_code"] != 200:
    raise SystemExit(
        "/live failed after boundary errors."
    )

if ready["status_code"] != 200:
    raise SystemExit(
        "/ready failed after boundary errors."
    )


metrics_response = raw_request(
    "GET",
    "/metrics",
)

if metrics_response["status_code"] != 200:
    raise SystemExit(
        "/metrics did not return HTTP 200."
    )

metrics_text = metrics_response[
    "raw_body"
].decode("utf-8")

metric_samples = []

for family in text_string_to_metric_families(
    metrics_text
):
    metric_samples.extend(
        family.samples
    )


def metric_value(
    name,
    labels=None,
):
    expected_labels = labels or {}

    for sample in metric_samples:
        if (
            sample.name == name
            and sample.labels == expected_labels
        ):
            return float(sample.value)

    return 0.0


expected_error_minimums = {
    "invalid_claim": 2.0,
    "invalid_request": 1.0,
    "payload_too_large": 1.0,
    "unsupported_media_type": 2.0,
}

for error_type, minimum in (
    expected_error_minimums.items()
):
    value = metric_value(
        "evidence_verification_errors_total",
        {
            "error_type": error_type,
        },
    )

    if value < minimum:
        raise SystemExit(
            "Metric for {} was {}, expected at "
            "least {}.".format(
                error_type,
                value,
                minimum,
            )
        )


expected_http_minimums = {
    "200": 1.0,
    "400": 2.0,
    "413": 1.0,
    "415": 2.0,
    "422": 1.0,
}

for status_code, minimum in (
    expected_http_minimums.items()
):
    value = metric_value(
        "evidence_http_requests_total",
        {
            "method": "POST",
            "path": "/verify",
            "status_code": status_code,
        },
    )

    if value < minimum:
        raise SystemExit(
            "HTTP metric for status {} was {}, "
            "expected at least {}.".format(
                status_code,
                value,
                minimum,
            )
        )


print()
print("Request boundary results")
print("------------------------")
print("Valid JSON request: HTTP 200")
print("Whitespace claim: HTTP 400")
print("Long claim: HTTP 400 claim_too_long")
print("Oversized body: HTTP 413")
print("Unsupported media type: HTTP 415")
print("Missing Content-Type: HTTP 415")
print("Malformed JSON: HTTP 422")
print("Liveness after errors: HTTP 200")
print("Readiness after errors: HTTP 200")
print("Boundary error metrics: verified")
print("HTTP status metrics: verified")
__REQUEST_BOUNDARY_VALIDATION_EOF__

sleep 1

docker logs \
  "$CONTAINER_NAME" \
  > "${TEMP_DIR}/container.log" \
  2>&1

for private_value in \
  "$PRIVATE_MEDIA_VALUE" \
  "$PRIVATE_OVERSIZED_MARKER" \
  "sk-proj-secret" \
  "hf_private_token"
do
  if grep \
    --fixed-strings \
    --quiet \
    "$private_value" \
    "${TEMP_DIR}/container.log"
  then
    echo \
      "Private request content appeared in container logs." \
      >&2

    exit 1
  fi
done

echo "Private request values absent from logs"
echo
echo "Request boundary check passed"

echo
echo "========================================"
echo "Docker request-boundary check completed"
echo "========================================"
