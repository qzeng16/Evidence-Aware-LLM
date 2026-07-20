#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="evidence-aware-llm:layer-7-3-check"

RULE_CONTAINER="evidence-aware-llm-layer-7-3-rule"
UNREADY_CONTAINER="evidence-aware-llm-layer-7-3-unready"

RULE_PORT="${RULE_PORT:-8006}"
UNREADY_PORT="${UNREADY_PORT:-8007}"

RULE_URL="http://127.0.0.1:${RULE_PORT}"
UNREADY_URL="http://127.0.0.1:${UNREADY_PORT}"

TEMP_DIR="$(mktemp -d)"

cleanup() {
  docker rm -f \
    "$RULE_CONTAINER" \
    "$UNREADY_CONTAINER" \
    >/dev/null 2>&1 || true

  rm -rf "$TEMP_DIR"
}

show_logs() {
  local container_name="$1"

  echo
  echo "===== ${container_name} logs ====="

  docker logs \
    "$container_name" \
    2>&1 || true

  echo "=================================="
}

wait_for_http_status() {
  local base_url="$1"
  local path="$2"
  local expected_status="$3"
  local container_name="$4"

  for attempt in $(seq 1 120); do
    local status

    status="$(
      curl \
        --silent \
        --output /dev/null \
        --write-out "%{http_code}" \
        --max-time 5 \
        "${base_url}${path}" \
        2>/dev/null \
        || true
    )"

    if [[ "$status" == "$expected_status" ]]; then
      return 0
    fi

    if ! docker ps \
      --format '{{.Names}}' \
      | grep -qx "$container_name"; then
      echo "Container stopped before ${path} became available."
      show_logs "$container_name"
      return 1
    fi

    sleep 2
  done

  echo "${base_url}${path} did not return HTTP ${expected_status}."
  show_logs "$container_name"

  return 1
}

wait_for_docker_health() {
  local container_name="$1"

  for attempt in $(seq 1 120); do
    local health_status

    health_status="$(
      docker inspect \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
        "$container_name" \
        2>/dev/null \
        || true
    )"

    if [[ "$health_status" == "healthy" ]]; then
      return 0
    fi

    if [[ "$health_status" == "unhealthy" ]]; then
      echo "Docker marked ${container_name} unhealthy."
      show_logs "$container_name"
      return 1
    fi

    sleep 2
  done

  echo "Docker health timed out: ${container_name}"
  show_logs "$container_name"

  return 1
}

request() {
  local prefix="$1"
  shift

  curl \
    --silent \
    --show-error \
    --max-time 60 \
    --dump-header "${TEMP_DIR}/${prefix}.headers" \
    --output "${TEMP_DIR}/${prefix}.json" \
    --write-out "%{http_code}" \
    "$@" \
    > "${TEMP_DIR}/${prefix}.status"
}

trap cleanup EXIT

echo
echo "========================================"
echo "1. Building Docker image"
echo "========================================"

docker build \
  --tag "$IMAGE_NAME" \
  .

docker rm -f \
  "$RULE_CONTAINER" \
  "$UNREADY_CONTAINER" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "2. Starting ready rule-only service"
echo "========================================"

docker run \
  --detach \
  --name "$RULE_CONTAINER" \
  --publish "${RULE_PORT}:8000" \
  --env VERIFIER_MODE=rule_only \
  "$IMAGE_NAME" \
  >/dev/null

wait_for_http_status \
  "$RULE_URL" \
  "/live" \
  "200" \
  "$RULE_CONTAINER"

wait_for_http_status \
  "$RULE_URL" \
  "/ready" \
  "200" \
  "$RULE_CONTAINER"

wait_for_docker_health \
  "$RULE_CONTAINER"

echo
echo "========================================"
echo "3. Generating ready-service traffic"
echo "========================================"

request \
  "success" \
  --request POST \
  --header "Content-Type: application/json" \
  --header "X-Request-ID: layer73-success-001" \
  --data '{
    "claim": "Retrieval augmented generation can improve factual reliability."
  }' \
  "${RULE_URL}/verify"

