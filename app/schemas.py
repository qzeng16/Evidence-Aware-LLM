from typing import Any, Dict, Optional

from pydantic import BaseModel


class VerifyRequest(BaseModel):
    claim: str


class VerifyResponse(BaseModel):
    status: str
    timestamp: Optional[str] = None
    request_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
