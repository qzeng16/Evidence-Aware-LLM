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
from app.llm_clients.openai_responses import (
    OPENAI_PROVIDER,
    OPENAI_RESPONSE_FORMAT_NAME,
    OpenAIResponsesClient,
)


__all__ = [
    "INVALID_REQUEST_ERROR",
    "INVALID_RESPONSE_ERROR",
    "PROVIDER_REQUEST_ERROR",
    "RATE_LIMIT_ERROR",
    "REQUEST_TIMEOUT_ERROR",
    "FAKE_RESPONSE_EXHAUSTED_ERROR",
    "OPENAI_PROVIDER",
    "OPENAI_RESPONSE_FORMAT_NAME",
    "LLMClient",
    "LLMClientError",
    "LLMClientResponse",
    "FakeLLMClient",
    "FakeLLMClientCall",
    "OpenAIResponsesClient",
]
