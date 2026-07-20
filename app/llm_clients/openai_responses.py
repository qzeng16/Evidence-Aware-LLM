"""OpenAI Responses API implementation of the shared LLM client."""

from time import perf_counter
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Sequence,
)

import openai

from app.llm_clients.base import (
    INVALID_REQUEST_ERROR,
    INVALID_RESPONSE_ERROR,
    PROVIDER_REQUEST_ERROR,
    RATE_LIMIT_ERROR,
    REQUEST_TIMEOUT_ERROR,
    LLMClientError,
    LLMClientResponse,
    normalize_messages,
    normalize_response_schema,
)


OPENAI_PROVIDER = "openai"
OPENAI_RESPONSE_FORMAT_NAME = "llm_judge_output"
OPENAI_STORE_RESPONSES = False
OPENAI_MAX_OUTPUT_TOKENS = 800


def _normalize_required_text(
    value: Optional[str],
    field_name: str,
) -> str:
    """Normalize one required configuration string."""

    normalized_value = str(
        value or ""
    ).strip()

    if not normalized_value:
        raise LLMClientError(
            f"{field_name} cannot be empty.",
            error_code=INVALID_REQUEST_ERROR,
            retryable=False,
        )

    return normalized_value


def _normalize_positive_float(
    value: float,
    field_name: str,
) -> float:
    """Normalize one positive numeric configuration value."""

    try:
        normalized_value = float(value)
    except (TypeError, ValueError) as error:
        raise LLMClientError(
            f"{field_name} must be a number.",
            error_code=INVALID_REQUEST_ERROR,
            retryable=False,
        ) from error

    if normalized_value <= 0:
        raise LLMClientError(
            f"{field_name} must be greater than zero.",
            error_code=INVALID_REQUEST_ERROR,
            retryable=False,
        )

    return normalized_value


def _normalize_nonnegative_integer(
    value: int,
    field_name: str,
) -> int:
    """Normalize one nonnegative integer setting."""

    if isinstance(value, bool):
        raise LLMClientError(
            f"{field_name} must be an integer.",
            error_code=INVALID_REQUEST_ERROR,
            retryable=False,
        )

    try:
        normalized_value = int(value)
    except (TypeError, ValueError) as error:
        raise LLMClientError(
            f"{field_name} must be an integer.",
            error_code=INVALID_REQUEST_ERROR,
            retryable=False,
        ) from error

    if normalized_value < 0:
        raise LLMClientError(
            f"{field_name} cannot be negative.",
            error_code=INVALID_REQUEST_ERROR,
            retryable=False,
        )

    return normalized_value


def _build_error_message(
    prefix: str,
    error: Exception,
) -> str:
    """Build an error message without exposing credentials."""

    request_id = getattr(
        error,
        "request_id",
        None,
    )

    if request_id:
        return (
            f"{prefix} "
            f"Request ID: {request_id}."
        )

    return prefix


def _extract_usage(
    response: Any,
) -> Dict[str, Optional[int]]:
    """Extract token usage from an OpenAI response."""

    usage = getattr(
        response,
        "usage",
        None,
    )

    if usage is None:
        return {
            "input_tokens": None,
            "output_tokens": None,
        }

    return {
        "input_tokens": getattr(
            usage,
            "input_tokens",
            None,
        ),
        "output_tokens": getattr(
            usage,
            "output_tokens",
            None,
        ),
    }


def _extract_response_metadata(
    response: Any,
) -> Dict[str, Any]:
    """Extract non-sensitive OpenAI response metadata."""

    metadata: Dict[str, Any] = {}

    response_id = getattr(
        response,
        "id",
        None,
    )

    status = getattr(
        response,
        "status",
        None,
    )

    if response_id:
        metadata["response_id"] = response_id

    if status:
        metadata["status"] = status

    return metadata


