"""Provider-independent interface for structured LLM generation."""

from copy import deepcopy
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)


INVALID_REQUEST_ERROR = "invalid_request"
INVALID_RESPONSE_ERROR = "invalid_response"
REQUEST_TIMEOUT_ERROR = "request_timeout"
RATE_LIMIT_ERROR = "rate_limit"
PROVIDER_REQUEST_ERROR = "provider_request_error"

ALLOWED_MESSAGE_ROLES = {
    "system",
    "user",
    "assistant",
}


class LLMClientError(RuntimeError):
    """Raised when an LLM client request fails."""

    def __init__(
        self,
        message: str,
        error_code: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)

        self.error_code = error_code
        self.retryable = retryable


def normalize_messages(
    messages: Sequence[Mapping[str, str]],
) -> Tuple[Dict[str, str], ...]:
    """Validate provider-independent chat messages."""

    if isinstance(messages, (str, bytes)):
        raise LLMClientError(
            "messages must be a sequence of message objects.",
            error_code=INVALID_REQUEST_ERROR,
        )

    try:
        raw_messages = list(messages)
    except TypeError as error:
        raise LLMClientError(
            "messages must be a sequence.",
            error_code=INVALID_REQUEST_ERROR,
        ) from error

    if not raw_messages:
        raise LLMClientError(
            "At least one message is required.",
            error_code=INVALID_REQUEST_ERROR,
        )

    normalized_messages = []

    for index, message in enumerate(raw_messages):
        if not isinstance(message, Mapping):
            raise LLMClientError(
                f"Message {index} must be an object.",
                error_code=INVALID_REQUEST_ERROR,
            )

        expected_fields = {
            "role",
            "content",
        }

        missing_fields = expected_fields - set(message)

        if missing_fields:
            raise LLMClientError(
                f"Message {index} is missing fields: "
                f"{sorted(missing_fields)}",
                error_code=INVALID_REQUEST_ERROR,
            )

        unexpected_fields = set(message) - expected_fields

        if unexpected_fields:
            raise LLMClientError(
                f"Message {index} contains unexpected fields: "
                f"{sorted(unexpected_fields)}",
                error_code=INVALID_REQUEST_ERROR,
            )

        role = str(message["role"]).strip().lower()
        content = str(message["content"]).strip()

        if role not in ALLOWED_MESSAGE_ROLES:
            raise LLMClientError(
                f"Message {index} has unsupported role '{role}'.",
                error_code=INVALID_REQUEST_ERROR,
            )

        if not content:
            raise LLMClientError(
                f"Message {index} content cannot be empty.",
                error_code=INVALID_REQUEST_ERROR,
            )

        normalized_messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    return tuple(normalized_messages)


def normalize_response_schema(
    response_schema: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate and copy a structured-output JSON schema."""

    if not isinstance(response_schema, Mapping):
        raise LLMClientError(
            "response_schema must be an object.",
            error_code=INVALID_REQUEST_ERROR,
        )

    normalized_schema = deepcopy(dict(response_schema))

    if not normalized_schema:
        raise LLMClientError(
            "response_schema cannot be empty.",
            error_code=INVALID_REQUEST_ERROR,
        )

    if normalized_schema.get("type") != "object":
        raise LLMClientError(
            "response_schema must define a top-level object.",
            error_code=INVALID_REQUEST_ERROR,
        )

    return normalized_schema


def _normalize_optional_number(
    value: Optional[float],
    field_name: str,
) -> Optional[float]:
    """Validate an optional nonnegative number."""

    if value is None:
        return None

    try:
        normalized_value = float(value)
    except (TypeError, ValueError) as error:
        raise LLMClientError(
            f"{field_name} must be a number.",
            error_code=INVALID_RESPONSE_ERROR,
        ) from error

    if normalized_value < 0:
        raise LLMClientError(
            f"{field_name} cannot be negative.",
            error_code=INVALID_RESPONSE_ERROR,
        )

    return normalized_value


def _normalize_optional_token_count(
    value: Optional[int],
    field_name: str,
) -> Optional[int]:
    """Validate an optional nonnegative token count."""

    if value is None:
        return None

    if isinstance(value, bool):
        raise LLMClientError(
            f"{field_name} must be an integer.",
            error_code=INVALID_RESPONSE_ERROR,
        )

    try:
        normalized_value = int(value)
    except (TypeError, ValueError) as error:
        raise LLMClientError(
            f"{field_name} must be an integer.",
            error_code=INVALID_RESPONSE_ERROR,
        ) from error

    if normalized_value < 0:
        raise LLMClientError(
            f"{field_name} cannot be negative.",
            error_code=INVALID_RESPONSE_ERROR,
        )

    return normalized_value


@dataclass(frozen=True)
class LLMClientResponse:
    """Provider-independent response returned by an LLM client."""

    text: str
    provider: str
    model: str
    request_id: Optional[str] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    metadata: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        """Normalize and validate response fields."""

        normalized_text = str(self.text).strip()
        normalized_provider = str(self.provider).strip()
        normalized_model = str(self.model).strip()

        if not normalized_text:
            raise LLMClientError(
                "LLM response text cannot be empty.",
                error_code=INVALID_RESPONSE_ERROR,
            )

        if not normalized_provider:
            raise LLMClientError(
                "LLM response provider cannot be empty.",
                error_code=INVALID_RESPONSE_ERROR,
            )

        if not normalized_model:
            raise LLMClientError(
                "LLM response model cannot be empty.",
                error_code=INVALID_RESPONSE_ERROR,
            )

        normalized_request_id = None

        if self.request_id is not None:
            normalized_request_id = str(
                self.request_id
            ).strip() or None

        normalized_latency = _normalize_optional_number(
            self.latency_ms,
            "latency_ms",
        )

        normalized_input_tokens = (
            _normalize_optional_token_count(
                self.input_tokens,
                "input_tokens",
            )
        )

        normalized_output_tokens = (
            _normalize_optional_token_count(
                self.output_tokens,
                "output_tokens",
            )
        )

        if self.metadata is None:
            normalized_metadata = {}
        elif isinstance(self.metadata, Mapping):
            normalized_metadata = dict(self.metadata)
        else:
            raise LLMClientError(
                "LLM response metadata must be an object.",
                error_code=INVALID_RESPONSE_ERROR,
            )

        object.__setattr__(self, "text", normalized_text)
        object.__setattr__(
            self,
            "provider",
            normalized_provider,
        )
        object.__setattr__(
            self,
            "model",
            normalized_model,
        )
        object.__setattr__(
            self,
            "request_id",
            normalized_request_id,
        )
        object.__setattr__(
            self,
            "latency_ms",
            normalized_latency,
        )
        object.__setattr__(
            self,
            "input_tokens",
            normalized_input_tokens,
        )
        object.__setattr__(
            self,
            "output_tokens",
            normalized_output_tokens,
        )
        object.__setattr__(
            self,
            "metadata",
            normalized_metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the response into a dictionary."""

        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "metadata": dict(self.metadata or {}),
        }


@runtime_checkable
class LLMClient(Protocol):
    """Interface implemented by all LLM providers."""

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        response_schema: Mapping[str, Any],
    ) -> LLMClientResponse:
        """Generate one structured LLM response."""

        ...
