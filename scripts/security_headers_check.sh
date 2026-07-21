#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="${SECURITY_HEADERS_IMAGE:-evidence-llm-api:security-headers-check}"
CONTAINER_NAME="${SECURITY_HEADERS_CONTAINER:-evidence-llm-security-headers-check}"

HOST_PORT="${SECURITY_HEADERS_PORT:-8014}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

TEMP_DIR="$(mktemp -d)"

cleanup() {
  docker rm -f \
    "$CONTAINER_NAME" \
    >/dev/null 2>&1 || true

  rm -rf "$TEMP_DIR"
}

show_logs() {
  echo
  echo "===== Security-header container logs ====="

  docker logs \
    "$CONTAINER_NAME" \
    2>&1 || true

  echo "=========================================="
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
echo "1. Building security-header image"
echo "========================================"

docker build \
  --tag "$IMAGE_NAME" \
  .

docker rm -f \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "2. Starting production application"
echo "========================================"

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:${HOST_PORT}:8000" \
  --cpus 2 \
  --memory 4g \
  --env VERIFIER_MODE=rule_only \
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
echo "3. Validating real HTTP security headers"
echo "========================================"

export BASE_URL

python - <<'__SECURITY_HEADERS_HTTP_EOF__'
import json
import os
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen


base_url = os.environ["BASE_URL"]

expected_common_headers = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": (
        "camera=(), microphone=(), "
        "geolocation=(), payment=(), usb=()"
    ),
}


def request(
    path,
    *,
    method="GET",
    body=None,
    headers=None,
):
    """Send one request and preserve HTTP error responses."""

    outbound_headers = dict(
        headers or {}
    )

    payload = body

    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    outbound = Request(
        base_url + path,
        data=payload,
        method=method,
        headers=outbound_headers,
    )

    try:
        response = urlopen(
            outbound,
            timeout=60,
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
        "text": raw_body.decode(
            "utf-8",
            errors="replace",
        ),
    }

    response.close()

    return result


def assert_common_headers(
    result,
    description,
):
    """Validate headers required on every response."""

    for header_name, expected_value in (
        expected_common_headers.items()
    ):
        actual_value = result[
            "headers"
        ].get(
            header_name
        )

        if actual_value != expected_value:
            raise SystemExit(
                "{}: {} expected {!r}, received {!r}."
                .format(
                    description,
                    header_name,
                    expected_value,
                    actual_value,
                )
            )


def assert_no_store(
    result,
    description,
):
    actual_value = result[
        "headers"
    ].get(
        "cache-control"
    )

    if actual_value != "no-store":
        raise SystemExit(
            "{} did not use Cache-Control: no-store."
            .format(
                description
            )
        )


def decode_json(
    result,
    description,
):
    try:
        return json.loads(
            result["text"]
        )
    except json.JSONDecodeError as error:
        raise SystemExit(
            "{} did not return JSON: {}."
            .format(
                description,
                type(error).__name__,
            )
        )


demo = request(
    "/",
    headers={
        "Accept": "text/html",
    },
)

if demo["status_code"] != 200:
    raise SystemExit(
        "Browser Demo did not return HTTP 200."
    )

assert_common_headers(
    demo,
    "Browser Demo",
)

assert_no_store(
    demo,
    "Browser Demo",
)

csp = demo["headers"].get(
    "content-security-policy",
    "",
)

required_csp_fragments = (
    "default-src 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "connect-src 'self'",
)

for fragment in required_csp_fragments:
    if fragment not in csp:
        raise SystemExit(
            "Demo CSP is missing: {}".format(
                fragment
            )
        )

if "'unsafe-inline'" in csp:
    raise SystemExit(
        "Demo CSP contains unsafe-inline."
    )

if "<style>" in demo["text"]:
    raise SystemExit(
        "Demo HTML still contains inline CSS."
    )

if re.search(
    r"<script(?![^>]*\bsrc=)",
    demo["text"],
    flags=re.IGNORECASE,
):
    raise SystemExit(
        "Demo HTML still contains inline JavaScript."
    )

if (
    'href="/assets/demo.css"'
    not in demo["text"]
):
    raise SystemExit(
        "Demo stylesheet reference is missing."
    )

if (
    'src="/assets/demo.js"'
    not in demo["text"]
):
    raise SystemExit(
        "Demo JavaScript reference is missing."
    )


stylesheet = request(
    "/assets/demo.css"
)

javascript = request(
    "/assets/demo.js"
)

for result, description in (
    (
        stylesheet,
        "Demo stylesheet",
    ),
    (
        javascript,
        "Demo JavaScript",
    ),
):
    if result["status_code"] != 200:
        raise SystemExit(
            "{} did not return HTTP 200."
            .format(
                description
            )
        )

    assert_common_headers(
        result,
        description,
    )

    if (
        result["headers"].get(
            "cache-control"
        )
        != "public, max-age=3600"
    ):
        raise SystemExit(
            "{} did not use the static cache policy."
            .format(
                description
            )
        )

    if (
        "content-security-policy"
        in result["headers"]
    ):
        raise SystemExit(
            "{} unexpectedly received the Demo CSP."
            .format(
                description
            )
        )

if ":root" not in stylesheet["text"]:
    raise SystemExit(
        "Demo stylesheet content is incomplete."
    )

