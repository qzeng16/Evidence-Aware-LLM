"""Tests that deployment checks use the correct probe roles."""

from pathlib import Path


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def read_project_file(
    relative_path: str,
) -> str:
    """Read one project file as UTF-8 text."""

    return (
        PROJECT_ROOT
        / relative_path
    ).read_text(
        encoding="utf-8"
    )


def test_docker_healthcheck_uses_liveness() -> None:
    """Docker health should represent process liveness."""

    dockerfile = read_project_file(
        "Dockerfile"
    )

    assert "HEALTHCHECK " in dockerfile
    assert "/live" in dockerfile

    healthcheck = dockerfile.split(
        "HEALTHCHECK ",
        1,
    )[1].split(
        "\n\n",
        1,
    )[0]

    assert "/ready" not in healthcheck
    assert "/health" not in healthcheck


def test_release_check_uses_all_probe_roles() -> None:
    """Release validation should separate the three probes."""

    script = read_project_file(
        "scripts/release_check.sh"
    )

    assert '"${BASE_URL}/live"' in script
    assert '"${BASE_URL}/ready"' in script
    assert '"${BASE_URL}/health"' in script
    assert "READY_FILE" in script
    assert (
        "initialization_error"
        in script
    )


def test_hf_check_validates_all_public_probes() -> None:
    """Public deployment checks should cover all probes."""

    script = read_project_file(
        "scripts/hf_space.sh"
    )

    assert 'load_json("/live")' in script
    assert 'load_json("/ready")' in script
    assert 'load_json("/health")' in script
    assert (
        '"/health exposed initialization_error."'
        in script
    )


def test_unready_container_remains_live() -> None:
    """Unready verification must not fail Docker liveness."""

    script = read_project_file(
        "scripts/error_contract_check.sh"
    )

    assert "wait_for_http_status" in script
    assert "wait_for_docker_health" in script
    assert '"readiness_unavailable"' in script
    assert (
        '"docker_health_uses_liveness": True'
        in script
    )


def test_llm_smoke_test_requires_readiness() -> None:
    """A real provider request should follow /ready."""

    script = read_project_file(
        "scripts/smoke_test_llm_api.sh"
    )

    assert (
        'Checking ${BASE_URL}/ready'
        in script
    )
    assert '"${BASE_URL}/ready"' in script
    assert (
        "Readiness response status "
        "is not ready."
        in script
    )
