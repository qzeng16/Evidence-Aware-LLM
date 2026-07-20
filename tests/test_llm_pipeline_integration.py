"""Offline integration tests for the complete LLM judge pipeline."""

import json
from typing import Any, Dict, List

import pytest

import layer0_verifier as core_verifier
from app.llm_clients import FakeLLMClient
from app.verification_result import (
    VerificationLabel,
    VerifierType,
)
from app.verifiers import LLMVerifier
import app.verifiers.llm as llm_module


def build_retrieved_evidence() -> List[
    Dict[str, Any]
]:
    """Return deterministic evidence for pipeline testing."""

    return [
        {
            "evidence_id": "rag-002",
            "title": (
                "RAG Improved Factuality in "
                "Evaluated Generation Tasks"
            ),
            "text": (
                "Retrieval-augmented models generated "
                "more factual language than a "
                "parametric-only sequence-to-sequence "
                "baseline."
            ),
            "source_name": (
                "Retrieval-Augmented Generation for "
                "Knowledge-Intensive NLP Tasks"
            ),
            "source_type": "paper",
            "topic": (
                "retrieval augmented generation"
            ),
            "source_url": (
                "https://example.com/rag-paper"
            ),
            "published_at": "2020-05-22",
            "retrieved_at": "2026-07-19",
            "score": 0.71,
            "embedding_score": 0.73,
            "keyword_score": 0.63,
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
            "source_name": "Portfolio seed corpus",
            "source_type": "other",
            "topic": (
                "retrieval augmented generation"
            ),
            "source_url": "",
            "published_at": "",
            "retrieved_at": "",
            "score": 0.62,
            "embedding_score": 0.63,
            "keyword_score": 0.57,
        },
    ]


def test_complete_offline_llm_judge_pipeline(
    monkeypatch: pytest.MonkeyPatch,
):
    """Prompt, fake client, parser, and verifier should work together."""

    claim = (
        "Retrieval augmented generation can "
        "improve factual reliability."
    )

    evidence_results = build_retrieved_evidence()

    monkeypatch.setattr(
        llm_module.core_verifier,
        "search_evidence",
        lambda **kwargs: evidence_results,
    )

    fake_model_output = json.dumps(
        {
            "label": "Supported",
            "confidence": 0.84,
            "reason": (
                "Evidence rag-002 directly supports "
                "the claim because it reports more "
                "factual generated language than the "
                "parametric-only baseline."
            ),
            "evidence_ids": [
                "rag-002",
            ],
        }
    )

    client = FakeLLMClient(
        responses=[
            fake_model_output,
        ],
    )

    verifier = LLMVerifier(
        evidence_db=[],
        model=object(),
        evidence_embeddings=object(),
        client=client,
    )

    verification_run = verifier.verify(claim)

    assert verification_run.claim == claim

    assert (
        verification_run.result.label
        == VerificationLabel.SUPPORTED
    )
    assert (
        verification_run.result.verifier_type
        == VerifierType.LLM
    )
    assert (
        verification_run.result.confidence
        == 0.84
    )
    assert (
        verification_run.result.matched_evidence_ids
        == ("rag-002",)
    )
    assert (
        verification_run.result.matched_rule
        is None
    )
    assert (
        verification_run.result.abstention_reason
        is None
    )

    assert len(verification_run.evidence) == 2
    assert (
        verification_run.evidence[0][
            "evidence_id"
        ]
        == "rag-002"
    )

    assert len(client.calls) == 1

    recorded_call = client.calls[0]

    assert (
        recorded_call.messages[0]["role"]
        == "system"
    )
    assert (
        recorded_call.messages[1]["role"]
        == "user"
    )

    prompt_payload = json.loads(
        recorded_call.messages[1]["content"]
    )

    assert prompt_payload["claim"] == claim
    assert (
        prompt_payload["evidence"][0][
            "evidence_id"
        ]
        == "rag-002"
    )
    assert (
        prompt_payload["evidence"][1][
            "evidence_id"
        ]
        == "seed-002"
    )
    assert (
        prompt_payload["output_schema"][
            "additionalProperties"
        ]
        is False
    )

    legacy_result = (
        verification_run.to_legacy_dict()
    )

    api_response = (
        core_verifier.build_success_response(
            legacy_result
        )
    )

    api_response["data"]["verification"] = (
        verification_run.result.to_dict()
    )

    assert api_response["data"][
        "prediction"
    ] == {
        "label": "Supported",
        "confidence": 0.84,
    }

    assert api_response["data"][
        "verification"
    ]["verifier_type"] == "llm"

    assert api_response["data"][
        "verification"
    ]["matched_evidence_ids"] == [
        "rag-002",
    ]

    assert api_response["data"][
        "evidence"
    ][0]["source_type"] == "paper"
