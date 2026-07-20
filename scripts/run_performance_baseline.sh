#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$PROJECT_ROOT"

IMAGE_NAME="${IMAGE_NAME:-evidence-aware-llm:performance-baseline}"
CONTAINER_NAME="${CONTAINER_NAME:-evidence-aware-llm-performance-baseline}"

HOST_PORT="${HOST_PORT:-8008}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

CPU_LIMIT="${CPU_LIMIT:-2}"
MEMORY_LIMIT="${MEMORY_LIMIT:-4g}"

REQUESTS_PER_SCENARIO="${REQUESTS_PER_SCENARIO:-30}"

WARMUP_REQUESTS="${WARMUP_REQUESTS:-3}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-60}"

OUTPUT_DIR="$PROJECT_ROOT/performance/baselines"
BASELINE_FILE="$OUTPUT_DIR/local_rule_only.json"

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

wait_for_readiness() {
  for attempt in $(seq 1 180); do
    status="$(
      curl \
        --silent \
        --output /dev/null \
        --write-out "%{http_code}" \
        --max-time 5 \
        "${BASE_URL}/ready" \
        2>/dev/null \
        || true
    )"

    if [[ "$status" == "200" ]]; then
      return 0
    fi

    if ! docker ps \
      --format '{{.Names}}' \
      | grep -qx "$CONTAINER_NAME"; then
      echo "Container stopped during initialization."
      show_logs
      return 1
    fi

    sleep 2
  done

  echo "Service did not become ready before timeout."
  show_logs

  return 1
}

trap cleanup EXIT

command -v docker >/dev/null 2>&1 || {
  echo "Docker is not available." >&2
  exit 1
}

if [[ ! -f "scripts/load_test_api.py" ]]; then
  echo "scripts/load_test_api.py is missing." >&2
  exit 1
fi

if [[ ! -f "app/performance.py" ]]; then
  echo "app/performance.py is missing." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo
echo "========================================"
echo "1. Validating performance utilities"
echo "========================================"

python -m pytest \
  tests/test_performance.py \
  -q

python -m py_compile \
  app/performance.py \
  scripts/load_test_api.py

echo
echo "========================================"
echo "2. Building benchmark Docker image"
echo "========================================"

docker build \
  --tag "$IMAGE_NAME" \
  .

docker rm -f \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1 || true

echo
echo "========================================"
echo "3. Starting rule-only benchmark service"
echo "========================================"

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "${HOST_PORT}:8000" \
  --cpus "$CPU_LIMIT" \
  --memory "$MEMORY_LIMIT" \
  --env VERIFIER_MODE=rule_only \
  "$IMAGE_NAME" \
  >/dev/null

wait_for_readiness

curl \
  --fail \
  --silent \
  --show-error \
  "${BASE_URL}/live" \
  > "${TEMP_DIR}/live.json"

curl \
  --fail \
  --silent \
  --show-error \
  "${BASE_URL}/ready" \
  > "${TEMP_DIR}/ready.json"

curl \
  --fail \
  --silent \
  --show-error \
  "${BASE_URL}/health" \
  > "${TEMP_DIR}/health.json"

IMAGE_ID="$(
  docker image inspect \
    --format '{{.Id}}' \
    "$IMAGE_NAME"
)"

CONTAINER_PYTHON="$(
  docker exec \
    "$CONTAINER_NAME" \
    python --version \
    2>&1
)"

DOCKER_VERSION="$(
  docker version \
    --format '{{.Server.Version}}' \
    2>/dev/null \
    || echo "unknown"
)"

GIT_COMMIT="$(
  git rev-parse HEAD
)"

if [[ -n "$(git status --porcelain)" ]]; then
  GIT_DIRTY="true"
else
  GIT_DIRTY="false"
fi

echo
echo "========================================"
echo "4. Running performance scenarios"
echo "========================================"

ENDPOINTS=(
  "live"
  "ready"
  "verify"
)

CONCURRENCIES=(
  "1"
  "4"
  "8"
)

for endpoint in "${ENDPOINTS[@]}"; do
  for concurrency in "${CONCURRENCIES[@]}"; do
    run_name="${endpoint}_c${concurrency}"

    echo
    echo "Endpoint: /${endpoint}"
    echo "Concurrency: ${concurrency}"
    echo "Requests: ${REQUESTS_PER_SCENARIO}"

    python scripts/load_test_api.py \
      --base-url "$BASE_URL" \
      --endpoint "$endpoint" \
      --requests "$REQUESTS_PER_SCENARIO" \
      --concurrency "$concurrency" \
      --warmup "$WARMUP_REQUESTS" \
      --timeout "$REQUEST_TIMEOUT" \
      --min-success-rate 1.0 \
      --output "${TEMP_DIR}/${run_name}.json" \
      >/dev/null
  done
done

curl \
  --fail \
  --silent \
  --show-error \
  "${BASE_URL}/metrics" \
  > "${TEMP_DIR}/metrics.txt"

docker logs \
  "$CONTAINER_NAME" \
  > "${TEMP_DIR}/container.log" \
  2>&1

echo
echo "========================================"
echo "5. Building aggregate baseline report"
echo "========================================"

export TEMP_DIR
export BASELINE_FILE
export IMAGE_NAME
export IMAGE_ID
export CONTAINER_PYTHON
export DOCKER_VERSION
export GIT_COMMIT
export GIT_DIRTY
export CPU_LIMIT
export MEMORY_LIMIT
export REQUESTS_PER_SCENARIO
export WARMUP_REQUESTS
export REQUEST_TIMEOUT

python - <<'__AGGREGATE_PERFORMANCE_RESULTS_EOF__'
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path


temp_dir = Path(os.environ["TEMP_DIR"])
baseline_file = Path(
    os.environ["BASELINE_FILE"]
)

