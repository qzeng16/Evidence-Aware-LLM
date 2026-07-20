"""Safe and consistent FastAPI exception handlers."""

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.error_contract import (
    HTTP_ERROR,
    INTERNAL_ERROR,
    INVALID_REQUEST_ERROR,
    METHOD_NOT_ALLOWED_ERROR,
    NOT_FOUND_ERROR,
    build_api_error_response,
)
from app.metrics import record_verification_response
from app.observability import (
    REQUEST_ID_HEADER,
    emit_request_event,
    get_scope_request_id,
    normalize_request_id,
)
from app.services import (
    get_active_verifier_mode,
    get_configured_verifier_mode,
    is_llm_verifier_available,
)


def _request_id(request: Request) -> str:
    """Return the middleware request ID or create a fallback."""

    return (
        get_scope_request_id(request.scope)
        or normalize_request_id(None)
    )


def _safe_metadata() -> Dict[str, Any]:
    """Return non-secret execution metadata."""

    return {
        "verifier_mode": (
            get_configured_verifier_mode()
        ),
        "active_verifier_mode": (
            get_active_verifier_mode()
        ),
        "llm_verifier_available": (
            is_llm_verifier_available()
        ),
    }


def _record_verify_error(
    request: Request,
    response: Dict[str, Any],
) -> None:
    """Record verification errors without user input."""

    if request.url.path == "/verify":
        record_verification_response(
            response
        )


def _log_error_response(
    *,
    request: Request,
    request_id: str,
    status_code: int,
    error_type: str,
    exception_type: Optional[str] = None,
) -> None:
    """Emit an error event without exception messages."""

    fields: Dict[str, Any] = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "error_type": error_type,
        "active_verifier_mode": (
            get_active_verifier_mode()
        ),
    }

    if exception_type is not None:
        fields["exception_type"] = (
            exception_type
        )

    emit_request_event(
        "application_error_response",
        **fields,
    )


def _json_error_response(
    *,
    request: Request,
    status_code: int,
    error_type: str,
    message: str,
    retryable: bool,
    exception_type: Optional[str] = None,
) -> JSONResponse:
    """Create, record and return one safe error response."""

    request_id = _request_id(request)

    response = build_api_error_response(
        error_type=error_type,
        message=message,
        retryable=retryable,
        request_id=request_id,
        metadata=_safe_metadata(),
    )

    _record_verify_error(
        request,
        response,
    )

    _log_error_response(
        request=request,
        request_id=request_id,
        status_code=status_code,
        error_type=error_type,
        exception_type=exception_type,
    )

    return JSONResponse(
        status_code=status_code,
        content=response,
        headers={
            REQUEST_ID_HEADER: request_id,
        },
    )


async def request_validation_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Return a generic 422 response without submitted values."""

    del error

    return _json_error_response(
        request=request,
        status_code=422,
        error_type=INVALID_REQUEST_ERROR,
        message=(
            "The request body or parameters "
            "are invalid."
        ),
        retryable=False,
        exception_type=(
            "RequestValidationError"
        ),
    )


async def http_exception_handler(
    request: Request,
    error: StarletteHTTPException,
) -> JSONResponse:
    """Normalize framework-generated HTTP errors."""

    if error.status_code == 404:
        error_type = NOT_FOUND_ERROR
        message = "The requested resource was not found."
    elif error.status_code == 405:
        error_type = METHOD_NOT_ALLOWED_ERROR
        message = (
            "The requested HTTP method is not allowed."
        )
    else:
        error_type = HTTP_ERROR
        message = "The HTTP request could not be completed."

    return _json_error_response(
        request=request,
        status_code=error.status_code,
        error_type=error_type,
        message=message,
        retryable=False,
        exception_type=type(error).__name__,
    )


async def unhandled_exception_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Hide implementation details for unexpected failures."""

    return _json_error_response(
        request=request,
        status_code=500,
        error_type=INTERNAL_ERROR,
        message=(
            "An unexpected internal error occurred."
        ),
        retryable=True,
        exception_type=type(error).__name__,
    )


def register_exception_handlers(
    app: FastAPI,
) -> None:
    """Register the complete application error contract."""

    app.add_exception_handler(
        RequestValidationError,
        request_validation_handler,
    )

    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )

    app.add_exception_handler(
        Exception,
        unhandled_exception_handler,
    )