class OpenAIResponsesClient:
    """Generate structured output through the OpenAI Responses API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        sdk_client: Optional[Any] = None,
    ) -> None:
        """Initialize the OpenAI client.

        sdk_client may be injected by unit tests so tests never make
        network requests.
        """

        self.model = _normalize_required_text(
            model,
            "OpenAI model",
        )

        normalized_api_key = (
            _normalize_required_text(
                api_key,
                "OpenAI API key",
            )
        )

        self.timeout_seconds = (
            _normalize_positive_float(
                timeout_seconds,
                "OpenAI timeout",
            )
        )

        self.max_retries = (
            _normalize_nonnegative_integer(
                max_retries,
                "OpenAI max retries",
            )
        )

        if sdk_client is None:
            self._client = openai.OpenAI(
                api_key=normalized_api_key,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
        else:
            self._client = sdk_client

    def generate(
        self,
        messages: Sequence[
            Mapping[str, str]
        ],
        response_schema: Mapping[str, Any],
    ) -> LLMClientResponse:
        """Generate one strict JSON-schema response."""

        normalized_messages = normalize_messages(
            messages
        )

        normalized_schema = (
            normalize_response_schema(
                response_schema
            )
        )

        request_input = [
            dict(message)
            for message in normalized_messages
        ]

        text_config = {
            "format": {
                "type": "json_schema",
                "name": (
                    OPENAI_RESPONSE_FORMAT_NAME
                ),
                "schema": normalized_schema,
                "strict": True,
            }
        }

        started_at = perf_counter()

        try:
            response = (
                self._client.responses.create(
                    model=self.model,
                    input=request_input,
                    text=text_config,
                    store=OPENAI_STORE_RESPONSES,
                    max_output_tokens=(
                        OPENAI_MAX_OUTPUT_TOKENS
                    ),
                )
            )

        except openai.APITimeoutError as error:
            raise LLMClientError(
                _build_error_message(
                    "OpenAI request timed out.",
                    error,
                ),
                error_code=(
                    REQUEST_TIMEOUT_ERROR
                ),
                retryable=True,
            ) from error

        except openai.RateLimitError as error:
            raise LLMClientError(
                _build_error_message(
                    "OpenAI rate limit was reached.",
                    error,
                ),
                error_code=RATE_LIMIT_ERROR,
                retryable=True,
            ) from error

        except openai.APIConnectionError as error:
            raise LLMClientError(
                _build_error_message(
                    (
                        "Could not connect to the "
                        "OpenAI API."
                    ),
                    error,
                ),
                error_code=(
                    PROVIDER_REQUEST_ERROR
                ),
                retryable=True,
            ) from error

        except openai.APIStatusError as error:
            status_code = getattr(
                error,
                "status_code",
                None,
            )

            retryable = (
                isinstance(status_code, int)
                and status_code >= 500
            )

            raise LLMClientError(
                _build_error_message(
                    (
                        "OpenAI API returned an "
                        f"error status: {status_code}."
                    ),
                    error,
                ),
                error_code=(
                    PROVIDER_REQUEST_ERROR
                ),
                retryable=retryable,
            ) from error

        latency_ms = (
            perf_counter() - started_at
        ) * 1000.0

        status = getattr(
            response,
            "status",
            None,
        )

        if status not in {
            None,
            "completed",
        }:
            raise LLMClientError(
                (
                    "OpenAI response did not complete "
                    f"successfully. Status: {status}."
                ),
                error_code=INVALID_RESPONSE_ERROR,
                retryable=False,
            )

        output_text = str(
            getattr(
                response,
                "output_text",
                "",
            )
            or ""
        ).strip()

        if not output_text:
            raise LLMClientError(
                (
                    "OpenAI response contained no "
                    "structured output text."
                ),
                error_code=INVALID_RESPONSE_ERROR,
                retryable=False,
            )

        usage = _extract_usage(response)

        response_model = str(
            getattr(
                response,
                "model",
                self.model,
            )
            or self.model
        ).strip()

        return LLMClientResponse(
            text=output_text,
            provider=OPENAI_PROVIDER,
            model=response_model,
            request_id=getattr(
                response,
                "_request_id",
                None,
            ),
            latency_ms=latency_ms,
            input_tokens=usage[
                "input_tokens"
            ],
            output_tokens=usage[
                "output_tokens"
            ],
            metadata=(
                _extract_response_metadata(
                    response
                )
            ),
        )
