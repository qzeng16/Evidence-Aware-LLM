from typing import Dict

from fastapi import APIRouter

from app.schemas import VerifyRequest, VerifyResponse
from app.services import is_service_ready, verify_claim_service


router = APIRouter()


@router.get("/")
def root() -> Dict:
    return {
        "message": "Evidence-Aware Claim Verification API is running.",
        "docs": "/docs",
        "verify_endpoint": "/verify"
    }


@router.get("/health")
def health_check() -> Dict:
    return {
        "status": "ready" if is_service_ready() else "loading_or_unavailable"
    }


@router.post("/verify", response_model=VerifyResponse)
def verify_claim(request: VerifyRequest) -> Dict:
    return verify_claim_service(request.claim)
