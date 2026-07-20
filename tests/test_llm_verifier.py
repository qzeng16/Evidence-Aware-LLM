"""Tests for the evidence-grounded LLM verifier."""

import json
from typing import Any, Dict, List

import pytest

from app.llm_clients import (
    LLMClientError,
    FakeLLMClient,
)
from app.llm_judge_parser import (
    UNKNOWN_EVIDENCE_ERROR,
    LLMJudgeResponseParseError,
)
from app.llm_judge_prompt import (
    LLMJudgePromptError,
)
from app.verification_result import (
    VerificationLabel,
    VerifierType,
)
from app.verifiers import (
    LLMVerifier,
    VerificationRun,
    Verifier,
)
import app.verifiers.llm as llm_module


def build_retrieved_evidence() -> List[
    Dict[str, Any]
]:
    """Return traceable evidence used by tests."""

    return [
        {
            "evidence_id": "rag-002",
            "title": "RAG Factuality Evidence",
            "text": (
                "Retrieval-augmented models generated "
                "more factual language than a "
                "parametric-only baseline."
            ),
            "source_name": "Example paper",
            "source_type": "paper",
            "source_url": (
                "https://example.com/rag-paper"
            ),
            "score": 0.72,
            "embedding_score": 0.74,
            "keyword_score": 0.64,
        },
        {
            "evidence_id": "seed-002",
            "title": (
                "Retrieval Augmented Generation"
            ),
            "text": (
                "RAG can improve factual reliability "
                "by grounding answers in retrieved "
                "documents."
            ),
            "source_name": "Seed corpus",
            "source_type": "other",
            "source_url": "",
            "score": 0.65,
            "embedding_score": 0.67,
            "keyword_score": 0.57,
        },
    ]


def build_supported_response() -> str:
    """Return one valid structured LLM response."""

    return json.dumps(
        {
            "label": "Supported",
            "confidence": 0.84,
            "reason": (
                "Evidence rag-002 directly supports "
                "the claim."
            ),
            "evidence_ids": [
                "rag-002",
            ],
        }
    )


def build_verifier(
    client: FakeLLMClient,
) -> LLMVerifier:
    """Build an LLMVerifier with lightweight dependencies."""

    return LLMVerifier(
        evidence_db=[],
        model=object(),
        evidence_embeddings=object(),
        client=client,
    )


def patch_retrieval(
    monkeypatch: pytest.MonkeyPatch,
    evidence_results: List[Dict[str, Any]],
) -> None:
    """Replace semantic retrieval with deterministic data."""

    monkeypatch.setattr(
        llm_module.core_verifier,
        "search_evidence",
        lambda **kwargs: evidence_results,
    )


def test_llm_verifier_implements_shared_interface():
    """LLMVerifier should satisfy the Verifier protocol."""

    verifier = build_verifier(
        FakeLLMClient(
            responses=[
                build_supported_response(),
            ]
        )
    )

    assert isinstance(verifier, Verifier)
    assert (
        verifier.verifier_type
        == VerifierType.LLM
    )


def test_llm_verifier_returns_supported_run(
    monkeypatch: pytest.MonkeyPatch,
):
    """A valid model response should become VerificationRun."""

    evidence_results = (
        build_retrieved_evidence()
    )

    patch_retrieval(
        monkeypatch,
        evidence_results,
    )

    client = FakeLLMClient(
        responses=[
            build_supported_response(),
        ]
    )

    verifier = build_verifier(client)

    claim = (
        "Retrieval augmented generation can "
        "improve factual reliability."
    )

    run = verifier.verify(claim)

    assert isinstance(run, VerificationRun)
    assert run.claim == claim

    assert (
        run.result.label
        == VerificationLabel.SUPPORTED
    )
    assert run.result.confidence == 0.84
    assert (
        run.result.verifier_type
        == VerifierType.LLM
    )
    assert run.result.matched_evidence_ids == (
        "rag-002",
    )
    assert run.result.matched_rule is None
    assert run.result.abstention_reason is None

    assert len(run.evidence) == 2
    assert run.evidence[0]["evidence_id"] == (
        "rag-002"
    )

    assert len(client.calls) == 1

    recorded_call = client.calls[0]

    assert recorded_call.response_schema[
        "additionalProperties"
    ] is False

    user_payload = json.loads(
        recorded_call.messages[1]["content"]
    )

    assert user_payload["claim"] == claim
    assert user_payload["evidence"][0][
        "evidence_id"
    ] == "rag-002"


