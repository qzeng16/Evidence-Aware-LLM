"""Tests for CI performance-smoke configuration."""

from pathlib import Path


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def test_ci_loads_image_and_runs_performance_gate():
    workflow = (
        PROJECT_ROOT
        / ".github"
        / "workflows"
        / "ci.yml"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "Docker build and performance smoke"
        in workflow
    )

    assert "load: true" in workflow

    assert (
        "./scripts/performance_smoke_check.sh"
        in workflow
    )

    assert (
        'PERFORMANCE_SMOKE_MIN_RPS: "1.0"'
        in workflow
    )

    assert (
        'PERFORMANCE_SMOKE_MAX_P95_MS: "5000"'
        in workflow
    )


def test_smoke_script_uses_rule_only_ready_service():
    script = (
        PROJECT_ROOT
        / "scripts"
        / "performance_smoke_check.sh"
    ).read_text(
        encoding="utf-8"
    )

    assert "VERIFIER_MODE=rule_only" in script
    assert '"/ready"' not in script
    assert "${BASE_URL}/ready" in script
    assert "--endpoint verify" in script
    assert "evaluate_performance_gate" in script
