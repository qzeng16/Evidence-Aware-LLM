#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

CLAIM="${1:-Retrieval augmented generation can improve factual reliability.}"

HEALTH_FILE="$(mktemp)"
PAYLOAD_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"

cleanup() {
  rm -f \
    "$HEALTH_FILE" \
    "$PAYLOAD_FILE" \
    "$RESPONSE_FILE"
}

trap cleanup EXIT

echo "Checking ${BASE_URL}/health ..."

curl \
  --fail \
  --silent \
  --show-error \
  --max-time 30 \
  "${BASE_URL}/health" \
  > "$HEALTH_FILE"

python3 - "$HEALTH_FILE" <<'PY'
import json
import sys
from pathlib import Path


path = Path(sys.argv[1])
status = json.loads(
    path.read_text(encoding="utf-8")
)

expected_values = {
    "status": "ready",
    "verifier_mode": "llm_only",
    "active_verifier_mode": "llm",
    "llm_verifier_available": True,
    "llm_provider": "openai",
    "openai_api_key_configured": True,
}

errors = []

for field_name, expected_value in (
    expected_values.items()
):
    actual_value = status.get(field_name)

    if actual_value != expected_value:
        errors.append(
            f"{field_name}: expected "
            f"{expected_value!r}, got "
            f"{actual_value!r}"
        )

serialized_status = json.dumps(status)

for forbidden_value in (
    "OPENAI_API_KEY",
    "sk-proj-",
    "sk-",
):
    if forbidden_value in serialized_status:
        errors.append(
            "Health response exposed a "
            f"forbidden credential pattern: "
            f"{forbidden_value}"
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
        "Health check failed:\n- "
        + "\n- ".join(errors)
    )

print(
    json.dumps(
        {
            "health": "passed",
            "verifier_mode": status[
                "verifier_mode"
            ],
            "active_verifier_mode": status[
                "active_verifier_mode"
            ],
            "provider": status[
                "llm_provider"
            ],
            "model": status[
                "llm_model"
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
)
PY

CLAIM="$CLAIM" python3 <<'PY' > "$PAYLOAD_FILE"
import json
import os


print(
    json.dumps(
        {
            "claim": os.environ["CLAIM"],
        }
    )
)
PY

echo
echo "Sending one real verification request ..."

curl \
  --fail \
  --silent \
  --show-error \
  --max-time 90 \
  -X POST \
  "${BASE_URL}/verify" \
  -H "Content-Type: application/json" \
  --data-binary "@${PAYLOAD_FILE}" \
  > "$RESPONSE_FILE"

python3 - "$RESPONSE_FILE" <<'PY'
import json
import sys
from pathlib import Path


path = Path(sys.argv[1])
response = json.loads(
    path.read_text(encoding="utf-8")
)

if response.get("status") != "success":
    print(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
        )
    )

    raise SystemExit(
        "Verification request did not succeed."
    )

data = response.get("data", {})
metadata = response.get("metadata", {})
verification = data.get("verification", {})
evidence_items = data.get("evidence", [])

if verification.get("verifier_type") != "llm":
    raise SystemExit(
        "Expected verifier_type='llm', got "
        f"{verification.get('verifier_type')!r}."
    )

if metadata.get(
    "active_verifier_mode"
) != "llm":
    raise SystemExit(
        "API metadata does not report an "
        "active LLM verifier."
    )

if metadata.get("llm_provider") != "openai":
    raise SystemExit(
        "API metadata does not report "
        "provider='openai'."
    )

matched_ids = set(
    verification.get(
        "matched_evidence_ids",
        [],
    )
)

returned_ids = {
    str(
        item.get(
            "evidence_id",
            item.get("id", ""),
        )
    ).strip()
    for item in evidence_items
    if isinstance(item, dict)
}

unknown_ids = matched_ids - returned_ids

if unknown_ids:
    raise SystemExit(
        "Verification cited evidence IDs that "
        "were not returned by the API: "
        f"{sorted(unknown_ids)}"
    )

serialized_response = json.dumps(response)

for forbidden_value in (
    "OPENAI_API_KEY",
    "sk-proj-",
    "sk-",
):
    if forbidden_value in serialized_response:
        raise SystemExit(
            "API response exposed a forbidden "
            f"credential pattern: {forbidden_value}"
        )

safe_summary = {
    "smoke_test": "passed",
    "claim": data.get("claim"),
    "label": verification.get("label"),
    "confidence": verification.get(
        "confidence"
    ),
    "reason": verification.get("reason"),
    "verifier_type": verification.get(
        "verifier_type"
    ),
    "matched_evidence_ids": sorted(
        matched_ids
    ),
    "returned_evidence_ids": sorted(
        returned_ids
    ),
    "provider": metadata.get(
        "llm_provider"
    ),
    "model": metadata.get("llm_model"),
}

print(
    json.dumps(
        safe_summary,
        indent=2,
        ensure_ascii=False,
    )
)
PY
