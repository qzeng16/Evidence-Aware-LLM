"""Deterministic application for graceful-shutdown validation."""

import time
from typing import Any, Dict

from fastapi import FastAPI

import app.lifecycle as lifecycle
import app.routes as routes
from app.concurrency import (
    configure_verification_concurrency,
)
from app.config import AppConfig
from app.exception_handlers import (
    register_exception_handlers,
)
from app.execution import (
    configure_verification_execution,
)
from app.observability import (
    RequestLoggingMiddleware,
)
from app.request_limits import (
    RequestBoundaryMiddleware,
)
from app.security_headers import (
    SecurityHeadersMiddleware,
)


PRIVATE_SLOW_CLAIM = (
    "layer94-private-slow-claim-"
    "sk-proj-secret"
)

TEST_CONFIG = AppConfig(
    max_concurrent_verifications=1,
    verification_queue_timeout_seconds=0.01,
    verification_timeout_seconds=0.05,
    graceful_shutdown_timeout_seconds=5.0,
)


def fake_verify_claim_service(
    claim: str,
) -> Dict[str, Any]:
    """Simulate work that continues after the HTTP timeout."""

    if claim == PRIVATE_SLOW_CLAIM:
        print(
            "LAYER94_BACKGROUND_STARTED",
            flush=True,
        )

        time.sleep(2.0)

        print(
            "LAYER94_BACKGROUND_COMPLETED",
            flush=True,
        )

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


def ready_response(
    request_id: str,
):
    """Return deterministic readiness metadata."""

    return (
        200,
        {
            "status": "ready",
            "request_id": request_id,
            "data": {
                "ready": True,
            },
            "metadata": {
                "status": "ready",
                "verifier_mode": "rule_only",
                "active_verifier_mode": "rule",
                "llm_verifier_available": False,
                "llm_provider": None,
                "llm_model": None,
                "openai_api_key_configured": False,
                "ready": True,
            },
            "error": None,
        },
    )


def fake_initialize_service() -> None:
    """Configure deterministic runtime resources."""

    configure_verification_concurrency(
        max_concurrent=(
            TEST_CONFIG.max_concurrent_verifications
        ),
        queue_timeout_seconds=(
            TEST_CONFIG
            .verification_queue_timeout_seconds
        ),
    )

    configure_verification_execution(
        max_workers=(
            TEST_CONFIG.max_concurrent_verifications
        ),
        timeout_seconds=(
            TEST_CONFIG.verification_timeout_seconds
        ),
    )

    routes.verify_claim_service = (
        fake_verify_claim_service
    )

    routes.build_readiness_response = (
        ready_response
    )

    print(
        "LAYER94_RUNTIME_INITIALIZED",
        flush=True,
    )


def fake_get_app_config() -> AppConfig:
    """Return the deterministic lifecycle configuration."""

    return TEST_CONFIG


def fake_reset_service_state() -> None:
    """Record that cleanup occurred after work drained."""

    print(
        "LAYER94_SERVICE_STATE_RESET",
        flush=True,
    )


lifecycle.initialize_service = (
    fake_initialize_service
)

lifecycle.get_app_config = (
    fake_get_app_config
)

lifecycle.reset_service_state = (
    fake_reset_service_state
)


app = FastAPI(
    title="Graceful Shutdown Integration Test",
    lifespan=lifecycle.application_lifespan,
)

app.add_middleware(
    RequestBoundaryMiddleware,
    max_request_body_bytes=4096,
)

app.add_middleware(
    RequestLoggingMiddleware
)

app.add_middleware(
    SecurityHeadersMiddleware
)

register_exception_handlers(app)

app.include_router(
    routes.router
)
