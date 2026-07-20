"""Safe liveness, readiness and health responses."""

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from app.error_contract import (
    SERVICE_UNAVAILABLE_ERROR,
    build_api_error_response,
)
from app.services import (
    get_service_status,
    is_service_ready,
)


PUBLIC_STATUS_FIELDS = (
    "status",
    "verifier_mode",
    "active_verifier_mode",
    "llm_verifier_available",
    "llm_provider",
    "llm_model",
    "openai_api_key_configured",
)


def utc_timestamp() -> str:
    """Return one timezone-aware UTC timestamp."""

    return datetime.now(
        timezone.utc
    ).isoformat()


def get_public_health_status() -> Dict[str, Any]:
    """Return health metadata without initialization details."""

    internal_status = get_service_status()

    public_status = {
        field: internal_status.get(field)
        for field in PUBLIC_STATUS_FIELDS
    }

    public_status["ready"] = is_service_ready()

    return public_status


def build_liveness_response(
    request_id: str,
) -> Dict[str, Any]:
    """Return a response proving that the API process is alive."""

    return {
        "status": "alive",
        "timestamp": utc_timestamp(),
        "request_id": request_id,
        "data": {
            "alive": True,
        },
        "metadata": None,
        "error": None,
    }


def build_readiness_response(
    request_id: str,
) -> Tuple[int, Dict[str, Any]]:
    """Return HTTP-ready state using the shared error contract."""

    public_status = get_public_health_status()

    if is_service_ready():
        return (
            200,
            {
                "status": "ready",
                "timestamp": utc_timestamp(),
                "request_id": request_id,
                "data": {
                    "ready": True,
                },
                "metadata": public_status,
                "error": None,
            },
        )

    response = build_api_error_response(
        error_type=SERVICE_UNAVAILABLE_ERROR,
        message="Service is not ready.",
        retryable=True,
        request_id=request_id,
        metadata=public_status,
    )

    return 503, response
