"""FastAPI route definitions."""

from typing import Any, Dict, Union

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    Response,
)

from app.error_contract import (
    attach_request_id,
    http_status_for_error,
)
from app.health import (
    build_liveness_response,
    build_readiness_response,
    get_public_health_status,
)
from app.metrics import (
    record_verification_response,
    render_metrics,
)
from app.observability import (
    get_scope_request_id,
    normalize_request_id,
)
from app.schemas import VerifyRequest, VerifyResponse
from app.services import verify_claim_service
from app.web import DEMO_HTML


router = APIRouter()


def _request_id(
    request: Request,
) -> str:
    """Return the request correlation ID."""

    return (
        get_scope_request_id(request.scope)
        or normalize_request_id(None)
    )


@router.get("/", response_model=None)
def root(
    request: Request,
) -> Union[HTMLResponse, Dict[str, str]]:
    """Serve the browser demo while preserving JSON navigation."""

    accept_header = request.headers.get(
        "accept",
        "",
    ).lower()

    if "text/html" in accept_header:
        return HTMLResponse(
            content=DEMO_HTML,
            status_code=200,
        )

    return {
        "message": (
            "Evidence-Aware Claim Verification API "
            "is running."
        ),
        "docs": "/docs",
        "health_endpoint": "/health",
        "liveness_endpoint": "/live",
        "readiness_endpoint": "/ready",
        "metrics_endpoint": "/metrics",
        "verify_endpoint": "/verify",
    }


@router.get("/live")
def liveness_check(
    request: Request,
) -> Dict[str, Any]:
    """Report whether the API process is alive."""

    return build_liveness_response(
        _request_id(request)
    )


@router.get(
    "/ready",
    response_model=None,
    responses={
        503: {
            "description": (
                "Verification service is not ready."
            ),
        },
    },
)
def readiness_check(
    request: Request,
) -> Union[JSONResponse, Dict[str, Any]]:
    """Report whether the verifier can accept requests."""

    status_code, response = (
        build_readiness_response(
            _request_id(request)
        )
    )

    if status_code != 200:
        return JSONResponse(
            status_code=status_code,
            content=response,
        )

    return response


@router.get("/health")
def health_check() -> Dict[str, Any]:
    """Return safe service and verifier metadata."""

    return get_public_health_status()


@router.get(
    "/metrics",
    include_in_schema=False,
)
def metrics_endpoint() -> Response:
    """Expose aggregate Prometheus application metrics."""

    payload, content_type = render_metrics()

    return Response(
        content=payload,
        headers={
            "Content-Type": content_type,
        },
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    responses={
        400: {"model": VerifyResponse},
        422: {"model": VerifyResponse},
        500: {"model": VerifyResponse},
        502: {"model": VerifyResponse},
        503: {"model": VerifyResponse},
    },
)
def verify_claim(
    payload: VerifyRequest,
    request: Request,
) -> Union[JSONResponse, Dict[str, Any]]:
    """Verify one claim using the active service mode."""

    response = verify_claim_service(
        payload.claim
    )

    request_id = _request_id(request)

    attach_request_id(
        response,
        request_id,
    )

    record_verification_response(
        response
    )

    if response.get("status") == "error":
        return JSONResponse(
            status_code=http_status_for_error(
                response
            ),
            content=response,
        )

    return response