request \
  "invalid_claim" \
  --request POST \
  --header "Content-Type: application/json" \
  --header "X-Request-ID: layer73-invalid-claim-001" \
  --data '{
    "claim": "   "
  }' \
  "${RULE_URL}/verify"

PRIVATE_VALUE="sk-proj-private-layer73-hf_private_token"

request \
  "invalid_request" \
  --request POST \
  --header "Content-Type: application/json" \
  --data "{
    \"claim\": {
      \"secret\": \"${PRIVATE_VALUE}\"
    }
  }" \
  "${RULE_URL}/verify"

request \
  "not_found" \
  --request GET \
  "${RULE_URL}/does-not-exist"

request \
  "method_not_allowed" \
  --request POST \
  "${RULE_URL}/health"

curl \
  --fail \
  --silent \
  --show-error \
  --dump-header "${TEMP_DIR}/rule_metrics.headers" \
  "${RULE_URL}/metrics" \
  > "${TEMP_DIR}/rule_metrics.txt"

sleep 1

docker logs \
  "$RULE_CONTAINER" \
  > "${TEMP_DIR}/rule_container.log" \
  2>&1

docker rm -f \
  "$RULE_CONTAINER" \
  >/dev/null

echo
echo "========================================"
echo "4. Starting intentionally unready service"
echo "========================================"

docker run \
  --detach \
  --name "$UNREADY_CONTAINER" \
  --publish "${UNREADY_PORT}:8000" \
  --env VERIFIER_MODE=llm_only \
  "$IMAGE_NAME" \
  >/dev/null

wait_for_http_status \
  "$UNREADY_URL" \
  "/live" \
  "200" \
  "$UNREADY_CONTAINER"

wait_for_docker_health \
  "$UNREADY_CONTAINER"

request \
  "readiness_unavailable" \
  --request GET \
  "${UNREADY_URL}/ready"

request \
  "service_unavailable" \
  --request POST \
  --header "Content-Type: application/json" \
  --header "X-Request-ID: layer73-unavailable-001" \
  --data '{
    "claim": "A valid claim that must not call OpenAI."
  }' \
  "${UNREADY_URL}/verify"

curl \
  --fail \
  --silent \
  --show-error \
  --dump-header "${TEMP_DIR}/unready_metrics.headers" \
  "${UNREADY_URL}/metrics" \
  > "${TEMP_DIR}/unready_metrics.txt"

sleep 1

docker logs \
  "$UNREADY_CONTAINER" \
  > "${TEMP_DIR}/unready_container.log" \
  2>&1

echo
echo "========================================"
echo "5. Validating responses, metrics and logs"
echo "========================================"

python - "$TEMP_DIR" "$PRIVATE_VALUE" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from prometheus_client.parser import (
    text_string_to_metric_families,
)


temp_dir = Path(sys.argv[1])
private_value = sys.argv[2]

generated_id_pattern = re.compile(
    r"^[a-f0-9]{32}$"
)


def read_status(prefix: str) -> int:
    return int(
        (
            temp_dir
            / f"{prefix}.status"
        ).read_text(
            encoding="utf-8"
        ).strip()
    )


def read_json(prefix: str) -> dict[str, Any]:
    return json.loads(
        (
            temp_dir
            / f"{prefix}.json"
        ).read_text(
            encoding="utf-8"
        )
    )


