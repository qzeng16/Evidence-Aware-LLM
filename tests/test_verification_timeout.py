"""Tests for verification execution timeouts."""

import time
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client.parser import (
    text_string_to_metric_families,
)

import app.routes as routes
from app.concurrency import (
    VerificationConcurrencyController,
)
from app.config import (
    ConfigurationError,
    load_app_config,
)
from app.error_contract import (
    VERIFICATION_TIMEOUT_ERROR,
    http_status_for_error,
)
from app.exception_handlers import (
    register_exception_handlers,
)
from app.execution import (
    VerificationExecutionManager,
)
from app.metrics import render_metrics
from app.observability import (
    RequestLoggingMiddleware,
)


def metric_value(name):
    """Read one unlabelled Prometheus metric sample."""

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


def build_client():
    """Build a lightweight application."""

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


def test_configuration_loads_timeout():
    config = load_app_config(
        {
            "VERIFICATION_TIMEOUT_SECONDS": "2.5",
        }
    )

    assert (
        config.verification_timeout_seconds
        == 2.5
    )


def test_configuration_rejects_invalid_timeout():
    with pytest.raises(
        ConfigurationError,
        match="greater than zero",
    ):
        load_app_config(
            {
                "VERIFICATION_TIMEOUT_SECONDS": "0",
            }
        )


def test_timeout_error_maps_to_504():
    response = {
        "status": "error",
        "error": {
            "type": VERIFICATION_TIMEOUT_ERROR,
            "retryable": True,
        },
    }

    assert http_status_for_error(response) == 504


def test_fast_execution_returns_and_releases_slot():
    in_flight_before = metric_value(
        "evidence_verification_in_flight"
    )

    duration_before = metric_value(
        (
            "evidence_verification_"
            "execution_duration_seconds_count"
        )
    )

    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.05,
    )

    manager = VerificationExecutionManager(
        max_workers=1,
        timeout_seconds=1.0,
    )

    lease = controller.acquire()

    result = manager.execute(
        lambda: "complete",
        lease=lease,
    )

    manager.shutdown()

    assert result == "complete"

    assert (
        metric_value(
            "evidence_verification_in_flight"
        )
        == in_flight_before
    )

    assert (
        metric_value(
            (
                "evidence_verification_"
                "execution_duration_seconds_count"
            )
        )
        - duration_before
        == 1.0
    )


def test_timed_out_task_retains_slot_until_completion(
    monkeypatch,
):
    started = threading.Event()
    release = threading.Event()

    controller = VerificationConcurrencyController(
        max_concurrent=1,
        queue_timeout_seconds=0.01,
    )

    manager = VerificationExecutionManager(
        max_workers=1,
        timeout_seconds=0.05,
    )

    in_flight_before = metric_value(
        "evidence_verification_in_flight"
    )

    timeout_before = metric_value(
        "evidence_verification_timeouts_total"
    )

    def verify(claim):
        if claim == "Slow verification claim.":
            started.set()

            assert release.wait(
                timeout=2.0
            )

        return successful_response()

    monkeypatch.setattr(
        routes,
        "verify_claim_service",
        verify,
    )

    monkeypatch.setattr(
        routes,
        "get_verification_concurrency_controller",
        lambda: controller,
    )

    monkeypatch.setattr(
        routes,
        "get_verification_execution_manager",
        lambda: manager,
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

    client = build_client()

    timed_out = client.post(
        "/verify",
        json={
            "claim": "Slow verification claim.",
        },
        headers={
            "X-Request-ID": "timeout-request-001",
        },
    )

    assert started.is_set()

    body = timed_out.json()

    assert timed_out.status_code == 504

    assert (
        body["error"]["type"]
        == VERIFICATION_TIMEOUT_ERROR
    )

    assert (
        body["error"]["code"]
        == VERIFICATION_TIMEOUT_ERROR
    )

    assert body["error"]["retryable"] is True

    assert (
        body["request_id"]
        == "timeout-request-001"
    )

    assert (
        timed_out.headers["x-request-id"]
        == body["request_id"]
    )

    assert (
        "Slow verification claim."
        not in timed_out.text
    )

    assert (
        metric_value(
            "evidence_verification_timeouts_total"
        )
        - timeout_before
        == 1.0
    )

    assert (
        metric_value(
            "evidence_verification_in_flight"
        )
        - in_flight_before
        == 1.0
    )

    overloaded = client.post(
        "/verify",
        json={
            "claim": "Second verification claim.",
        },
    )

    assert overloaded.status_code == 429

    assert client.get("/live").status_code == 200
    assert client.get("/ready").status_code == 200

    release.set()

    deadline = time.monotonic() + 2.0

    while (
        metric_value(
            "evidence_verification_in_flight"
        )
        != in_flight_before
    ):
        if time.monotonic() >= deadline:
            raise AssertionError(
                "Timed-out task did not release "
                "its slot after completion."
            )

        time.sleep(0.01)

    completed = client.post(
        "/verify",
        json={
            "claim": "Third verification claim.",
        },
    )

    manager.shutdown()

    assert completed.status_code == 200


def test_timeout_metrics_are_exposed():
    output = render_metrics()[0].decode(
        "utf-8"
    )

    assert (
        "evidence_verification_timeouts_total"
        in output
    )

    assert (
        (
            "evidence_verification_"
            "execution_duration_seconds"
        )
        in output
    )
