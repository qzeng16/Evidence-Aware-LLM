"""Deterministic application used by the Docker timeout check."""

import time
from typing import Any, Dict

from fastapi import FastAPI

import app.routes as routes
from app.concurrency import (
    configure_verification_concurrency,
)
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


SLOW_CLAIM = (
    "layer92-private-slow-claim-"
    "sk-proj-secret"
)


def fake_verify_claim_service(
    claim: str,
) -> Dict[str, Any]:
    """Simulate one slow verification without external services."""

    if claim == SLOW_CLAIM:
        time.sleep(1.0)

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
    """Return deterministic readiness for the test application."""

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


configure_verification_concurrency(
    max_concurrent=1,
    queue_timeout_seconds=0.01,
)

configure_verification_execution(
    max_workers=1,
    timeout_seconds=0.05,
)

routes.verify_claim_service = (
    fake_verify_claim_service
)

routes.build_readiness_response = (
    ready_response
)


app = FastAPI(
    title="Verification Timeout Integration Test",
)

app.add_middleware(
    RequestBoundaryMiddleware
)

app.add_middleware(
    RequestLoggingMiddleware
)

register_exception_handlers(app)

app.include_router(
    routes.router
)