for fragment in (
    'requestJson("/health"',
    'requestJson("/verify"',
):
    if fragment not in javascript["text"]:
        raise SystemExit(
            "Demo JavaScript is missing {}."
            .format(
                fragment
            )
        )


root_json = request(
    "/",
    headers={
        "Accept": "application/json",
    },
)

if root_json["status_code"] != 200:
    raise SystemExit(
        "JSON root did not return HTTP 200."
    )

assert_common_headers(
    root_json,
    "JSON root",
)

assert_no_store(
    root_json,
    "JSON root",
)

if (
    "content-security-policy"
    in root_json["headers"]
):
    raise SystemExit(
        "JSON root unexpectedly received Demo CSP."
    )


docs = request(
    "/docs"
)

if docs["status_code"] != 200:
    raise SystemExit(
        "/docs did not return HTTP 200."
    )

assert_common_headers(
    docs,
    "/docs",
)

assert_no_store(
    docs,
    "/docs",
)

if (
    "content-security-policy"
    in docs["headers"]
):
    raise SystemExit(
        "/docs unexpectedly received Demo CSP."
    )

if "Swagger UI" not in docs["text"]:
    raise SystemExit(
        "/docs content is incomplete."
    )


verify_request_id = (
    "layer93-success-001"
)

verify = request(
    "/verify",
    method="POST",
    body=json.dumps(
        {
            "claim": (
                "Retrieval augmented generation "
                "can improve factual reliability."
            ),
        }
    ),
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": verify_request_id,
    },
)

if verify["status_code"] != 200:
    raise SystemExit(
        "/verify did not return HTTP 200."
    )

assert_common_headers(
    verify,
    "/verify success",
)

assert_no_store(
    verify,
    "/verify success",
)

verify_body = decode_json(
    verify,
    "/verify success",
)

if verify_body.get("status") != "success":
    raise SystemExit(
        "/verify did not use the success contract."
    )


metrics = request(
    "/metrics"
)

if metrics["status_code"] != 200:
    raise SystemExit(
        "/metrics did not return HTTP 200."
    )

assert_common_headers(
    metrics,
    "/metrics",
)

assert_no_store(
    metrics,
    "/metrics",
)

if (
    "evidence_http_requests_total"
    not in metrics["text"]
):
    raise SystemExit(
        "/metrics payload is incomplete."
    )


not_found = request(
    "/does-not-exist",
    headers={
        "X-Request-ID": (
            "layer93-not-found-001"
        ),
    },
)

unsupported = request(
    "/verify",
    method="POST",
    body=(
        "layer93-private-"
        "sk-proj-security-header-secret"
    ),
    headers={
        "Content-Type": "text/plain",
        "X-Request-ID": (
            "layer93-unsupported-001"
        ),
    },
)

malformed = request(
    "/verify",
    method="POST",
    body='{"claim": ',
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": (
            "layer93-malformed-001"
        ),
    },
)

error_cases = (
    (
        not_found,
        404,
        "not_found",
        "404 response",
    ),
    (
        unsupported,
        415,
        "unsupported_media_type",
        "415 response",
    ),
    (
        malformed,
        422,
        "invalid_request",
        "422 response",
    ),
)

for (
    result,
    expected_status,
    expected_error_type,
    description,
) in error_cases:
    if result["status_code"] != expected_status:
        raise SystemExit(
            "{} expected HTTP {}, received HTTP {}."
            .format(
                description,
                expected_status,
                result["status_code"],
            )
        )

    assert_common_headers(
        result,
        description,
    )

    assert_no_store(
        result,
        description,
    )

    if (
        "content-security-policy"
        in result["headers"]
    ):
        raise SystemExit(
            "{} unexpectedly received Demo CSP."
            .format(
                description
            )
        )

    body = decode_json(
        result,
        description,
    )

    if (
        body.get(
            "error",
            {},
        ).get(
            "type"
        )
        != expected_error_type
    ):
        raise SystemExit(
            "{} used an unexpected error contract."
            .format(
                description
            )
        )


private_value = (
    "layer93-private-"
    "sk-proj-security-header-secret"
)

if private_value in unsupported["text"]:
    raise SystemExit(
        "Private request content entered "
        "the HTTP 415 response."
    )


print()
print("Security-header results")
print("-----------------------")
print("Browser Demo: HTTP 200 with strict CSP")
print("CSP unsafe-inline: absent")
print("Inline CSS and JavaScript: absent")
print("Demo stylesheet: HTTP 200 with static cache")
print("Demo JavaScript: HTTP 200 with static cache")
print("JSON root: HTTP 200 with no-store")
print("/docs: HTTP 200 without Demo CSP")
print("/verify: HTTP 200 with security headers")
print("/metrics: HTTP 200 with no-store")
print("HTTP 404: security headers verified")
print("HTTP 415: security headers verified")
print("HTTP 422: security headers verified")
__SECURITY_HEADERS_HTTP_EOF__

sleep 1

docker logs \
  "$CONTAINER_NAME" \
  > "${TEMP_DIR}/container.log" \
  2>&1

if grep \
  --fixed-strings \
  --quiet \
  "sk-proj-security-header-secret" \
  "${TEMP_DIR}/container.log"
then
  echo \
    "Private request content appeared in logs." \
    >&2

  exit 1
fi

echo "Private request content absent from logs"

echo
echo "Security-header check passed"

echo
echo "========================================"
echo "Docker security-header check completed"
echo "========================================"
