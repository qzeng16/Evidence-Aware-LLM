"""Tests for the complete hybrid verification policy."""

from typing import Optional

import pytest

from app.llm_clients import (
    LLMClientError,
)
from app.verification_result import (
    VerificationLabel,
    VerificationResult,
    VerifierType,
)
from app.verifiers import (
    HybridVerifier,
    VerificationRun,
    Verifier,
)


class StubVerifier:
    """Deterministic verifier used by hybrid tests."""

    def __init__(
        self,
        verifier_type: VerifierType,
        run: Optional[VerificationRun] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.verifier_type = verifier_type
        self.run = run
        self.error = error
        self.call_count = 0
        self.received_claim = None

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        self.call_count += 1
        self.received_claim = claim

        if self.error is not None:
            raise self.error

        if self.run is None:
            raise AssertionError(
                "StubVerifier has no configured run."
            )

        return self.run


def build_run(
    label: VerificationLabel,
    confidence: float,
    verifier_type: VerifierType,
    evidence_id: Optional[str],
    reason: str,
    matched_rule: Optional[str] = None,
) -> VerificationRun:
    """Build one deterministic verifier run."""

    evidence_ids = (
        (evidence_id,)
        if evidence_id
        else ()
    )

    evidence = (
        (
            {
                "evidence_id": evidence_id,
                "title": (
                    f"Evidence {evidence_id}"
                ),
                "text": reason,
            },
        )
        if evidence_id
        else ()
    )

    abstention_reason = (
        "insufficient_evidence"
        if label
        == VerificationLabel.UNCERTAIN
        else None
    )

    result = VerificationResult(
        label=label,
        confidence=confidence,
        reason=reason,
        verifier_type=verifier_type,
        matched_evidence_ids=evidence_ids,
        matched_rule=matched_rule,
        abstention_reason=(
            abstention_reason
        ),
    )

    return VerificationRun(
        claim="Test claim",
        result=result,
        evidence=evidence,
    )


def test_hybrid_verifier_implements_interface():
    """HybridVerifier should satisfy the shared protocol."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.97,
            VerifierType.RULE,
            "rule-001",
            "Strong rule evidence.",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.9,
            VerifierType.LLM,
            "llm-001",
            "Strong LLM evidence.",
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    assert isinstance(verifier, Verifier)
    assert (
        verifier.verifier_type
        == VerifierType.HYBRID
    )


def test_high_confidence_rule_short_circuits_llm():
    """High-confidence rule results should avoid an LLM call."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.97,
            VerifierType.RULE,
            "rule-001",
            "A high-confidence rule matched.",
            matched_rule="support_rule",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        error=AssertionError(
            "LLM should not be called."
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    result = verifier.verify(
        "Test claim"
    )

    assert (
        result.result.label
        == VerificationLabel.SUPPORTED
    )
    assert result.result.confidence == 0.97
    assert (
        result.result.verifier_type
        == VerifierType.HYBRID
    )
    assert result.result.matched_rule == (
        "support_rule"
    )
    assert llm.call_count == 0


def test_agreement_combines_confidence():
    """Agreement should combine evidence and add a bonus."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.8,
            VerifierType.RULE,
            "rule-001",
            "Rule supports the claim.",
            matched_rule="support_rule",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.9,
            VerifierType.LLM,
            "llm-001",
            "LLM supports the claim.",
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    result = verifier.verify(
        "Test claim"
    )

    assert (
        result.result.label
        == VerificationLabel.SUPPORTED
    )
    assert result.result.confidence == 0.9
    assert (
        result.result.matched_evidence_ids
        == (
            "rule-001",
            "llm-001",
        )
    )
    assert len(result.evidence) == 2
    assert llm.call_count == 1


def test_one_decisive_result_is_discounted():
    """A single decisive result should be retained cautiously."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.UNCERTAIN,
            0.4,
            VerifierType.RULE,
            None,
            "Rule evidence was insufficient.",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.9,
            VerifierType.LLM,
            "llm-001",
            "LLM evidence directly supports it.",
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    result = verifier.verify(
        "Test claim"
    )

    assert (
        result.result.label
        == VerificationLabel.SUPPORTED
    )
    assert result.result.confidence == 0.81
    assert (
        result.result.matched_evidence_ids
        == ("llm-001",)
    )


def test_conflicting_decisive_results_abstain():
    """Conflicting decisive results should become Uncertain."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.8,
            VerifierType.RULE,
            "rule-001",
            "Rule supports the claim.",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        run=build_run(
            VerificationLabel.REFUTED,
            0.9,
            VerifierType.LLM,
            "llm-001",
            "LLM evidence refutes the claim.",
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    result = verifier.verify(
        "Test claim"
    )

    assert (
        result.result.label
        == VerificationLabel.UNCERTAIN
    )
    assert result.result.confidence == 0.35
    assert result.result.abstention_reason == (
        "rule_llm_conflict"
    )
    assert (
        result.result.matched_evidence_ids
        == (
            "rule-001",
            "llm-001",
        )
    )


def test_llm_failure_falls_back_to_rule():
    """Expected provider failures should return the rule result."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.REFUTED,
            0.8,
            VerifierType.RULE,
            "rule-001",
            "Rule evidence refutes the claim.",
            matched_rule="refute_rule",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        error=LLMClientError(
            "Provider timeout.",
            error_code="request_timeout",
            retryable=True,
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    result = verifier.verify(
        "Test claim"
    )

    assert (
        result.result.label
        == VerificationLabel.REFUTED
    )
    assert result.result.confidence == 0.68
    assert (
        result.result.verifier_type
        == VerifierType.HYBRID
    )
    assert "request_timeout" in (
        result.result.reason
    )
    assert (
        result.result.abstention_reason
        is None
    )


def test_rule_uncertain_and_llm_failure_abstains():
    """No decisive fallback should remain Uncertain."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.UNCERTAIN,
            0.4,
            VerifierType.RULE,
            None,
            "Rule evidence was insufficient.",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        error=LLMClientError(
            "Provider timeout.",
            error_code="request_timeout",
            retryable=True,
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    result = verifier.verify(
        "Test claim"
    )

    assert (
        result.result.label
        == VerificationLabel.UNCERTAIN
    )
    assert result.result.confidence == 0.4
    assert result.result.abstention_reason == (
        "llm_unavailable_and_rule_uncertain"
    )


def test_duplicate_evidence_is_removed():
    """Evidence returned by both backends should not be duplicated."""

    shared_evidence = {
        "evidence_id": "shared-001",
        "title": "Shared Evidence",
        "text": "Shared evidence text.",
    }

    rule_run = build_run(
        VerificationLabel.SUPPORTED,
        0.8,
        VerifierType.RULE,
        "shared-001",
        "Rule supports the claim.",
    )

    llm_run = build_run(
        VerificationLabel.SUPPORTED,
        0.9,
        VerifierType.LLM,
        "shared-001",
        "LLM supports the claim.",
    )

    rule_run = VerificationRun(
        claim="Test claim",
        result=rule_run.result,
        evidence=(
            shared_evidence,
            {
                "evidence_id": "rule-only",
                "title": "Rule Evidence",
                "text": "Rule-only evidence.",
            },
        ),
    )

    llm_run = VerificationRun(
        claim="Test claim",
        result=llm_run.result,
        evidence=(
            dict(shared_evidence),
            {
                "evidence_id": "llm-only",
                "title": "LLM Evidence",
                "text": "LLM-only evidence.",
            },
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=StubVerifier(
            VerifierType.RULE,
            run=rule_run,
        ),
        llm_verifier=StubVerifier(
            VerifierType.LLM,
            run=llm_run,
        ),
    )

    result = verifier.verify(
        "Test claim"
    )

    returned_ids = [
        item["evidence_id"]
        for item in result.evidence
    ]

    assert returned_ids == [
        "shared-001",
        "rule-only",
        "llm-only",
    ]


@pytest.mark.parametrize(
    "field_name, value",
    [
        (
            "rule_short_circuit_confidence",
            1.1,
        ),
        (
            "agreement_bonus",
            -0.1,
        ),
        (
            "single_verifier_discount",
            2.0,
        ),
        (
            "llm_failure_discount",
            -1.0,
        ),
        (
            "conflict_confidence",
            1.5,
        ),
    ],
)
def test_invalid_policy_configuration_is_rejected(
    field_name,
    value,
):
    """All hybrid policy values must be probabilities."""

    rule = StubVerifier(
        VerifierType.RULE,
    )

    llm = StubVerifier(
        VerifierType.LLM,
    )

    with pytest.raises(
        ValueError,
        match=field_name,
    ):
        HybridVerifier(
            rule_verifier=rule,
            llm_verifier=llm,
            **{
                field_name: value,
            },
        )

def test_default_threshold_short_circuits_decisive_rule():
    """A 0.86 decisive rule result should avoid an LLM call."""

    rule = StubVerifier(
        verifier_type=VerifierType.RULE,
        run=build_run(
            VerificationLabel.SUPPORTED,
            0.86,
            VerifierType.RULE,
            "rule-086",
            "The rule verifier found direct support.",
            matched_rule="support_rule",
        ),
    )

    llm = StubVerifier(
        verifier_type=VerifierType.LLM,
        error=AssertionError(
            "LLM should not be called."
        ),
    )

    verifier = HybridVerifier(
        rule_verifier=rule,
        llm_verifier=llm,
    )

    run = verifier.verify(
        "A directly supported claim."
    )

    assert (
        run.result.label
        == VerificationLabel.SUPPORTED
    )
    assert run.result.confidence == 0.86
    assert (
        run.result.verifier_type
        == VerifierType.HYBRID
    )
    assert llm.call_count == 0

