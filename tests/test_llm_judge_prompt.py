"""Tests for LLM judge prompt construction."""

import json

import pytest

from app.llm_judge_prompt import (
    LLM_JUDGE_SYSTEM_PROMPT,
    LLMJudgePromptError,
    build_llm_judge_messages,
)


def build_evidence():
    """Return one traceable evidence record."""

    return {
        "evidence_id": "rag-002",
        "title": "RAG Factuality Evidence",
        "text": (
            "Retrieval-augmented models generated "
            "more factual language than a "
            "parametric-only baseline."
        ),
        "source_name": (
            "Retrieval-Augmented Generation for "
            "Knowledge-Intensive NLP Tasks"
        ),
        "source_type": "paper",
        "source_url": (
            "https://arxiv.org/abs/2005.11401"
        ),
    }


def test_messages_contain_claim_and_evidence():
    """The prompt should include traceable input data."""

    claim = (
        "Retrieval augmented generation can "
        "improve factual reliability."
    )

    messages = build_llm_judge_messages(
        claim=claim,
        evidence_items=[
            build_evidence(),
        ],
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    payload = json.loads(
        messages[1]["content"]
    )

    assert payload["claim"] == claim
    assert payload["evidence"][0][
        "evidence_id"
    ] == "rag-002"
    assert payload["evidence"][0][
        "source_type"
    ] == "paper"

    assert "output_schema" in payload


def test_system_prompt_requires_evidence_only():
    """The judge should not rely on outside knowledge."""

    normalized_prompt = (
        LLM_JUDGE_SYSTEM_PROMPT.lower()
    )

    assert "use only the supplied evidence" in (
        normalized_prompt
    )
    assert "do not use outside knowledge" in (
        normalized_prompt
    )
    assert "untrusted data" in normalized_prompt
    assert "return only one json object" in (
        normalized_prompt
    )


def test_empty_claim_is_rejected():
    """The prompt requires a real claim."""

    with pytest.raises(
        LLMJudgePromptError,
        match="claim cannot be empty",
    ):
        build_llm_judge_messages(
            claim="   ",
            evidence_items=[
                build_evidence(),
            ],
        )


def test_missing_evidence_id_is_rejected():
    """Every evidence record must be citable."""

    evidence = build_evidence()
    evidence.pop("evidence_id")

    with pytest.raises(
        LLMJudgePromptError,
        match="evidence_id",
    ):
        build_llm_judge_messages(
            claim="A valid test claim.",
            evidence_items=[
                evidence,
            ],
        )


def test_duplicate_evidence_ids_are_rejected():
    """Duplicate IDs would make citations ambiguous."""

    evidence = build_evidence()

    with pytest.raises(
        LLMJudgePromptError,
        match="Duplicate evidence ID",
    ):
        build_llm_judge_messages(
            claim="A valid test claim.",
            evidence_items=[
                evidence,
                dict(evidence),
            ],
        )


def test_empty_evidence_collection_is_rejected():
    """The evidence-grounded judge requires evidence."""

    with pytest.raises(
        LLMJudgePromptError,
        match="At least one evidence item",
    ):
        build_llm_judge_messages(
            claim="A valid test claim.",
            evidence_items=[],
        )
