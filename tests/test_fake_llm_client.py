"""Tests for the deterministic fake LLM client."""

import json

import pytest

from app.llm_clients import (
    FAKE_RESPONSE_EXHAUSTED_ERROR,
    INVALID_REQUEST_ERROR,
    LLMClient,
    LLMClientError,
    LLMClientResponse,
    FakeLLMClient,
)
from app.llm_judge_contract import (
    LLM_JUDGE_JSON_SCHEMA,
)
from app.llm_judge_prompt import (
    build_llm_judge_messages,
)


def build_messages():
    """Build one valid judge request."""

    return build_llm_judge_messages(
        claim=(
            "Retrieval augmented generation can "
            "improve factual reliability."
        ),
        evidence_items=[
            {
                "evidence_id": "rag-002",
                "title": "RAG Factuality Evidence",
                "text": (
                    "Retrieval-augmented models "
                    "generated more factual language "
                    "than a parametric-only baseline."
                ),
                "source_name": "Example paper",
                "source_type": "paper",
                "source_url": (
                    "https://example.com/paper"
                ),
            }
        ],
    )


def build_response_text():
    """Build one valid structured response."""

    return json.dumps(
        {
            "label": "Supported",
            "confidence": 0.84,
            "reason": (
                "Evidence rag-002 directly "
                "supports the claim."
            ),
            "evidence_ids": [
                "rag-002",
            ],
        }
    )


def test_fake_client_implements_protocol():
    """FakeLLMClient should satisfy the client interface."""

    client = FakeLLMClient(
        responses=[
            build_response_text(),
        ]
    )

    assert isinstance(client, LLMClient)


def test_fake_client_returns_queued_text():
    """A queued string should become LLMClientResponse."""

    client = FakeLLMClient(
        responses=[
            build_response_text(),
        ]
    )

    response = client.generate(
        messages=build_messages(),
        response_schema=(
            LLM_JUDGE_JSON_SCHEMA
        ),
    )

    assert isinstance(
        response,
        LLMClientResponse,
    )

    assert response.text == (
        build_response_text()
    )
    assert response.provider == "fake"
    assert response.model == (
        "fake-structured-model"
    )
    assert response.request_id == (
        "fake-request-0001"
    )
    assert response.metadata["fake"] is True
    assert client.remaining_responses == 0


def test_fake_client_records_normalized_call():
    """The fake should expose requests for assertions."""

    client = FakeLLMClient(
        responses=[
            build_response_text(),
        ]
    )

    messages = build_messages()

    client.generate(
        messages=messages,
        response_schema=(
            LLM_JUDGE_JSON_SCHEMA
        ),
    )

    assert len(client.calls) == 1

    recorded_call = client.calls[0]

    assert recorded_call.messages[0][
        "role"
    ] == "system"

    assert recorded_call.messages[1][
        "role"
    ] == "user"

    assert recorded_call.response_schema[
        "type"
    ] == "object"


def test_fake_client_returns_response_object():
    """A fully constructed response should be returned unchanged."""

    expected_response = LLMClientResponse(
        text=build_response_text(),
        provider="custom-fake",
        model="custom-model",
        request_id="custom-request",
        latency_ms=12.5,
        input_tokens=100,
        output_tokens=30,
    )

    client = FakeLLMClient(
        responses=[
            expected_response,
        ]
    )

    actual_response = client.generate(
        messages=build_messages(),
        response_schema=(
            LLM_JUDGE_JSON_SCHEMA
        ),
    )

    assert actual_response is expected_response


def test_fake_client_raises_queued_error():
    """Queued failures should simulate provider errors."""

    expected_error = LLMClientError(
        "Simulated provider timeout.",
        error_code="request_timeout",
        retryable=True,
    )

    client = FakeLLMClient(
        responses=[
            expected_error,
        ]
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            messages=build_messages(),
            response_schema=(
                LLM_JUDGE_JSON_SCHEMA
            ),
        )

    assert error_info.value is expected_error
    assert error_info.value.retryable is True
    assert client.remaining_responses == 0


def test_fake_client_reports_exhaustion():
    """Calling past the queue should fail explicitly."""

    client = FakeLLMClient(
        responses=[]
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            messages=build_messages(),
            response_schema=(
                LLM_JUDGE_JSON_SCHEMA
            ),
        )

    assert error_info.value.error_code == (
        FAKE_RESPONSE_EXHAUSTED_ERROR
    )
    assert error_info.value.retryable is False


def test_invalid_messages_do_not_consume_response():
    """Request validation should happen before queue consumption."""

    client = FakeLLMClient(
        responses=[
            build_response_text(),
        ]
    )

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
    assert client.remaining_responses == 1
    assert client.calls == ()


def test_invalid_schema_does_not_consume_response():
    """Invalid schemas should fail before recording a call."""

    client = FakeLLMClient(
        responses=[
            build_response_text(),
        ]
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        client.generate(
            messages=build_messages(),
            response_schema={
                "type": "array",
            },
        )

    assert error_info.value.error_code == (
        INVALID_REQUEST_ERROR
    )
    assert client.remaining_responses == 1
    assert client.calls == ()
