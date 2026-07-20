"""Tests for the legacy rule-verifier adapter."""

import pytest

from app.rule_verifier_adapter import (
    build_rule_verification_result,
)
from app.verification_result import (
    VerificationLabel,
    VerificationResultError,
    VerifierType,
)


def test_supported_rule_result_is_adapted():
    """A decisive legacy result should become VerificationResult."""

    legacy_result = {
        "label": "Supported",
        "confidence": 0.86,
        "matched_evidence_ids": [
            "seed-002",
        ],
        "matched_rule": (
            "supports_rag_improves_reliability"
        ),
        "abstention_reason": None,
    }

    result = build_rule_verification_result(
        legacy_result
    )

    assert (
        result.label
        == VerificationLabel.SUPPORTED
    )
    assert result.confidence == 0.86
    assert (
        result.verifier_type
        == VerifierType.RULE
    )
    assert result.matched_evidence_ids == (
        "seed-002",
    )
    assert result.matched_rule == (
        "supports_rag_improves_reliability"
    )
    assert result.abstention_reason is None
    assert "supports the claim" in result.reason


def test_uncertain_result_preserves_abstention_reason():
    """An abstention explanation should remain available."""

    legacy_result = {
        "label": "Uncertain",
        "confidence": 0.5,
        "matched_evidence_ids": [],
        "matched_rule": None,
        "abstention_reason": (
            "No verification rule matched."
        ),
    }

    result = build_rule_verification_result(
        legacy_result
    )

    assert (
        result.label
        == VerificationLabel.UNCERTAIN
    )
    assert result.reason == (
        "No verification rule matched."
    )
    assert result.abstention_reason == (
        "No verification rule matched."
    )


def test_adapter_normalizes_evidence_ids():
    """Blank and duplicate evidence IDs should be removed."""

    legacy_result = {
        "label": "Refuted",
        "confidence": 0.82,
        "matched_evidence_ids": [
            " rag-002 ",
            "",
            "rag-002",
            "seed-002",
        ],
        "matched_rule": "test-rule",
        "abstention_reason": None,
    }

    result = build_rule_verification_result(
        legacy_result
    )

    assert result.matched_evidence_ids == (
        "rag-002",
        "seed-002",
    )


def test_adapter_supports_legacy_result_without_ids():
    """Older result dictionaries should remain compatible."""

    legacy_result = {
        "label": "Supported",
        "confidence": 0.8,
        "matched_rule": "test-rule",
        "abstention_reason": None,
    }

    result = build_rule_verification_result(
        legacy_result
    )

    assert result.matched_evidence_ids == ()


def test_adapter_rejects_missing_core_fields():
    """A malformed legacy result should not pass silently."""

    with pytest.raises(
        VerificationResultError,
        match="missing fields",
    ):
        build_rule_verification_result(
            {
                "label": "Supported",
            }
        )
