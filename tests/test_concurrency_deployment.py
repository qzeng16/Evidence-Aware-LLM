"""Deployment regression tests for concurrency protection."""

from pathlib import Path

from app.config import (
    DEFAULT_MAX_CONCURRENT_VERIFICATIONS,
    DEFAULT_VERIFICATION_QUEUE_TIMEOUT_SECONDS,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def overload_script_text():
    """Return the Docker overload-check script."""

    return (
        PROJECT_ROOT
        / "scripts"
        / "concurrency_overload_check.sh"
    ).read_text(
        encoding="utf-8"
    )


def concurrency_readme_section():
    """Return the documented concurrency section."""

    readme = (
        PROJECT_ROOT / "README.md"
    ).read_text(
        encoding="utf-8"
    )

    start_marker = (
        "<!-- concurrency-protection:start -->"
    )

    end_marker = (
        "<!-- concurrency-protection:end -->"
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


def test_docker_check_exercises_overload_contract():
    """The real Docker check must validate 200 and 429 behavior."""

    script = overload_script_text()

    required_fragments = (
        "MAX_CONCURRENT_VERIFICATIONS",
        "VERIFICATION_QUEUE_TIMEOUT_SECONDS",
        "status_counts[200]",
        "status_counts[429]",
        "service_overloaded",
        "retry-after",
        "x-request-id",
        "${BASE_URL}/ready",
        'get_json("/live")',
    )

    for fragment in required_fragments:
        assert fragment in script


def test_docker_check_validates_saturation_metrics():
    """Every saturation metric should be checked."""

    script = overload_script_text()

    required_metrics = (
        "evidence_verification_in_flight",
        "evidence_verification_rejected_total",
        "evidence_verification_",
        "queue_wait_seconds_count",
        "evidence_verification_errors_total",
    )

    for metric_name in required_metrics:
        assert metric_name in script

    assert (
        '"error_type": "service_overloaded"'
        in script
    )


def test_readme_documents_runtime_controls():
    """Documentation should match runtime defaults."""

    section = concurrency_readme_section()

    assert (
        "MAX_CONCURRENT_VERIFICATIONS={}".format(
            DEFAULT_MAX_CONCURRENT_VERIFICATIONS
        )
        in section
    )

    assert (
        (
            "VERIFICATION_QUEUE_TIMEOUT_SECONDS={}"
        ).format(
            DEFAULT_VERIFICATION_QUEUE_TIMEOUT_SECONDS
        )
        in section
    )

    assert "429 Too Many Requests" in section
    assert "Retry-After: 1" in section
    assert "service_overloaded" in section

    assert (
        "./scripts/concurrency_overload_check.sh"
        in section
    )

    assert "process-local" in section
