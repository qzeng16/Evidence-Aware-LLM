"""Shared API error response contract."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


INVALID_CLAIM_ERROR = "invalid_claim"
INVALID_REQUEST_ERROR = "invalid_request"
SERVICE_UNAVAILABLE_ERROR = "service_unavailable"
SERVICE_OVERLOADED_ERROR = "service_overloaded"

PAYLOAD_TOO_LARGE_ERROR = "payload_too_large"

UNSUPPORTED_MEDIA_TYPE_ERROR = (
    "unsupported_media_type"
)
PROVIDER_ERROR = "provider_error"
INTERNAL_ERROR = "internal_error"
NOT_FOUND_ERROR = "not_found"
METHOD_NOT_ALLOWED_ERROR = "method_not_allowed"
HTTP_ERROR = "http_error"
UNKNOWN_ERROR = "unknown"


def annotate_error_response(
    response: Dict[str, Any],
    *,
    error_type: str,
    retryable: bool,
    message: Optional[str] = None,
    code: Optional[str] = None,
) -> Dict[str, Any]:
    """Add stable machine-readable fields to an existing error."""

    response["status"] = "error"
    response["data"] = None

    error = response.get("error")

    if not isinstance(error, dict):
        error = {}

    if message is not None:
        error["message"] = message
    elif not isinstance(error.get("message"), str):
        error["message"] = "The request could not be completed."

    error["type"] = error_type
    error["retryable"] = bool(retryable)

    if code:
        error["code"] = code

    response["error"] = error

    return response


def build_api_error_response(
    *,
    error_type: str,
    message: str,
    retryable: bool,
    request_id: str,
    metadata: Optional[Dict[str, Any]] = None,
    code: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a complete public error response."""

    response = {
        "status": "error",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "request_id": request_id,
        "data": None,
        "metadata": dict(metadata or {}),
        "error": {
            "type": error_type,
            "message": message,
            "retryable": bool(retryable),
        },
    }

    if code:
        response["error"]["code"] = code

    return response


def attach_request_id(
    response: Dict[str, Any],
    request_id: str,
) -> Dict[str, Any]:
    """Attach one public request correlation ID."""

    response["request_id"] = request_id

    return response


def get_error_type(
    response: Dict[str, Any],
) -> str:
    """Return a normalized error type."""

    error = response.get("error")

    if not isinstance(error, dict):
        return UNKNOWN_ERROR

    error_type = error.get("type")

    if not isinstance(error_type, str):
        return UNKNOWN_ERROR

    return error_type


def is_retryable_error(
    response: Dict[str, Any],
) -> bool:
    """Return the normalized retryable flag."""

    error = response.get("error")

    return bool(
        isinstance(error, dict)
        and error.get("retryable") is True
    )


def http_status_for_error(
    response: Dict[str, Any],
) -> int:
    """Map an internal error response to an HTTP status."""

    error_type = get_error_type(response)

    if error_type in {
        INVALID_CLAIM_ERROR,
        INVALID_REQUEST_ERROR,
    }:
        return 400

    if error_type == PAYLOAD_TOO_LARGE_ERROR:
        return 413

    if error_type == UNSUPPORTED_MEDIA_TYPE_ERROR:
        return 415

    if error_type == SERVICE_OVERLOADED_ERROR:
        return 429

    if error_type == SERVICE_UNAVAILABLE_ERROR:
        return 503

    if error_type == PROVIDER_ERROR:
        return (
            503
            if is_retryable_error(response)
            else 502
        )

    if error_type == NOT_FOUND_ERROR:
        return 404

    if error_type == METHOD_NOT_ALLOWED_ERROR:
        return 405

    if error_type == INTERNAL_ERROR:
        return 500

    return 500
