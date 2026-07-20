"""Tests for the public API error contract."""

import json
import re
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client.parser import (
    text_string_to_metric_families,
)

import app.routes as routes
import app.services as services
from app.error_contract import (
    INTERNAL_ERROR,
    INVALID_CLAIM_ERROR,
    SERVICE_UNAVAILABLE_ERROR,
    annotate_error_response,
)
from app.exception_handlers import (
    register_exception_handlers,
)
from app.metrics import render_metrics
from app.observability import (
    REQUEST_LOGGER,
    RequestLoggingMiddleware,
)
from app.verification_result import VerifierType


REQUEST_ID_PATTERN = re.compile(
    r"^[a-f0-9]{32}$"
)


def build_test_client() -> TestClient:
    """Build a lightweight API without startup model loading."""

    test_app = FastAPI()

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


def error_response(
    *,
    error_type: str,
    message: str,
    retryable: bool,
) -> Dict[str, Any]:
    """Build a service-layer error fixture."""

    response: Dict[str, Any] = {
        "status": "error",
        "data": None,
        "metadata": {
            "verifier_mode": "rule_only",
            "active_verifier_mode": "rule",
        },
        "error": {
            "message": message,
        },
    }

    return annotate_error_response(
        response,
        error_type=error_type,
        retryable=retryable,
    )


def metric_value(
    name: str,
    **expected_labels: str,
) -> float:
    """Read one metric sample without label-order assumptions."""

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


def test_unknown_service_exception_is_sanitized(
    monkeypatch,
) -> None:
    """Unknown backend details must not enter response or logs."""

    secret = (
        "private-claim "
        "OPENAI_API_KEY=sk-proj-secret"
    )

    class ExplodingVerifier:
        verifier_type = VerifierType.RULE

        def verify(self, claim: str):
            del claim
            raise RuntimeError(secret)

    logged_responses = []

    monkeypatch.setattr(
        services,
        "is_service_ready",
        lambda: True,
    )

    monkeypatch.setattr(
        services,
        "get_active_verifier",
        lambda: ExplodingVerifier(),
    )

    monkeypatch.setattr(
        services.verifier,
        "validate_claim",
        lambda claim: (True, ""),
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: logged_responses.append(
            response
        ),
    )

    response = services.verify_claim_service(
        "private-claim"
    )

    serialized_response = json.dumps(
        response
    )

    serialized_log = json.dumps(
        logged_responses
    )

    assert response["status"] == "error"
    assert (
        response["error"]["type"]
        == INTERNAL_ERROR
    )
    assert response["error"]["retryable"] is True

    assert secret not in serialized_response
    assert secret not in serialized_log
    assert "sk-proj-secret" not in serialized_response
    assert "sk-proj-secret" not in serialized_log


def test_service_unavailable_returns_503(
    monkeypatch,
) -> None:
    """Unavailable verifier state should use HTTP 503."""

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        lambda claim: error_response(
            error_type=SERVICE_UNAVAILABLE_ERROR,
            message=(
                "Service is temporarily unavailable."
            ),
            retryable=True,
        ),
    )

    client = build_test_client()

    response = client.post(
        "/verify",
        json={"claim": "A valid test claim."},
        headers={
            "X-Request-ID": "service-unavailable-001",
        },
    )

    body = response.json()

    assert response.status_code == 503
    assert (
        body["error"]["type"]
        == SERVICE_UNAVAILABLE_ERROR
    )
    assert body["error"]["retryable"] is True
    assert (
        body["request_id"]
        == "service-unavailable-001"
    )
    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_invalid_claim_returns_400(
    monkeypatch,
) -> None:
    """Domain-level claim validation should use HTTP 400."""

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        lambda claim: error_response(
            error_type=INVALID_CLAIM_ERROR,
            message="Claim cannot be empty.",
            retryable=False,
        ),
    )

    client = build_test_client()

    response = client.post(
        "/verify",
        json={"claim": "   "},
    )

    body = response.json()

    assert response.status_code == 400
    assert (
        body["error"]["type"]
        == INVALID_CLAIM_ERROR
    )
    assert body["error"]["retryable"] is False
    assert REQUEST_ID_PATTERN.fullmatch(
        body["request_id"]
    )


def test_request_validation_returns_safe_422() -> None:
    """Pydantic errors must not echo submitted values."""

    client = build_test_client()

    secret = "private-invalid-claim-value"

    response = client.post(
        "/verify",
        json={
            "claim": {
                "secret": secret,
            }
        },
    )

    body = response.json()
    serialized = response.text

    assert response.status_code == 422
    assert (
        body["error"]["type"]
        == "invalid_request"
    )
    assert body["error"]["retryable"] is False
    assert secret not in serialized
    assert "input" not in body["error"]
    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_unhandled_route_exception_returns_safe_500(
    monkeypatch,
    caplog,
) -> None:
    """Unexpected route exceptions must hide their messages."""

    secret = (
        "sensitive-route-error "
        "hf_private_token "
        "sk-proj-secret"
    )

    def raise_secret_error(claim: str):
        del claim
        raise RuntimeError(secret)

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        raise_secret_error,
    )

    if caplog.handler not in REQUEST_LOGGER.handlers:
        REQUEST_LOGGER.addHandler(
            caplog.handler
        )

    try:
        client = build_test_client()

        response = client.post(
            "/verify",
            json={"claim": "A valid test claim."},
        )
    finally:
        if caplog.handler in REQUEST_LOGGER.handlers:
            REQUEST_LOGGER.removeHandler(
                caplog.handler
            )

    body = response.json()

    assert response.status_code == 500
    assert (
        body["error"]["type"]
        == INTERNAL_ERROR
    )
    assert body["error"]["retryable"] is True

    assert secret not in response.text
    assert "hf_private_token" not in response.text
    assert "sk-proj-secret" not in response.text

    logs = "\n".join(
        record.getMessage()
        for record in caplog.records
    )

    assert secret not in logs
    assert "hf_private_token" not in logs
    assert "sk-proj-secret" not in logs


def test_unknown_path_returns_unified_404() -> None:
    """Unknown paths should use the shared error contract."""

    client = build_test_client()

    response = client.get(
        "/does-not-exist-private-value"
    )

    body = response.json()

    assert response.status_code == 404
    assert body["status"] == "error"
    assert body["error"]["type"] == "not_found"
    assert body["error"]["retryable"] is False
    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_success_response_contains_request_id(
    monkeypatch,
) -> None:
    """Successful verification should also be traceable."""

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        lambda claim: {
            "status": "success",
            "data": {
                "verification": {
                    "label": "Supported",
                    "confidence": 0.9,
                    "verifier_type": "rule",
                }
            },
            "metadata": {
                "active_verifier_mode": "rule",
            },
        },
    )

    client = build_test_client()

    response = client.post(
        "/verify",
        json={"claim": "A valid test claim."},
        headers={
            "X-Request-ID": "successful-request-001",
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert (
        body["request_id"]
        == "successful-request-001"
    )
    assert (
        response.headers["x-request-id"]
        == body["request_id"]
    )


def test_validation_error_metric_is_recorded() -> None:
    """422 verification errors should update aggregate metrics."""

    before = metric_value(
        "evidence_verification_errors_total",
        error_type="invalid_request",
    )

    client = build_test_client()

    response = client.post(
        "/verify",
        json={"claim": ["invalid"]},
    )

    after = metric_value(
        "evidence_verification_errors_total",
        error_type="invalid_request",
    )

    assert response.status_code == 422
    assert after - before == 1.0
