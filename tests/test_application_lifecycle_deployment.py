"""Deployment regressions for application lifecycle behavior."""

from pathlib import Path

from app.config import (
    DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def read_text(relative_path):
    """Read one checked-in project file."""

    return (
        PROJECT_ROOT / relative_path
    ).read_text(
        encoding="utf-8"
    )


def lifecycle_readme_section():
    """Return the documented graceful-shutdown section."""

    readme = read_text(
        "README.md"
    )

    start_marker = (
        "<!-- graceful-shutdown:start -->"
    )

    end_marker = (
        "<!-- graceful-shutdown:end -->"
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


def test_application_uses_lifespan_without_event_hooks():
    """Production startup must use the FastAPI lifespan contract."""

    main_text = read_text(
        "app/main.py"
    )

    lifecycle_text = read_text(
        "app/lifecycle.py"
    )

    assert (
        "lifespan=application_lifespan"
        in main_text
    )

    assert "@app.on_event" not in main_text

    required_fragments = (
        "initialize_service()",
        "shutdown_verification_execution",
        "reset_service_state()",
        "verification_shutdown_drained",
    )

    for fragment in required_fragments:
        assert fragment in lifecycle_text


def test_docker_check_exercises_sigterm_drain_order():
    """The Docker check must prove work drains before cleanup."""

    script = read_text(
        "scripts/graceful_shutdown_check.sh"
    )

    required_fragments = (
        "--signal=TERM",
        "Slow request: HTTP 504",
        "In-flight background tasks",
        "LAYER94_BACKGROUND_STARTED",
        "LAYER94_BACKGROUND_COMPLETED",
        "LAYER94_SERVICE_STATE_RESET",
        "started_index",
        "completed_index",
        "reset_index",
        "Container exit code: 0",
        "Private claim absent from logs",
        "Graceful shutdown check passed",
    )

    for fragment in required_fragments:
        assert fragment in script


def test_documentation_matches_runtime_configuration():
    """README, Docker signal forwarding and defaults must agree."""

    section = lifecycle_readme_section()

    dockerfile = read_text(
        "Dockerfile"
    )

    expected_default = (
        "GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS={}"
        .format(
            DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
        )
    )

    assert expected_default in section

    required_fragments = (
        "application lifespan",
        "stops accepting new verification work",
        "HTTP 503",
        "service_shutting_down",
        "Retry-After: 1",
        "./scripts/graceful_shutdown_check.sh",
    )

    for fragment in required_fragments:
        assert fragment in section

    assert (
        "exec python -m uvicorn"
        in dockerfile
    )
