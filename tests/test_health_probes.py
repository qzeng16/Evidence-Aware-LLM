"""Tests for liveness, readiness and safe health routes."""

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.health as health
from app.exception_handlers import (
    register_exception_handlers,
)
from app.metrics import render_metrics
from app.observability import (
    RequestLoggingMiddleware,
)
from app.routes import router


def build_test_client() -> TestClient:
    """Build an API without loading production models."""

    test_app = FastAPI()

    test_app.add_middleware(
        RequestLoggingMiddleware
    )

    register_exception_handlers(
        test_app
    )

    test_app.include_router(router)

    return TestClient(
        test_app,
        raise_server_exceptions=False,
    )


def ready_status() -> Dict[str, Any]:
    """Return representative safe service metadata."""

    return {
        "status": "ready",
        "verifier_mode": "rule_only",
        "active_verifier_mode": "rule",
        "llm_verifier_available": False,
        "llm_provider": None,
        "llm_model": None,
        "openai_api_key_configured": False,
        "initialization_error": None,
    }


def unavailable_status(
    secret: str,
) -> Dict[str, Any]:
    """Return internal state containing a private error."""

    return {
        "status": "loading_or_unavailable",
        "verifier_mode": "llm_only",
        "active_verifier_mode": None,
        "llm_verifier_available": False,
        "llm_provider": "openai",
        "llm_model": "test-model",
        "openai_api_key_configured": False,
        "initialization_error": secret,
    }


def test_liveness_remains_200_when_unready(
    monkeypatch,
) -> None:
    """Liveness must describe the process, not model readiness."""

    monkeypatch.setattr(
        health,
        "is_service_ready",
        lambda: False,
    )

    client = build_test_client()

    response = client.get(
        "/live",
        headers={
            "X-Request-ID": "layer74-live-001",
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "alive"
    assert body["data"]["alive"] is True
    assert (
        body["request_id"]
        == "layer74-live-001"
    )
    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_readiness_returns_200_when_ready(
    monkeypatch,
) -> None:
    """Ready services should accept verification traffic."""

    monkeypatch.setattr(
        health,
        "get_service_status",
        ready_status,
    )

    monkeypatch.setattr(
        health,
        "is_service_ready",
        lambda: True,
    )

    client = build_test_client()

    response = client.get(
        "/ready",
        headers={
            "X-Request-ID": "layer74-ready-001",
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ready"
    assert body["data"]["ready"] is True
    assert body["metadata"]["ready"] is True
    assert (
        body["metadata"]["active_verifier_mode"]
        == "rule"
    )
    assert "initialization_error" not in (
        body["metadata"]
    )
    assert (
        body["request_id"]
        == "layer74-ready-001"
    )
    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_readiness_returns_safe_503_when_unready(
    monkeypatch,
) -> None:
    """Readiness failures must use the shared safe contract."""

    secret = (
        "OPENAI_API_KEY=sk-private-layer74 "
        "private initialization failure"
    )

    monkeypatch.setattr(
        health,
        "get_service_status",
        lambda: unavailable_status(secret),
    )

    monkeypatch.setattr(
        health,
        "is_service_ready",
        lambda: False,
    )

    client = build_test_client()

    response = client.get(
        "/ready",
        headers={
            "X-Request-ID": (
                "layer74-unavailable-001"
            ),
        },
    )

    body = response.json()

    assert response.status_code == 503
    assert body["status"] == "error"
    assert body["data"] is None
    assert (
        body["error"]["type"]
        == "service_unavailable"
    )
    assert body["error"]["retryable"] is True
    assert body["metadata"]["ready"] is False
    assert "initialization_error" not in (
        body["metadata"]
    )

    assert secret not in response.text
    assert "sk-private-layer74" not in (
        response.text
    )
    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_health_removes_initialization_error(
    monkeypatch,
) -> None:
    """Public health must not expose internal failure details."""

    secret = (
        "private model path "
        "OPENAI_API_KEY=sk-secret"
    )

    monkeypatch.setattr(
        health,
        "get_service_status",
        lambda: unavailable_status(secret),
    )

    monkeypatch.setattr(
        health,
        "is_service_ready",
        lambda: False,
    )

    client = build_test_client()

    response = client.get("/health")
    body = response.json()

    assert response.status_code == 200
    assert (
        body["status"]
        == "loading_or_unavailable"
    )
    assert body["ready"] is False
    assert body["verifier_mode"] == "llm_only"
    assert "initialization_error" not in body
    assert secret not in response.text
    assert "sk-secret" not in response.text


def test_root_advertises_probe_endpoints() -> None:
    """API navigation should expose both probe roles."""

    client = build_test_client()

    response = client.get(
        "/",
        headers={
            "Accept": "application/json",
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["health_endpoint"] == "/health"
    assert body["liveness_endpoint"] == "/live"
    assert body["readiness_endpoint"] == "/ready"


def test_probe_paths_keep_low_cardinality_metrics(
    monkeypatch,
) -> None:
    """Probe requests should keep their stable path labels."""

    monkeypatch.setattr(
        health,
        "get_service_status",
        ready_status,
    )

    monkeypatch.setattr(
        health,
        "is_service_ready",
        lambda: True,
    )

    client = build_test_client()

    assert client.get("/live").status_code == 200
    assert client.get("/ready").status_code == 200

    payload, _ = render_metrics()
    metrics = payload.decode("utf-8")

    assert (
        'method="GET",path="/live",'
        in metrics
    )
    assert (
        'method="GET",path="/ready",'
        in metrics
    )
