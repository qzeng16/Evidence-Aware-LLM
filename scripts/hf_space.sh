#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

HF_SPACE_REPO="${HF_SPACE_REPO:-qzeng16/evidence-aware-llm-api}"
HF_SPACE_URL="${HF_SPACE_URL:-https://qzeng16-evidence-aware-llm-api.hf.space}"

check_deployment() {
  python3 - "$HF_SPACE_URL" <<'PY'
import json
import sys
import urllib.request


base_url = sys.argv[1].rstrip("/")


def load_json(
    path: str,
    *,
    method: str = "GET",
    payload=None,
) -> dict:
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(
        request,
        timeout=180,
    ) as response:
        if response.status != 200:
            raise SystemExit(
                f"{path} returned HTTP {response.status}"
            )

        return json.loads(
            response.read().decode("utf-8")
        )


def reject_secrets(value: object) -> None:
    serialized = json.dumps(value)

    for forbidden in (
        "OPENAI_API_KEY",
        "sk-proj-",
        "hf_",
    ):
        if forbidden in serialized:
            raise SystemExit(
                "Public response exposed forbidden "
                f"content: {forbidden}"
            )


print("========================================")
print("Checking public demo page")
print("========================================")

demo_request = urllib.request.Request(
    f"{base_url}/",
    headers={
        "Accept": "text/html",
    },
)

with urllib.request.urlopen(
    demo_request,
    timeout=180,
) as response:
    if response.status != 200:
        raise SystemExit(
            f"/ returned HTTP {response.status}"
        )

    demo_html = response.read().decode("utf-8")

required_demo_content = (
    "Evidence-Aware Claim Verification",
    'id="verify-form"',
    'id="claim"',
    'id="submit-button"',
    'requestJson("/health"',
    'requestJson("/verify"',
)

missing_demo_content = [
    value
    for value in required_demo_content
    if value not in demo_html
]

if missing_demo_content:
    raise SystemExit(
        "Public demo validation failed. Missing:\n- "
        + "\n- ".join(missing_demo_content)
    )

print("Public demo page returned HTTP 200")

print()
print("========================================")
print("Checking public /health")
print("========================================")

health = load_json("/health")

expected_health = {
    "status": "ready",
    "verifier_mode": "rule_only",
    "active_verifier_mode": "rule",
    "llm_verifier_available": False,
}

for key, expected in expected_health.items():
    actual = health.get(key)

    if actual != expected:
        raise SystemExit(
            f"/health field {key!r}: expected "
            f"{expected!r}, got {actual!r}"
        )

reject_secrets(health)

print(
    json.dumps(
        health,
        indent=2,
        ensure_ascii=False,
    )
)

print()
print("========================================")
print("Checking public /docs")
print("========================================")

with urllib.request.urlopen(
    f"{base_url}/docs",
    timeout=180,
) as response:
    if response.status != 200:
        raise SystemExit(
            f"/docs returned HTTP {response.status}"
        )

print("/docs returned HTTP 200")

print()
print("========================================")
print("Checking public POST /verify")
print("========================================")

verification_response = load_json(
    "/verify",
    method="POST",
    payload={
        "claim": (
            "Retrieval augmented generation can "
            "improve factual reliability."
        )
    },
)

if verification_response.get("status") != "success":
    raise SystemExit(
        "/verify response status is not success."
    )

data = verification_response.get("data")

if not isinstance(data, dict):
    raise SystemExit(
        "/verify response data is missing."
    )

verification = data.get("verification")

if not isinstance(verification, dict):
    raise SystemExit(
        "Unified verification result is missing."
    )

if verification.get("verifier_type") != "rule":
    raise SystemExit(
        "Expected verifier_type='rule', got "
        f"{verification.get('verifier_type')!r}."
    )

if verification.get("label") not in {
    "Supported",
    "Refuted",
    "Uncertain",
}:
    raise SystemExit(
        "Verification label is invalid."
    )

metadata = verification_response.get("metadata")

if not isinstance(metadata, dict):
    raise SystemExit(
        "/verify metadata is missing."
    )

if metadata.get("active_verifier_mode") != "rule":
    raise SystemExit(
        "Expected active_verifier_mode='rule'."
    )

reject_secrets(verification_response)

summary = {
    "status": verification_response.get("status"),
    "label": verification.get("label"),
    "confidence": verification.get("confidence"),
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
        summary,
        indent=2,
        ensure_ascii=False,
    )
)

print()
print("========================================")
print("Public deployment check passed")
print("========================================")
print()
print(f"Health: {base_url}/health")
print(f"Docs:   {base_url}/docs")
print(f"Verify: POST {base_url}/verify")
PY
}

deploy_space() {
  command -v hf >/dev/null 2>&1 || {
    echo "Hugging Face CLI is not installed." >&2
    exit 1
  }

  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree is not clean:"
    git status --short
    echo
    echo "Commit local changes before deployment."
    exit 1
  fi

  echo "========================================"
  echo "Checking Hugging Face authentication"
  echo "========================================"

  hf auth whoami

  local temp_dir
  temp_dir="$(mktemp -d)"

  cleanup() {
    rm -rf "$temp_dir"
  }

  trap cleanup RETURN

  echo
  echo "========================================"
  echo "Preparing committed project files"
  echo "========================================"

  git archive \
    --format=tar \
    HEAD \
    | tar -xf - -C "$temp_dir"

  echo
  echo "========================================"
  echo "Uploading Hugging Face Space"
  echo "========================================"

  hf upload \
    "$HF_SPACE_REPO" \
    "$temp_dir" \
    . \
    --repo-type space \
    --commit-message \
    "Deploy Git commit $(git rev-parse --short HEAD)"

  echo
  echo "========================================"
  echo "Hugging Face upload completed"
  echo "========================================"
}

show_usage() {
  echo "Usage:"
  echo "  ./scripts/hf_space.sh check"
  echo "  ./scripts/hf_space.sh deploy"
}

case "${1:-check}" in
  check)
    check_deployment
    ;;
  deploy)
    deploy_space
    ;;
  *)
    show_usage
    exit 1
    ;;
esac
