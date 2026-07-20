"""Deterministic fake LLM client for tests and local development."""

from collections import deque
from dataclasses import dataclass
from typing import (
    Any,
    Deque,
    Dict,
    Mapping,
    Sequence,
    Tuple,
    Union,
)

from app.llm_clients.base import (
    INVALID_REQUEST_ERROR,
    INVALID_RESPONSE_ERROR,
    LLMClientError,
    LLMClientResponse,
    normalize_messages,
    normalize_response_schema,
)


FAKE_RESPONSE_EXHAUSTED_ERROR = (
    "fake_response_exhausted"
)

FakeResponseItem = Union[
    str,
    LLMClientResponse,
    LLMClientError,
]


@dataclass(frozen=True)
class FakeLLMClientCall:
    """One normalized request received by FakeLLMClient."""

    messages: Tuple[Dict[str, str], ...]
    response_schema: Dict[str, Any]


class FakeLLMClient:
    """Return queued responses without making network requests."""

    def __init__(
        self,
        responses: Sequence[FakeResponseItem],
        provider: str = "fake",
        model: str = "fake-structured-model",
    ) -> None:
        """Create a client with deterministic queued responses."""

        normalized_provider = str(provider).strip()
        normalized_model = str(model).strip()

        if not normalized_provider:
            raise LLMClientError(
                "Fake provider cannot be empty.",
                error_code=INVALID_REQUEST_ERROR,
            )

        if not normalized_model:
            raise LLMClientError(
                "Fake model cannot be empty.",
                error_code=INVALID_REQUEST_ERROR,
            )

        self.provider = normalized_provider
        self.model = normalized_model

        self._responses: Deque[
            FakeResponseItem
        ] = deque(responses)

        self._calls = []

    @property
    def calls(
        self,
    ) -> Tuple[FakeLLMClientCall, ...]:
        """Return recorded calls without exposing the mutable list."""

        return tuple(self._calls)

    @property
    def remaining_responses(self) -> int:
        """Return the number of queued response items."""

        return len(self._responses)

    def generate(
        self,
        messages: Sequence[
            Mapping[str, str]
        ],
        response_schema: Mapping[str, Any],
    ) -> LLMClientResponse:
        """Validate a request and return the next queued response."""

        normalized_messages = normalize_messages(
            messages
        )

        normalized_schema = (
            normalize_response_schema(
                response_schema
            )
        )

        self._calls.append(
            FakeLLMClientCall(
                messages=normalized_messages,
                response_schema=normalized_schema,
            )
        )

        if not self._responses:
            raise LLMClientError(
                "Fake LLM client has no queued responses.",
                error_code=(
                    FAKE_RESPONSE_EXHAUSTED_ERROR
                ),
                retryable=False,
            )

        queued_item = self._responses.popleft()

        if isinstance(
            queued_item,
            LLMClientError,
        ):
            raise queued_item

        if isinstance(
            queued_item,
            LLMClientResponse,
        ):
            return queued_item

        if isinstance(queued_item, str):
            request_number = len(self._calls)

            return LLMClientResponse(
                text=queued_item,
                provider=self.provider,
                model=self.model,
                request_id=(
                    f"fake-request-"
                    f"{request_number:04d}"
                ),
                metadata={
                    "fake": True,
                },
            )

        raise LLMClientError(
            "Fake LLM client received an unsupported "
            "queued response type.",
            error_code=INVALID_RESPONSE_ERROR,
            retryable=False,
        )
