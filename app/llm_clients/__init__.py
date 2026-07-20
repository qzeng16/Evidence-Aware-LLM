"""Provider-independent LLM client interfaces."""

from app.llm_clients.base import (
    INVALID_REQUEST_ERROR,
    INVALID_RESPONSE_ERROR,
    PROVIDER_REQUEST_ERROR,
    RATE_LIMIT_ERROR,
    REQUEST_TIMEOUT_ERROR,
    LLMClient,
    LLMClientError,
    LLMClientResponse,
)
from app.llm_clients.fake import (
    FAKE_RESPONSE_EXHAUSTED_ERROR,
    FakeLLMClient,
    FakeLLMClientCall,
)


__all__ = [
    "INVALID_REQUEST_ERROR",
    "INVALID_RESPONSE_ERROR",
    "PROVIDER_REQUEST_ERROR",
    "RATE_LIMIT_ERROR",
    "REQUEST_TIMEOUT_ERROR",
    "FAKE_RESPONSE_EXHAUSTED_ERROR",
    "LLMClient",
    "LLMClientError",
    "LLMClientResponse",
    "FakeLLMClient",
    "FakeLLMClientCall",
]
