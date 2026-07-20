"""Tests for the structured LLM judge output contract."""

import pytest

from app.llm_judge_contract import (
    LLM_JUDGE_JSON_SCHEMA,
    LLMJudgeOutput,
    LLMJudgeOutputError,
)
from app.verification_result import (
    VerificationLabel,
    VerifierType,
)


def test_supported_output_converts_to_shared_result():
    """A supported output should become VerificationResult."""

    output = LLMJudgeOutput(
        label="Supported",
        confidence=0.84,
        reason=(
            "Evidence rag-002 directly supports "
            "the claim."
        ),
        evidence_ids=(
            "rag-002",
        ),
    )

    result = output.to_verification_result()

    assert (
        result.label
        == VerificationLabel.SUPPORTED
    )
    assert result.confidence == 0.84
    assert (
        result.verifier_type
        == VerifierType.LLM
    )
    assert result.matched_evidence_ids == (
        "rag-002",
    )
    assert result.matched_rule is None
    assert result.abstention_reason is None


def test_uncertain_output_uses_reason_as_abstention():
    """Uncertain decisions should preserve their explanation."""

    output = LLMJudgeOutput(
        label="Uncertain",
        confidence=0.45,
        reason=(
            "The supplied evidence is insufficient."
        ),
        evidence_ids=(),
    )

    result = output.to_verification_result()

    assert result.label == (
        VerificationLabel.UNCERTAIN
    )
    assert result.abstention_reason == (
        "The supplied evidence is insufficient."
    )


def test_decisive_output_requires_evidence_id():
    """Supported and Refuted outputs must cite evidence."""

    with pytest.raises(
        LLMJudgeOutputError,
        match="cite at least one evidence ID",
    ):
        LLMJudgeOutput(
            label="Refuted",
            confidence=0.8,
            reason=(
                "The evidence contradicts the claim."
            ),
            evidence_ids=(),
        )


def test_output_rejects_unknown_evidence_id():
    """The output may cite only supplied evidence IDs."""

    output = LLMJudgeOutput(
        label="Supported",
        confidence=0.8,
        reason="The evidence supports the claim.",
        evidence_ids=(
            "invented-999",
        ),
    )

    with pytest.raises(
        LLMJudgeOutputError,
        match="unknown evidence IDs",
    ):
        output.validate_evidence_ids(
            [
                "rag-002",
                "seed-002",
            ]
        )


def test_output_accepts_available_evidence_ids():
    """Known evidence IDs should pass validation."""

    output = LLMJudgeOutput(
        label="Refuted",
        confidence=0.8,
        reason=(
            "The evidence contradicts the claim."
        ),
        evidence_ids=(
            "rag-002",
        ),
    )

    output.validate_evidence_ids(
        [
            "rag-002",
            "seed-002",
        ]
    )


def test_confidence_outside_range_is_rejected():
    """Confidence must remain between zero and one."""

    with pytest.raises(
        LLMJudgeOutputError,
        match="between 0.0 and 1.0",
    ):
        LLMJudgeOutput(
            label="Uncertain",
            confidence=1.2,
            reason="Invalid confidence.",
            evidence_ids=(),
        )


def test_single_string_evidence_ids_is_rejected():
    """evidence_ids must be a JSON array."""

    with pytest.raises(
        LLMJudgeOutputError,
        match="must be an array",
    ):
        LLMJudgeOutput(
            label="Supported",
            confidence=0.8,
            reason="The evidence supports the claim.",
            evidence_ids="rag-002",
        )


def test_from_dict_rejects_extra_fields():
    """Unexpected model-generated fields should fail."""

    with pytest.raises(
        LLMJudgeOutputError,
        match="unexpected fields",
    ):
        LLMJudgeOutput.from_dict(
            {
                "label": "Uncertain",
                "confidence": 0.5,
                "reason": "Insufficient evidence.",
                "evidence_ids": [],
                "extra_comment": "Not allowed.",
            }
        )


def test_json_schema_is_strict():
    """The provider schema should reject extra fields."""

    assert (
        LLM_JUDGE_JSON_SCHEMA[
            "additionalProperties"
        ]
        is False
    )

    assert set(
        LLM_JUDGE_JSON_SCHEMA["required"]
    ) == {
        "label",
        "confidence",
        "reason",
        "evidence_ids",
    }
