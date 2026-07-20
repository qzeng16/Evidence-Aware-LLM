"""Tests for the OpenAI Responses API client adapter."""

from typing import Any, Dict, Optional

import pytest

from app.llm_clients import (
    INVALID_REQUEST_ERROR,
    INVALID_RESPONSE_ERROR,
    PROVIDER_REQUEST_ERROR,
    RATE_LIMIT_ERROR,
    REQUEST_TIMEOUT_ERROR,
    LLMClient,
    LLMClientError,
    OpenAIResponsesClient,
)
from app.llm_judge_contract import (
    LLM_JUDGE_JSON_SCHEMA,
)
from app.llm_judge_prompt import (
    build_llm_judge_messages,
)
import app.llm_clients.openai_responses as openai_module


class FakeUsage:
    """Small token-usage response."""

    input_tokens = 125
    output_tokens = 32


class FakeOpenAIResponse:
    """Small stand-in for an SDK Response object."""

    def __init__(
        self,
        output_text: str = (
            '{"label":"Uncertain",'
            '"confidence":0.5,'
            '"reason":"Insufficient evidence.",'
            '"evidence_ids":[]}'
        ),
        status: Optional[str] = "completed",
    ) -> None:
        self.output_text = output_text
        self.status = status
        self.model = "test-openai-model"
        self.id = "resp_test_001"
        self._request_id = "req_test_001"
        self.usage = FakeUsage()


class FakeResponsesResource:
    """Record Responses API calls."""

    def __init__(
        self,
        response: Optional[Any] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls = []

    def create(
        self,
        **kwargs: Any,
    ) -> Any:
        self.calls.append(kwargs)

        if self.error is not None:
            raise self.error

        return self.response


class FakeSDKClient:
    """SDK client exposing a responses resource."""

    def __init__(
        self,
        response: Optional[Any] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.responses = FakeResponsesResource(
            response=response,
            error=error,
        )


def build_messages():
    """Build one valid evidence-grounded request."""

    return build_llm_judge_messages(
        claim=(
            "Retrieval augmented generation can "
            "improve factual reliability."
        ),
        evidence_items=[
            {
                "evidence_id": "rag-002",
                "title": "RAG Factuality",
                "text": (
                    "Retrieval-augmented models "
                    "generated more factual language."
                ),
                "source_name": "Example paper",
                "source_type": "paper",
                "source_url": (
                    "https://example.com/paper"
                ),
            }
        ],
    )


def build_client(
    sdk_client: FakeSDKClient,
) -> OpenAIResponsesClient:
    """Build an adapter with a fake SDK backend."""

    return OpenAIResponsesClient(
        api_key="test-api-key",
        model="test-model",
        timeout_seconds=12.0,
        max_retries=3,
        sdk_client=sdk_client,
    )


def test_openai_client_implements_protocol():
    """The adapter should satisfy the shared client interface."""

    client = build_client(
        FakeSDKClient(
            response=FakeOpenAIResponse()
        )
    )

    assert isinstance(client, LLMClient)


def test_generate_uses_responses_structured_outputs():
    """The adapter should send strict JSON schema configuration."""

    sdk_client = FakeSDKClient(
        response=FakeOpenAIResponse()
    )

    client = build_client(sdk_client)

    response = client.generate(
        messages=build_messages(),
        response_schema=(
            LLM_JUDGE_JSON_SCHEMA
        ),
    )

    assert len(
        sdk_client.responses.calls
    ) == 1

    request = sdk_client.responses.calls[0]

    assert request["model"] == "test-model"
    assert request["store"] is False
    assert request["max_output_tokens"] == 800
    assert request["input"][0][
        "role"
    ] == "system"
    assert request["input"][1][
        "role"
    ] == "user"

    response_format = request["text"][
        "format"
    ]

    assert response_format["type"] == (
        "json_schema"
    )
    assert response_format["name"] == (
        "llm_judge_output"
    )
    assert response_format["strict"] is True
    assert response_format["schema"][
        "additionalProperties"
    ] is False

    assert response.provider == "openai"
    assert response.model == (
        "test-openai-model"
    )
    assert response.request_id == (
        "req_test_001"
    )
    assert response.input_tokens == 125
    assert response.output_tokens == 32
    assert response.latency_ms is not None
    assert response.latency_ms >= 0
    assert response.metadata[
        "response_id"
    ] == "resp_test_001"
    assert response.metadata[
        "status"
    ] == "completed"


def test_invalid_request_does_not_call_sdk():
    """Local validation should happen before a provider call."""

    sdk_client = FakeSDKClient(
        response=FakeOpenAIResponse()
    )

    client = build_client(sdk_client)

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            messages=[],
            response_schema=(
                LLM_JUDGE_JSON_SCHEMA
            ),
        )

    assert error_info.value.error_code == (
        INVALID_REQUEST_ERROR
    )
    assert sdk_client.responses.calls == []


class FakeTimeoutError(Exception):
    """Simulated OpenAI timeout."""


class FakeRateLimitError(Exception):
    """Simulated OpenAI rate limit."""


class FakeConnectionError(Exception):
    """Simulated OpenAI connection error."""


class FakeStatusError(Exception):
    """Simulated OpenAI HTTP status error."""

    def __init__(
        self,
        status_code: int,
        request_id: str = "req_error_001",
    ) -> None:
        super().__init__("Simulated status error.")

        self.status_code = status_code
        self.request_id = request_id


def test_timeout_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
):
    """Timeout errors should be retryable."""

    monkeypatch.setattr(
        openai_module.openai,
        "APITimeoutError",
        FakeTimeoutError,
    )

    client = build_client(
        FakeSDKClient(
            error=FakeTimeoutError()
        )
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            build_messages(),
            LLM_JUDGE_JSON_SCHEMA,
        )

    assert error_info.value.error_code == (
        REQUEST_TIMEOUT_ERROR
    )
    assert error_info.value.retryable is True


