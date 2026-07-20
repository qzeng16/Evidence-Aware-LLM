"""Tests for the shared verification result contract."""

import pytest

from app.verification_result import (
    VerificationLabel,
    VerificationResult,
    VerificationResultError,
    VerifierType,
)


def test_supported_result_serializes_to_dictionary():
    """A valid rule result should serialize consistently."""

    result = VerificationResult(
        label=VerificationLabel.SUPPORTED,
        confidence=0.86,
        reason=(
            "The retrieved evidence supports "
            "the claim."
        ),
        verifier_type=VerifierType.RULE,
        matched_evidence_ids=(
            "seed-002",
        ),
        matched_rule=(
            "supports_rag_improves_reliability"
        ),
    )

    assert result.to_dict() == {
        "label": "Supported",
        "confidence": 0.86,
        "reason": (
            "The retrieved evidence supports "
            "the claim."
        ),
        "verifier_type": "rule",
        "matched_evidence_ids": [
            "seed-002",
        ],
        "matched_rule": (
            "supports_rag_improves_reliability"
        ),
        "abstention_reason": None,
    }


def test_string_enum_values_are_normalized():
    """Plain strings should become validated enum values."""

    result = VerificationResult(
        label="Refuted",
        confidence="0.82",
        reason="The evidence contradicts the claim.",
        verifier_type="llm",
        matched_evidence_ids=(
            "rag-002",
        ),
    )

    assert (
        result.label
        == VerificationLabel.REFUTED
    )
    assert (
        result.verifier_type
        == VerifierType.LLM
    )
    assert result.confidence == 0.82


def test_evidence_ids_are_normalized_and_deduplicated():
    """Duplicate and blank evidence IDs should be removed."""

    result = VerificationResult(
        label="Supported",
        confidence=0.8,
        reason="Evidence supports the claim.",
        verifier_type="rule",
        matched_evidence_ids=(
            " rag-002 ",
            "",
            "rag-002",
            "seed-002",
        ),
    )

    assert result.matched_evidence_ids == (
        "rag-002",
        "seed-002",
    )


def test_uncertain_result_accepts_abstention_reason():
    """Uncertain results may explain why they abstained."""

    result = VerificationResult(
        label="Uncertain",
        confidence=0.5,
        reason=(
            "The verifier could not determine "
            "the relationship."
        ),
        verifier_type="rule",
        abstention_reason=(
            "No verification rule matched."
        ),
    )

    assert (
        result.label
        == VerificationLabel.UNCERTAIN
    )
    assert result.abstention_reason == (
        "No verification rule matched."
    )


@pytest.mark.parametrize(
    "confidence",
    [
        -0.01,
        1.01,
    ],
)
def test_confidence_outside_valid_range_is_rejected(
    confidence,
):
    """Confidence must remain between zero and one."""

    with pytest.raises(
        VerificationResultError,
        match="between 0.0 and 1.0",
    ):
        VerificationResult(
            label="Supported",
            confidence=confidence,
            reason="Evidence supports the claim.",
            verifier_type="rule",
        )


def test_invalid_label_is_rejected():
    """Unknown labels should fail validation."""

    with pytest.raises(
        VerificationResultError,
        match="Invalid verification label",
    ):
        VerificationResult(
            label="Probably True",
            confidence=0.7,
            reason="Invalid label test.",
            verifier_type="rule",
        )


def test_invalid_verifier_type_is_rejected():
    """Unknown verifier implementations should fail."""

    with pytest.raises(
        VerificationResultError,
        match="Invalid verifier type",
    ):
        VerificationResult(
            label="Supported",
            confidence=0.7,
            reason="Invalid verifier type test.",
            verifier_type="human",
        )


def test_empty_reason_is_rejected():
    """Every result should explain its decision."""

    with pytest.raises(
        VerificationResultError,
        match="reason cannot be empty",
    ):
        VerificationResult(
            label="Uncertain",
            confidence=0.5,
            reason="   ",
            verifier_type="rule",
        )


def test_supported_result_cannot_have_abstention_reason():
    """A decisive result must not claim that it abstained."""

    with pytest.raises(
        VerificationResultError,
        match="Only an Uncertain result",
    ):
        VerificationResult(
            label="Supported",
            confidence=0.8,
            reason="Evidence supports the claim.",
            verifier_type="rule",
            abstention_reason=(
                "Insufficient evidence."
            ),
        )


def test_result_can_round_trip_through_dictionary():
    """Serialized results should be recoverable."""

    original_result = VerificationResult(
        label="Uncertain",
        confidence=0.45,
        reason=(
            "The retrieved evidence produced "
            "conflicting labels."
        ),
        verifier_type="hybrid",
        matched_evidence_ids=(
            "rag-002",
            "seed-002",
        ),
        abstention_reason=(
            "Verifier disagreement."
        ),
    )

    restored_result = (
        VerificationResult.from_dict(
            original_result.to_dict()
        )
    )

    assert restored_result == original_result


def test_missing_required_dictionary_field_is_rejected():
    """Dictionary construction should require core fields."""

    with pytest.raises(
        VerificationResultError,
        match="missing fields",
    ):
        VerificationResult.from_dict(
            {
                "label": "Supported",
                "confidence": 0.8,
            }
        )