def read_headers(prefix: str) -> dict[str, str]:
    headers: dict[str, str] = {}

    for line in (
        temp_dir
        / f"{prefix}.headers"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        if ":" not in line:
            continue

        name, value = line.split(":", 1)

        headers[
            name.strip().lower()
        ] = value.strip()

    return headers


def validate_request_id(
    prefix: str,
    body: dict[str, Any],
    expected: Optional[str] = None,
) -> str:
    header_id = read_headers(
        prefix
    ).get("x-request-id")

    body_id = body.get("request_id")

    if not isinstance(header_id, str):
        raise SystemExit(
            f"{prefix}: missing X-Request-ID header."
        )

    if body_id != header_id:
        raise SystemExit(
            f"{prefix}: response body and header "
            "request IDs do not match."
        )

    if expected is not None:
        if header_id != expected:
            raise SystemExit(
                f"{prefix}: expected request ID "
                f"{expected!r}, got {header_id!r}."
            )
    elif not generated_id_pattern.fullmatch(
        header_id
    ):
        raise SystemExit(
            f"{prefix}: invalid generated request ID "
            f"{header_id!r}."
        )

    return header_id


def validate_error(
    prefix: str,
    *,
    expected_status: int,
    expected_type: str,
    expected_retryable: bool,
    expected_request_id: Optional[str] = None,
) -> dict[str, Any]:
    actual_status = read_status(prefix)
    body = read_json(prefix)

    if actual_status != expected_status:
        raise SystemExit(
            f"{prefix}: expected HTTP "
            f"{expected_status}, got {actual_status}."
        )

    if body.get("status") != "error":
        raise SystemExit(
            f"{prefix}: status is not error."
        )

    if body.get("data") is not None:
        raise SystemExit(
            f"{prefix}: error data must be null."
        )

    if not isinstance(
        body.get("timestamp"),
        str,
    ):
        raise SystemExit(
            f"{prefix}: timestamp is missing."
        )

    if not isinstance(
        body.get("metadata"),
        dict,
    ):
        raise SystemExit(
            f"{prefix}: metadata is missing."
        )

    error = body.get("error")

    if not isinstance(error, dict):
        raise SystemExit(
            f"{prefix}: error object is missing."
        )

    if error.get("type") != expected_type:
        raise SystemExit(
            f"{prefix}: expected error type "
            f"{expected_type!r}, got "
            f"{error.get('type')!r}."
        )

    if (
        error.get("retryable")
        is not expected_retryable
    ):
        raise SystemExit(
            f"{prefix}: incorrect retryable value."
        )

    if not isinstance(
        error.get("message"),
        str,
    ):
        raise SystemExit(
            f"{prefix}: safe error message is missing."
        )

    validate_request_id(
        prefix,
        body,
        expected_request_id,
    )

    return body


def parse_metrics(path: Path) -> dict:
    samples = {}

    text = path.read_text(
        encoding="utf-8"
    )

    for family in (
        text_string_to_metric_families(
            text
        )
    ):
        for sample in family.samples:
            key = (
                sample.name,
                tuple(
                    sorted(
                        sample.labels.items()
                    )
                ),
            )

            samples[key] = float(
                sample.value
            )

    return samples


def metric_value(
    samples: dict,
    name: str,
    **labels: str,
) -> float:
    return samples.get(
        (
            name,
            tuple(
                sorted(
                    labels.items()
                )
            ),
        ),
        0.0,
    )


success_status = read_status(
    "success"
)

success = read_json(
    "success"
)

if success_status != 200:
    raise SystemExit(
        "Successful verification did not return 200."
    )

if success.get("status") != "success":
    raise SystemExit(
        "Successful verification response is invalid."
    )

validate_request_id(
    "success",
    success,
    "layer73-success-001",
)

verification = (
    success.get("data", {})
    .get("verification")
)

if not isinstance(
    verification,
    dict,
):
    raise SystemExit(
        "Successful verification result is missing."
    )

if verification.get("label") not in {
    "Supported",
    "Refuted",
    "Uncertain",
}:
    raise SystemExit(
        "Successful verification label is invalid."
    )

validate_error(
    "invalid_claim",
    expected_status=400,
    expected_type="invalid_claim",
    expected_retryable=False,
    expected_request_id=(
        "layer73-invalid-claim-001"
    ),
)

validate_error(
    "invalid_request",
    expected_status=422,
    expected_type="invalid_request",
    expected_retryable=False,
)

validate_error(
    "not_found",
    expected_status=404,
    expected_type="not_found",
    expected_retryable=False,
)

validate_error(
    "method_not_allowed",
    expected_status=405,
    expected_type="method_not_allowed",
    expected_retryable=False,
)

validate_error(
    "readiness_unavailable",
    expected_status=503,
    expected_type="service_unavailable",
    expected_retryable=True,
)

validate_error(
    "service_unavailable",
    expected_status=503,
    expected_type="service_unavailable",
    expected_retryable=True,
    expected_request_id=(
        "layer73-unavailable-001"
    ),
)

all_public_output = "\n".join(
    path.read_text(
        encoding="utf-8",
        errors="replace",
    )
    for path in temp_dir.glob("*.json")
)

all_logs = (
    temp_dir
    / "rule_container.log"
).read_text(
    encoding="utf-8",
    errors="replace",
) + (
    temp_dir
    / "unready_container.log"
).read_text(
    encoding="utf-8",
    errors="replace",
)

for source_name, source in (
    ("responses", all_public_output),
    ("container logs", all_logs),
):
    if private_value in source:
        raise SystemExit(
            f"Sensitive submitted value appeared "
            f"in {source_name}."
        )

rule_metrics_text = (
    temp_dir
    / "rule_metrics.txt"
).read_text(
    encoding="utf-8"
)

unready_metrics_text = (
    temp_dir
    / "unready_metrics.txt"
).read_text(
    encoding="utf-8"
)

for source_name, source in (
    ("rule metrics", rule_metrics_text),
    (
        "unready metrics",
        unready_metrics_text,
    ),
):
    if private_value in source:
        raise SystemExit(
            f"Sensitive submitted value appeared "
            f"in {source_name}."
        )

rule_metrics = parse_metrics(
    temp_dir / "rule_metrics.txt"
)

unready_metrics = parse_metrics(
    temp_dir / "unready_metrics.txt"
)

expected_rule_metrics = (
    (
        "evidence_verification_requests_total",
        1.0,
        {
            "outcome": "success",
        },
    ),
    (
        "evidence_verification_requests_total",
        2.0,
        {
            "outcome": "error",
        },
    ),
    (
        "evidence_verification_errors_total",
        1.0,
        {
            "error_type": "invalid_claim",
        },
    ),
    (
        "evidence_verification_errors_total",
        1.0,
        {
            "error_type": "invalid_request",
        },
    ),
)

for name, expected, labels in (
    expected_rule_metrics
):
    actual = metric_value(
        rule_metrics,
        name,
        **labels,
    )

    if actual != expected:
        raise SystemExit(
            f"{name}{labels}: expected "
            f"{expected}, got {actual}."
        )

expected_unready_metrics = (
    (
        "evidence_verification_requests_total",
        1.0,
        {
            "outcome": "error",
        },
    ),
    (
        "evidence_verification_errors_total",
        1.0,
        {
            "error_type": (
                "service_unavailable"
            ),
        },
    ),
)

for name, expected, labels in (
    expected_unready_metrics
):
    actual = metric_value(
        unready_metrics,
        name,
        **labels,
    )

    if actual != expected:
        raise SystemExit(
            f"{name}{labels}: expected "
            f"{expected}, got {actual}."
        )

summary = {
    "success": 200,
    "invalid_claim": 400,
    "invalid_request": 422,
    "not_found": 404,
    "method_not_allowed": 405,
    "readiness_unavailable": 503,
    "service_unavailable": 503,
    "docker_health_uses_liveness": True,
    "request_ids_consistent": True,
    "error_metrics_recorded": True,
    "submitted_private_value_exposed": False,
}

print(
    json.dumps(
        summary,
        indent=2,
        ensure_ascii=False,
    )
)
PY

echo
echo "========================================"
echo "Layer 7.3 Docker error-contract check passed"
echo "========================================"
echo
echo "Verified:"
echo "- successful verification remains HTTP 200"
echo "- invalid claims return HTTP 400"
echo "- malformed requests return HTTP 422"
echo "- unknown paths return HTTP 404"
echo "- unsupported methods return HTTP 405"
echo "- unavailable services return HTTP 503"
echo "- response body and header Request IDs match"
echo "- error metrics use stable low-cardinality labels"
echo "- submitted private values do not enter responses, metrics or logs"