def test_rate_limit_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
):
    """Rate-limit errors should be retryable."""

    monkeypatch.setattr(
        openai_module.openai,
        "RateLimitError",
        FakeRateLimitError,
    )

    client = build_client(
        FakeSDKClient(
            error=FakeRateLimitError()
        )
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            build_messages(),
            LLM_JUDGE_JSON_SCHEMA,
        )

    assert error_info.value.error_code == (
        RATE_LIMIT_ERROR
    )
    assert error_info.value.retryable is True


def test_connection_error_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
):
    """Connection errors should be retryable."""

    monkeypatch.setattr(
        openai_module.openai,
        "APIConnectionError",
        FakeConnectionError,
    )

    client = build_client(
        FakeSDKClient(
            error=FakeConnectionError()
        )
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            build_messages(),
            LLM_JUDGE_JSON_SCHEMA,
        )

    assert error_info.value.error_code == (
        PROVIDER_REQUEST_ERROR
    )
    assert error_info.value.retryable is True


@pytest.mark.parametrize(
    "status_code, expected_retryable",
    [
        (400, False),
        (401, False),
        (500, True),
        (503, True),
    ],
)
def test_status_error_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_retryable: bool,
):
    """Only server-side HTTP failures should be retryable."""

    monkeypatch.setattr(
        openai_module.openai,
        "APIStatusError",
        FakeStatusError,
    )

    client = build_client(
        FakeSDKClient(
            error=FakeStatusError(
                status_code
            )
        )
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            build_messages(),
            LLM_JUDGE_JSON_SCHEMA,
        )

    assert error_info.value.error_code == (
        PROVIDER_REQUEST_ERROR
    )
    assert (
        error_info.value.retryable
        is expected_retryable
    )
    assert "req_error_001" in str(
        error_info.value
    )


@pytest.mark.parametrize(
    "response",
    [
        FakeOpenAIResponse(
            output_text="",
        ),
        FakeOpenAIResponse(
            status="incomplete",
        ),
        FakeOpenAIResponse(
            status="failed",
        ),
    ],
)
def test_invalid_provider_response_is_rejected(
    response: FakeOpenAIResponse,
):
    """Incomplete or empty responses should not enter the parser."""

    client = build_client(
        FakeSDKClient(
            response=response
        )
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            build_messages(),
            LLM_JUDGE_JSON_SCHEMA,
        )

    assert error_info.value.error_code == (
        INVALID_RESPONSE_ERROR
    )
    assert error_info.value.retryable is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "api_key": "",
            "model": "test-model",
        },
        {
            "api_key": "test-key",
            "model": "",
        },
        {
            "api_key": "test-key",
            "model": "test-model",
            "timeout_seconds": 0,
        },
        {
            "api_key": "test-key",
            "model": "test-model",
            "max_retries": -1,
        },
    ],
)
def test_invalid_client_configuration_is_rejected(
    kwargs: Dict[str, Any],
):
    """Malformed provider configuration should fail locally."""

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        OpenAIResponsesClient(
            sdk_client=FakeSDKClient(
                response=FakeOpenAIResponse()
            ),
            **kwargs,
        )

    assert error_info.value.error_code == (
        INVALID_REQUEST_ERROR
    )
