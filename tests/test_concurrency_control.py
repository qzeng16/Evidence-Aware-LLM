"""Tests for verification concurrency protection."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client.parser import (
    text_string_to_metric_families,
)

import app.routes as routes
from app.concurrency import (
    VerificationConcurrencyController,
    VerificationOverloadedError,
)
from app.config import (
    ConfigurationError,
    load_app_config,
)
from app.error_contract import (
    SERVICE_OVERLOADED_ERROR,
    http_status_for_error,
)
from app.exception_handlers import (
    register_exception_handlers,
)
from app.metrics import render_metrics
from app.observability import (
    RequestLoggingMiddleware,
)


def metric_value(name):
    """Read one unlabelled Prometheus metric value."""

    payload, _ = render_metrics()

    text = payload.decode("utf-8")

    for family in text_string_to_metric_families(
        text
    ):
        for sample in family.samples:
            if (
                sample.name == name
                and not sample.labels
            ):
                return float(sample.value)

    return 0.0


def build_test_client():
    """Build a lightweight application without startup loading."""

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


def successful_response():
    """Return one valid service response."""

    return {
        "status": "success",
        "data": {
            "verification": {
                "label": "Supported",
                "confidence": 0.9,
                "verifier_type": "rule",
            }
        },
        "metadata": {
            "verifier_mode": "rule_only",
            "active_verifier_mode": "rule",
        },
        "error": None,
    }


def test_controller_tracks_in_flight_requests():
    before = metric_value(
        "evidence_verification_in_flight"
    )

    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.05,
    )

    with controller.slot():
        during = metric_value(
            "evidence_verification_in_flight"
        )

        assert during - before == 1.0

    after = metric_value(
        "evidence_verification_in_flight"
    )

    assert after == before


def test_controller_rejects_when_capacity_is_exhausted():
    rejected_before = metric_value(
        "evidence_verification_rejected_total"
    )

    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.01,
    )

    with controller.slot():
        with pytest.raises(
            VerificationOverloadedError
        ):
            with controller.slot():
                pass

    rejected_after = metric_value(
        "evidence_verification_rejected_total"
    )

    assert rejected_after - rejected_before == 1.0


def test_configuration_loads_concurrency_limits():
    config = load_app_config(
        {
            "MAX_CONCURRENT_VERIFICATIONS": "7",
            (
                "VERIFICATION_QUEUE_"
                "TIMEOUT_SECONDS"
            ): "0.25",
        }
    )

    assert config.max_concurrent_verifications == 7

    assert (
        config.verification_queue_timeout_seconds
        == 0.25
    )


def test_configuration_rejects_invalid_concurrency():
    with pytest.raises(
        ConfigurationError,
        match="greater than zero",
    ):
        load_app_config(
            {
                "MAX_CONCURRENT_VERIFICATIONS": "0",
            }
        )


def test_overload_error_maps_to_429():
    response = {
        "status": "error",
        "error": {
            "type": SERVICE_OVERLOADED_ERROR,
            "retryable": True,
        },
    }

    assert http_status_for_error(response) == 429


def test_overloaded_route_returns_safe_429(
    monkeypatch,
):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.05,
    )

    def blocking_verify(claim):
        calls.append(claim)
        entered.set()

        assert release.wait(timeout=2.0)

        return successful_response()

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        blocking_verify,
    )

    monkeypatch.setattr(
        routes,
        "get_verification_concurrency_controller",
        lambda: controller,
    )

    monkeypatch.setattr(
        routes,
        "build_readiness_response",
        lambda request_id: (
            200,
            {
                "status": "ready",
                "request_id": request_id,
                "data": {
                    "ready": True,
                },
                "metadata": {},
                "error": None,
            },
        ),
    )

    client = build_test_client()

    with ThreadPoolExecutor(
        max_workers=1
    ) as executor:
        first_future = executor.submit(
            client.post,
            "/verify",
            json={
                "claim": "First valid claim.",
            },
            headers={
                "X-Request-ID": "first-request",
            },
        )

        assert entered.wait(timeout=1.0)

        overloaded = client.post(
            "/verify",
            json={
                "claim": "Second valid claim.",
            },
            headers={
                "X-Request-ID": "second-request",
            },
        )

        live = client.get("/live")
        ready = client.get("/ready")

        release.set()

        first = first_future.result(
            timeout=2.0
        )

    body = overloaded.json()

    assert first.status_code == 200
    assert overloaded.status_code == 429
    assert live.status_code == 200
    assert ready.status_code == 200

    assert body["status"] == "error"

    assert (
        body["error"]["type"]
        == SERVICE_OVERLOADED_ERROR
    )

    assert (
        body["error"]["code"]
        == SERVICE_OVERLOADED_ERROR
    )

    assert body["error"]["retryable"] is True

    assert (
        body["request_id"]
        == "second-request"
    )

    assert (
        overloaded.headers["x-request-id"]
        == "second-request"
    )

    assert (
        overloaded.headers["retry-after"]
        == "1"
    )

    assert calls == [
        "First valid claim.",
    ]


def test_available_capacity_allows_sequential_requests(
    monkeypatch,
):
    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.05,
    )

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        lambda claim: successful_response(),
    )

    monkeypatch.setattr(
        routes,
        "get_verification_concurrency_controller",
        lambda: controller,
    )

    client = build_test_client()

    first = client.post(
        "/verify",
        json={
            "claim": "First valid claim.",
        },
    )

    second = client.post(
        "/verify",
        json={
            "claim": "Second valid claim.",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200


def test_saturation_metrics_are_exposed():
    output = render_metrics()[0].decode(
        "utf-8"
    )

    assert (
        "evidence_verification_in_flight"
        in output
    )

    assert (
        "evidence_verification_rejected_total"
        in output
    )

    assert (
        "evidence_verification_queue_wait_seconds"
        in output
    )
