"""Deployment regression tests for request boundaries."""

from pathlib import Path

from app.config import (
    DEFAULT_MAX_CLAIM_LENGTH,
    DEFAULT_MAX_REQUEST_BODY_BYTES,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def boundary_script_text():
    """Return the Docker request-boundary script."""

    return (
        PROJECT_ROOT
        / "scripts"
        / "request_boundary_check.sh"
    ).read_text(
        encoding="utf-8"
    )


def readme_boundary_section():
    """Return the documented request-boundary section."""

    readme = (
        PROJECT_ROOT / "README.md"
    ).read_text(
        encoding="utf-8"
    )

    start_marker = (
        "<!-- request-boundaries:start -->"
    )

    end_marker = (
        "<!-- request-boundaries:end -->"
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


def test_docker_check_covers_boundary_contract():
    """The real HTTP check must cover every public boundary."""

    script = boundary_script_text()

    required_fragments = (
        "MAX_REQUEST_BODY_BYTES",
        "MAX_CLAIM_LENGTH",
        "claim_too_long",
        "payload_too_large",
        "unsupported_media_type",
        "invalid_request",
        "HTTP 413",
        "HTTP 415",
        "HTTP 422",
    )

    for fragment in required_fragments:
        assert fragment in script


def test_docker_check_validates_safety_and_metrics():
    """The Docker check should verify IDs, metrics and secrecy."""

    script = boundary_script_text()

    required_fragments = (
        "x-request-id",
        "evidence_verification_errors_total",
        "evidence_http_requests_total",
        "Private request values absent from logs",
        "sk-proj-secret",
        "hf_private_token",
        '"/live"',
        '"/ready"',
    )

    for fragment in required_fragments:
        assert fragment in script


def test_readme_matches_runtime_defaults():
    """Documentation should match configured default limits."""

    section = readme_boundary_section()

    assert (
        "MAX_REQUEST_BODY_BYTES={}".format(
            DEFAULT_MAX_REQUEST_BODY_BYTES
        )
        in section
    )

    assert (
        "MAX_CLAIM_LENGTH={}".format(
            DEFAULT_MAX_CLAIM_LENGTH
        )
        in section
    )

    required_fragments = (
        "HTTP 400",
        "HTTP 413",
        "HTTP 415",
        "HTTP 422",
        "claim_too_long",
        "payload_too_large",
        "unsupported_media_type",
        "./scripts/request_boundary_check.sh",
    )

    for fragment in required_fragments:
        assert fragment in section
