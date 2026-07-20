"""FastAPI route definitions."""

from typing import Any, Dict

from fastapi import APIRouter

from app.schemas import VerifyRequest, VerifyResponse
from app.services import (
    get_service_status,
    verify_claim_service,
)


router = APIRouter()


@router.get("/")
def root() -> Dict[str, str]:
    """Return basic API navigation information."""

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
