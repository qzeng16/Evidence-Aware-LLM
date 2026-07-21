"""Deployment regression tests for verification timeouts."""

from pathlib import Path

from app.config import (
    DEFAULT_VERIFICATION_TIMEOUT_SECONDS,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def timeout_script_text():
    """Return the Docker timeout-check script."""

    return (
        PROJECT_ROOT
        / "scripts"
        / "verification_timeout_check.sh"
    ).read_text(
        encoding="utf-8"
    )


def integration_app_text():
    """Return the deterministic timeout application."""

    return (
        PROJECT_ROOT
        / "scripts"
        / "timeout_integration_app.py"
    ).read_text(
        encoding="utf-8"
    )


def readme_timeout_section():
    """Return the timeout documentation section."""

    readme = (
        PROJECT_ROOT / "README.md"
    ).read_text(
        encoding="utf-8"
    )

    start_marker = (
        "<!-- verification-timeout:start -->"
    )

    end_marker = (
        "<!-- verification-timeout:end -->"
    )

    start_index = readme.index(
        start_marker
    )

    end_index = readme.index(
        end_marker
    )

    return readme[
        start_index:end_index
    ]


def test_docker_check_covers_timeout_lifecycle():
    """The real check must cover timeout and slot retention."""

    script = timeout_script_text()

    required_fragments = (
        "verification_timeout",
        "HTTP 504",
        "HTTP 429",
        "HTTP 200",
        "retry-after",
        "x-request-id",
        "Request during background execution",
        "Request after background completion",
        "Private claim absent from logs",
    )

    for fragment in required_fragments:
        assert fragment in script


def test_docker_check_validates_timeout_metrics():
    """Timeout, execution and concurrency metrics must be checked."""

    script = timeout_script_text()

    required_fragments = (
        "evidence_verification_timeouts_total",
        "evidence_verification_",
        "execution_duration_seconds_count",
        "evidence_verification_rejected_total",
        "evidence_verification_errors_total",
        "evidence_verification_in_flight",
        '"/live"',
        '"/ready"',
    )

    for fragment in required_fragments:
        assert fragment in script


def test_documentation_matches_runtime_behavior():
    """README should match defaults and resource semantics."""

    section = readme_timeout_section()
    integration_app = integration_app_text()

    assert (
        "VERIFICATION_TIMEOUT_SECONDS={}".format(
            DEFAULT_VERIFICATION_TIMEOUT_SECONDS
        )
        in section
    )

    required_fragments = (
        "HTTP 504",
        "verification_timeout",
        "retryable: true",
        "does not cancel",
        "retains its concurrency",
        "./scripts/verification_timeout_check.sh",
    )

    for fragment in required_fragments:
        assert fragment in section

    assert (
        "configure_verification_concurrency"
        in integration_app
    )

    assert (
        "configure_verification_execution"
        in integration_app
    )

    assert "time.sleep(1.0)" in integration_app