endpoints = (
    "live",
    "ready",
    "verify",
)

concurrencies = (
    1,
    4,
    8,
)

expected_requests = int(
    os.environ["REQUESTS_PER_SCENARIO"]
)

scenarios = []
errors = []

for endpoint in endpoints:
    for concurrency in concurrencies:
        path = (
            temp_dir
            / "{}_c{}.json".format(
                endpoint,
                concurrency,
            )
        )

        report = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        results = report["results"]

        if (
            results["completed_requests"]
            != expected_requests
        ):
            errors.append(
                "/{} concurrency {} completed "
                "{} requests instead of {}.".format(
                    endpoint,
                    concurrency,
                    results[
                        "completed_requests"
                    ],
                    expected_requests,
                )
            )

        if results["success_rate"] != 1.0:
            errors.append(
                "/{} concurrency {} success "
                "rate was {}.".format(
                    endpoint,
                    concurrency,
                    results["success_rate"],
                )
            )

        scenarios.append(
            {
                "endpoint": (
                    results["endpoint"]
                ),
                "concurrency": concurrency,
                "configuration": (
                    report["configuration"]
                ),
                "results": results,
            }
        )

if errors:
    raise SystemExit(
        "Performance baseline failed:\n- "
        + "\n- ".join(errors)
    )

metrics_text = (
    temp_dir / "metrics.txt"
).read_text(
    encoding="utf-8",
    errors="replace",
)

metric_prefixes = (
    "evidence_http_requests_total",
    (
        "evidence_http_request_"
        "duration_seconds_count"
    ),
    (
        "evidence_verification_"
        "requests_total"
    ),
)

metrics_snapshot = [
    line
    for line in metrics_text.splitlines()
    if line.startswith(metric_prefixes)
]

live = json.loads(
    (
        temp_dir / "live.json"
    ).read_text(
        encoding="utf-8"
    )
)

ready = json.loads(
    (
        temp_dir / "ready.json"
    ).read_text(
        encoding="utf-8"
    )
)

health = json.loads(
    (
        temp_dir / "health.json"
    ).read_text(
        encoding="utf-8"
    )
)

baseline = {
    "schema_version": 1,
    "benchmark_type": (
        "local_docker_rule_only_baseline"
    ),
    "generated_at": datetime.now(
        timezone.utc
    ).isoformat(),
    "scope": {
        "purpose": (
            "Development regression baseline; "
            "not a production capacity claim."
        ),
        "base_url": (
            "http://127.0.0.1:<local-port>"
        ),
        "verifier_mode": "rule_only",
        "endpoints": [
            "/live",
            "/ready",
            "/verify",
        ],
    },
    "source": {
        "git_commit": os.environ[
            "GIT_COMMIT"
        ],
        "working_tree_dirty": (
            os.environ["GIT_DIRTY"]
            == "true"
        ),
        "docker_image": os.environ[
            "IMAGE_NAME"
        ],
        "docker_image_id": os.environ[
            "IMAGE_ID"
        ],
    },
    "environment": {
        "host_platform": platform.platform(),
        "host_machine": platform.machine(),
        "host_python": (
            platform.python_version()
        ),
        "container_python": os.environ[
            "CONTAINER_PYTHON"
        ],
        "docker_server_version": (
            os.environ["DOCKER_VERSION"]
        ),
        "container_cpu_limit": (
            os.environ["CPU_LIMIT"]
        ),
        "container_memory_limit": (
            os.environ["MEMORY_LIMIT"]
        ),
    },
    "configuration": {
        "requests_per_scenario": int(
            os.environ[
                "REQUESTS_PER_SCENARIO"
            ]
        ),
        "warmup_requests": int(
            os.environ[
                "WARMUP_REQUESTS"
            ]
        ),
        "request_timeout_seconds": float(
            os.environ[
                "REQUEST_TIMEOUT"
            ]
        ),
        "concurrencies": list(
            concurrencies
        ),
    },
    "probe_snapshot": {
        "live": live,
        "ready": ready,
        "health": health,
    },
    "scenarios": scenarios,
    "prometheus_snapshot": (
        metrics_snapshot
    ),
}

serialized = json.dumps(
    baseline,
    indent=2,
    ensure_ascii=False,
)

baseline_file.parent.mkdir(
    parents=True,
    exist_ok=True,
)

baseline_file.write_text(
    serialized + "\n",
    encoding="utf-8",
)

print()
print(
    "{:<10} {:>11} {:>9} {:>11} "
    "{:>10} {:>10} {:>10}".format(
        "Endpoint",
        "Concurrency",
        "Success",
        "RPS",
        "Avg ms",
        "P95 ms",
        "P99 ms",
    )
)

print("-" * 78)

for scenario in scenarios:
    results = scenario["results"]
    latency = results["latency_ms"]

    print(
        "{:<10} {:>11} {:>8.1%} {:>11.3f} "
        "{:>10.3f} {:>10.3f} {:>10.3f}".format(
            results["endpoint"],
            scenario["concurrency"],
            results["success_rate"],
            results["throughput_rps"],
            latency["average"],
            latency["p95"],
            latency["p99"],
        )
    )

print()
print(
    "Baseline written to: {}".format(
        baseline_file
    )
)
__AGGREGATE_PERFORMANCE_RESULTS_EOF__

echo
echo "========================================"
echo "Performance baseline completed"
echo "========================================"
echo
echo "Report: ${BASELINE_FILE}"
echo "Container resources: ${CPU_LIMIT} CPU / ${MEMORY_LIMIT} memory"
echo "Requests per scenario: ${REQUESTS_PER_SCENARIO}"
echo "Warmup requests: ${WARMUP_REQUESTS}"