def test_no_evidence_returns_uncertain_without_client_call(
    monkeypatch: pytest.MonkeyPatch,
):
    """The verifier should abstain before calling the model."""

    patch_retrieval(
        monkeypatch,
        [],
    )

    client = FakeLLMClient(
        responses=[]
    )

    verifier = build_verifier(client)

    run = verifier.verify(
        "A claim with no relevant evidence."
    )

    assert (
        run.result.label
        == VerificationLabel.UNCERTAIN
    )
    assert run.result.confidence == 0.3
    assert (
        run.result.verifier_type
        == VerifierType.LLM
    )
    assert run.result.matched_evidence_ids == ()
    assert run.result.abstention_reason is not None
    assert run.evidence == ()
    assert client.calls == ()


def test_unknown_evidence_citation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
):
    """The model cannot cite evidence it did not receive."""

    patch_retrieval(
        monkeypatch,
        build_retrieved_evidence(),
    )

    response_text = json.dumps(
        {
            "label": "Supported",
            "confidence": 0.8,
            "reason": (
                "The evidence supports the claim."
            ),
            "evidence_ids": [
                "invented-999",
            ],
        }
    )

    verifier = build_verifier(
        FakeLLMClient(
            responses=[
                response_text,
            ]
        )
    )

    with pytest.raises(
        LLMJudgeResponseParseError,
    ) as error_info:
        verifier.verify(
            "A valid test claim."
        )

    assert error_info.value.error_code == (
        UNKNOWN_EVIDENCE_ERROR
    )


def test_client_error_is_propagated(
    monkeypatch: pytest.MonkeyPatch,
):
    """Provider failures should remain visible to later fallback logic."""

    patch_retrieval(
        monkeypatch,
        build_retrieved_evidence(),
    )

    expected_error = LLMClientError(
        "Simulated provider timeout.",
        error_code="request_timeout",
        retryable=True,
    )

    verifier = build_verifier(
        FakeLLMClient(
            responses=[
                expected_error,
            ]
        )
    )

    with pytest.raises(
        LLMClientError,
    ) as error_info:
        verifier.verify(
            "A valid test claim."
        )

    assert error_info.value is expected_error
    assert error_info.value.retryable is True


def test_missing_evidence_id_is_rejected_before_client_call(
    monkeypatch: pytest.MonkeyPatch,
):
    """Evidence supplied to the LLM must remain traceable."""

    evidence_results = (
        build_retrieved_evidence()
    )

    evidence_results[0].pop(
        "evidence_id"
    )

    patch_retrieval(
        monkeypatch,
        evidence_results,
    )

    client = FakeLLMClient(
        responses=[
            build_supported_response(),
        ]
    )

    verifier = build_verifier(client)

    with pytest.raises(
        LLMJudgePromptError,
        match="evidence_id",
    ):
        verifier.verify(
            "A valid test claim."
        )

    assert client.calls == ()


def test_search_parameters_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
):
    """Configured retrieval parameters should reach the core."""

    captured_arguments: Dict[str, Any] = {}

    def fake_search_evidence(**kwargs):
        captured_arguments.update(kwargs)

        return []

    monkeypatch.setattr(
        llm_module.core_verifier,
        "search_evidence",
        fake_search_evidence,
    )

    client = FakeLLMClient(
        responses=[]
    )

    verifier = LLMVerifier(
        evidence_db=[
            {
                "title": "Test",
                "text": "Test evidence.",
            }
        ],
        model=object(),
        evidence_embeddings=object(),
        client=client,
        initial_top_k=8,
        final_top_k=3,
        min_score=0.35,
    )

    verifier.verify(
        "A valid test claim."
    )

    assert captured_arguments[
        "initial_top_k"
    ] == 8
    assert captured_arguments[
        "final_top_k"
    ] == 3
    assert captured_arguments[
        "min_score"
    ] == 0.35
