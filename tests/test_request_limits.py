"""Tests for API request and claim boundaries."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client.parser import (
    text_string_to_metric_families,
)

import app.routes as routes
from app.config import (
    ConfigurationError,
    load_app_config,
)
from app.exception_handlers import (
    register_exception_handlers,
)
from app.metrics import render_metrics
from app.observability import (
    RequestLoggingMiddleware,
)
from app.request_limits import (
    RequestBoundaryMiddleware,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def successful_response():
    """Return one valid verification response."""

    return {
        "status": "success",
        "data": {
            "verification": {
                "label": "Supported",
                "confidence": 0.9,
                "verifier_type": "rule",
            },
        },
        "metadata": {
            "verifier_mode": "rule_only",
            "active_verifier_mode": "rule",
        },
        "error": None,
    }


def build_client(
    *,
    max_request_body_bytes=4096,
):
    """Build a lightweight app with production middleware order."""

    test_app = FastAPI()

    test_app.add_middleware(
        RequestBoundaryMiddleware,
        max_request_body_bytes=(
            max_request_body_bytes
        ),
    )

    test_app.add_middleware(
        RequestLoggingMiddleware
    )

    register_exception_handlers(
        test_app
    )

    test_app.include_router(
        routes.router
    )

    return TestClient(
        test_app,
        raise_server_exceptions=False,
    )


def metric_value(
    name,
    **expected_labels
):
    """Read one Prometheus sample."""

    payload, _ = render_metrics()

    text = payload.decode("utf-8")

    for family in text_string_to_metric_families(
        text
    ):
        for sample in family.samples:
            if (
                sample.name == name
                and sample.labels
                == expected_labels
            ):
                return float(sample.value)

    return 0.0


def test_configuration_loads_request_limits():
    config = load_app_config(
        {
            "MAX_REQUEST_BODY_BYTES": "8192",
            "MAX_CLAIM_LENGTH": "2000",
        }
    )

    assert config.max_request_body_bytes == 8192
    assert config.max_claim_length == 2000


@pytest.mark.parametrize(
    "name",
    (
        "MAX_REQUEST_BODY_BYTES",
        "MAX_CLAIM_LENGTH",
    ),
)
def test_configuration_rejects_invalid_limits(
    name,
):
    with pytest.raises(
        ConfigurationError,
        match="greater than zero",
    ):
        load_app_config(
            {
                name: "0",
            }
        )


def test_wrong_content_type_returns_safe_415(
    monkeypatch,
):
    secret = (
        "private-claim-"
        "OPENAI_API_KEY=sk-proj-secret"
    )

    def fail_if_called(claim):
        raise AssertionError(
            "Verifier must not be called."
        )

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        fail_if_called,
    )

    client = build_client()

    response = client.post(
        "/verify",
        content=secret,
        headers={
            "Content-Type": "text/plain",
            "X-Request-ID": (
                "unsupported-media-001"
            ),
        },
    )

    body = response.json()

    assert response.status_code == 415

    assert (
        body["error"]["type"]
        == "unsupported_media_type"
    )

    assert (
        body["error"]["code"]
        == "unsupported_media_type"
    )

    assert body["error"]["retryable"] is False

    assert (
        body["request_id"]
        == "unsupported-media-001"
    )

    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )

    assert secret not in response.text
    assert "sk-proj-secret" not in response.text


def test_missing_content_type_returns_415():
    client = build_client()

    response = client.post(
        "/verify",
        content='{"claim": "A claim."}',
        headers={
            "X-Request-ID": (
                "missing-content-type-001"
            ),
        },
    )

    assert response.status_code == 415

    assert (
        response.json()["error"]["type"]
        == "unsupported_media_type"
    )


def test_oversized_body_returns_safe_413(
    monkeypatch,
):
    secret = "private-oversized-value-" * 20

    def fail_if_called(claim):
        raise AssertionError(
            "Verifier must not be called."
        )

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        fail_if_called,
    )

    client = build_client(
        max_request_body_bytes=80
    )

    response = client.post(
        "/verify",
        content=json.dumps(
            {
                "claim": secret,
            }
        ),
        headers={
            "Content-Type": "application/json",
            "X-Request-ID": (
                "payload-too-large-001"
            ),
        },
    )

    body = response.json()

    assert response.status_code == 413

    assert (
        body["error"]["type"]
        == "payload_too_large"
    )

    assert (
        body["error"]["code"]
        == "payload_too_large"
    )

    assert body["error"]["retryable"] is False

    assert (
        body["request_id"]
        == "payload-too-large-001"
    )

    assert secret not in response.text


def test_json_suffix_media_type_is_allowed(
    monkeypatch,
):
    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        lambda claim: successful_response(),
    )

    client = build_client()

    response = client.post(
        "/verify",
        content=json.dumps(
            {
                "claim": "A valid claim.",
            }
        ),
        headers={
            "Content-Type": (
                "application/problem+json"
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_long_claim_returns_400_before_verifier(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        routes,
        "get_max_claim_length",
        lambda: 10,
    )

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        lambda claim: calls.append(claim),
    )

    client = build_client()

    response = client.post(
        "/verify",
        json={
            "claim": "12345678901",
        },
        headers={
            "X-Request-ID": "long-claim-001",
        },
    )

    body = response.json()

    assert response.status_code == 400

    assert (
        body["error"]["type"]
        == "invalid_claim"
    )

    assert (
        body["error"]["code"]
        == "claim_too_long"
    )

    assert body["error"]["retryable"] is False
    assert body["request_id"] == "long-claim-001"
    assert calls == []


def test_boundary_errors_record_metrics():
    unsupported_before = metric_value(
        "evidence_verification_errors_total",
        error_type="unsupported_media_type",
    )

    oversized_before = metric_value(
        "evidence_verification_errors_total",
        error_type="payload_too_large",
    )

    client = build_client(
        max_request_body_bytes=60
    )

    unsupported = client.post(
        "/verify",
        content="not-json",
        headers={
            "Content-Type": "text/plain",
        },
    )

    oversized = client.post(
        "/verify",
        content=json.dumps(
            {
                "claim": "x" * 200,
            }
        ),
        headers={
            "Content-Type": "application/json",
        },
    )

    unsupported_after = metric_value(
        "evidence_verification_errors_total",
        error_type="unsupported_media_type",
    )

    oversized_after = metric_value(
        "evidence_verification_errors_total",
        error_type="payload_too_large",
    )

    assert unsupported.status_code == 415
    assert oversized.status_code == 413

    assert (
        unsupported_after
        - unsupported_before
        == 1.0
    )

    assert (
        oversized_after
        - oversized_before
        == 1.0
    )


def test_main_keeps_logging_outside_boundary():
    main_text = (
        PROJECT_ROOT
        / "app"
        / "main.py"
    ).read_text(
        encoding="utf-8"
    )

    boundary_index = main_text.index(
        "RequestBoundaryMiddleware"
    )

    logging_index = main_text.rindex(
        "RequestLoggingMiddleware"
    )

    assert boundary_index < logging_index
