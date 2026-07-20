"""FastAPI route definitions."""

from typing import Any, Dict, Union

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.schemas import VerifyRequest, VerifyResponse
from app.services import (
    get_service_status,
    verify_claim_service,
)
from app.web import DEMO_HTML


router = APIRouter()


@router.get("/", response_model=None)
def root(
    request: Request,
) -> Union[HTMLResponse, Dict[str, str]]:
    """Serve the browser demo while preserving JSON API navigation."""

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
        "verify_endpoint": "/verify",
    }


@router.get("/health")
def health_check() -> Dict[str, Any]:
    """Return readiness and verifier-mode information."""

    return get_service_status()


@router.post(
    "/verify",
    response_model=VerifyResponse,
)
def verify_claim(
    request: VerifyRequest,
) -> Dict[str, Any]:
    """Verify one claim using the active service mode."""

    return verify_claim_service(request.claim)
