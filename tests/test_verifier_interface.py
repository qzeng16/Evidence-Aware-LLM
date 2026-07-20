"""Tests for the shared verifier interface."""

from typing import Any, Dict

import pytest

from app.verification_result import (
    VerificationResult,
    VerifierType,
)
from app.verifiers import (
    RuleVerifier,
    VerificationRun,
    Verifier,
)
from app.verifiers.base import (
    VerificationRunError,
)
import app.verifiers.rule as rule_module


def build_supported_result() -> VerificationResult:
    """Build a reusable supported result."""

    return VerificationResult(
        label="Supported",
        confidence=0.86,
        reason=(
            "The retrieved evidence supports "
            "the claim."
        ),
        verifier_type="rule",
        matched_evidence_ids=(
            "seed-002",
        ),
        matched_rule=(
            "supports_rag_improves_reliability"
        ),
    )


def test_verification_run_converts_to_legacy_format():
    """Unified executions should support the old response builder."""

    run = VerificationRun(
        claim=(
            "Retrieval augmented generation can "
            "improve factual reliability."
        ),
        result=build_supported_result(),
        evidence=(
            {
                "evidence_id": "seed-002",
                "title": (
                    "Retrieval Augmented Generation"
                ),
                "text": (
                    "RAG can improve factual reliability."
                ),
            },
        ),
    )

    legacy_result = run.to_legacy_dict()

    assert legacy_result["label"] == "Supported"
    assert legacy_result["confidence"] == 0.86
    assert legacy_result[
        "matched_evidence_ids"
    ] == ["seed-002"]
    assert legacy_result["matched_rule"] == (
        "supports_rag_improves_reliability"
    )
    assert legacy_result["abstention_reason"] is None
    assert legacy_result["evidence"][0][
        "evidence_id"
    ] == "seed-002"


def test_verification_run_rejects_empty_claim():
    """A verifier execution must identify its claim."""

    with pytest.raises(
        VerificationRunError,
        match="claim cannot be empty",
    ):
        VerificationRun(
            claim="   ",
            result=build_supported_result(),
        )


def test_verification_run_rejects_invalid_result():
    """The run must contain a validated result."""

    with pytest.raises(
        VerificationRunError,
        match="VerificationResult",
    ):
        VerificationRun(
            claim="A valid claim.",
            result={},
        )


def test_rule_verifier_implements_shared_interface():
    """RuleVerifier should satisfy the runtime protocol."""

    rule_verifier = RuleVerifier(
        evidence_db=[],
        verification_rules=[],
        model=object(),
        evidence_embeddings=object(),
    )

    assert isinstance(
        rule_verifier,
        Verifier,
    )
    assert (
        rule_verifier.verifier_type
        == VerifierType.RULE
    )


def test_rule_verifier_wraps_legacy_core(
    monkeypatch: pytest.MonkeyPatch,
):
    """RuleVerifier should return a unified VerificationRun."""

    captured_arguments: Dict[str, Any] = {}

    legacy_result = {
        "claim": (
            "Retrieval augmented generation can "
            "improve factual reliability."
        ),
        "label": "Supported",
        "confidence": 0.86,
        "evidence": [
            {
                "evidence_id": "seed-002",
                "title": (
                    "Retrieval Augmented Generation"
                ),
                "text": (
                    "RAG can improve factual reliability."
                ),
            }
        ],
        "matched_evidence_ids": [
            "seed-002",
        ],
        "matched_rule": (
            "supports_rag_improves_reliability"
        ),
        "abstention_reason": None,
    }

    def fake_verify_claim(**kwargs):
        captured_arguments.update(kwargs)
        return legacy_result

    monkeypatch.setattr(
        rule_module.core_verifier,
        "verify_claim",
        fake_verify_claim,
    )

    evidence_db = [
        {
            "title": "Test Evidence",
            "text": "Test evidence text.",
        }
    ]
    rules = [
        {
            "name": "test-rule",
        }
    ]
    model = object()
    embeddings = object()

    rule_verifier = RuleVerifier(
        evidence_db=evidence_db,
        verification_rules=rules,
        model=model,
        evidence_embeddings=embeddings,
    )

    run = rule_verifier.verify(
        legacy_result["claim"]
    )

    assert isinstance(
        run,
        VerificationRun,
    )
    assert run.result.label.value == "Supported"
    assert (
        run.result.verifier_type
        == VerifierType.RULE
    )
    assert run.result.matched_evidence_ids == (
        "seed-002",
    )
    assert run.evidence[0]["evidence_id"] == (
        "seed-002"
    )

    assert (
        captured_arguments["evidence_db"]
        is evidence_db
    )
    assert (
        captured_arguments[
            "verification_rules"
        ]
        is rules
    )
    assert captured_arguments["model"] is model
    assert (
        captured_arguments[
            "evidence_embeddings"
        ]
        is embeddings
    )


def test_future_llm_verifier_can_use_same_interface():
    """A future LLM verifier can return the same run type."""

    class FakeLLMVerifier:
        """Minimal implementation of the protocol."""

        verifier_type = VerifierType.LLM

        def verify(
            self,
            claim: str,
        ) -> VerificationRun:
            result = VerificationResult(
                label="Uncertain",
                confidence=0.5,
                reason=(
                    "The supplied evidence is insufficient."
                ),
                verifier_type="llm",
                abstention_reason=(
                    "Insufficient evidence."
                ),
            )

            return VerificationRun(
                claim=claim,
                result=result,
                evidence=(),
            )

    llm_verifier = FakeLLMVerifier()

    assert isinstance(
        llm_verifier,
        Verifier,
    )

    run = llm_verifier.verify(
        "A test claim."
    )

    assert (
        run.result.verifier_type
        == VerifierType.LLM
    )
    assert run.result.label.value == "Uncertain"
