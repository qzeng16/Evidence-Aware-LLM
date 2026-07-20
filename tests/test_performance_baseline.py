"""Tests for the committed local performance baseline."""

import json
import re
from pathlib import Path


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

BASELINE_PATH = (
    PROJECT_ROOT
    / "performance"
    / "baselines"
    / "local_rule_only.json"
)

EXPECTED_SCENARIOS = {
    (endpoint, concurrency)
    for endpoint in (
        "/live",
        "/ready",
        "/verify",
    )
    for concurrency in (
        1,
        4,
        8,
    )
}


def load_baseline():
    """Load the committed performance report."""

    return json.loads(
        BASELINE_PATH.read_text(
            encoding="utf-8"
        )
    )


def test_baseline_has_expected_schema_and_matrix():
    """The report should contain all nine scenarios."""

    baseline = load_baseline()

    assert baseline["schema_version"] == 1

    assert baseline["benchmark_type"] == (
        "local_docker_rule_only_baseline"
    )

    scenarios = baseline["scenarios"]

    actual_scenarios = {
        (
            scenario["endpoint"],
            scenario["concurrency"],
        )
        for scenario in scenarios
    }

    assert len(scenarios) == 9
    assert actual_scenarios == EXPECTED_SCENARIOS


def test_baseline_records_complete_successful_runs():
    """Every scenario should contain all measured requests."""

    baseline = load_baseline()

    expected_requests = baseline[
        "configuration"
    ]["requests_per_scenario"]

    for scenario in baseline["scenarios"]:
        results = scenario["results"]

        assert (
            results["completed_requests"]
            == expected_requests
        )

        assert (
            results["successful_requests"]
            == expected_requests
        )

        assert results["failed_requests"] == 0
        assert results["success_rate"] == 1.0
        assert results["error_rate"] == 0.0

        assert (
            results["throughput_rps"]
            > 0
        )

        assert (
            results["latency_ms"]["p95"]
            >= 0
        )


def test_baseline_uses_committed_safe_metadata():
    """The report must identify committed code without secrets."""

    baseline = load_baseline()
    source = baseline["source"]

    assert (
        source["working_tree_dirty"]
        is False
    )

    assert re.fullmatch(
        r"[0-9a-f]{40}",
        source["git_commit"],
    )

    serialized = json.dumps(
        baseline
    )

    forbidden_values = (
        "OPENAI_API_KEY",
        "sk-proj-",
        "hf_private_token",
        "/Users/zengqihong/",
    )

    for forbidden in forbidden_values:
        assert forbidden not in serialized
