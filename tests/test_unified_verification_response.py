"""Tests for the unified verification service response."""

from typing import Optional

import pytest

from app.config import (
    RULE_ONLY_MODE,
    AppConfig,
)
from app.verification_result import (
    VerificationResult,
    VerifierType,
)
from app.verifiers.base import VerificationRun
import app.services as services


class FakeRuleVerifier:
    """Small verifier used to isolate service tests."""

    verifier_type = VerifierType.RULE

    def __init__(
        self,
        verification_run: VerificationRun,
    ) -> None:
        self.verification_run = verification_run
        self.received_claim: Optional[str] = None

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        self.received_claim = claim

        return self.verification_run


@pytest.fixture(autouse=True)
def reset_service_state():
    """Prevent service state from leaking between tests."""

    services.reset_service_state()

    yield

    services.reset_service_state()


def build_verification_run() -> VerificationRun:
    """Build a unified rule-verifier execution."""

    claim = (
        "Retrieval augmented generation can "
        "improve factual reliability."
    )

    result = VerificationResult(
        label="Supported",
        confidence=0.86,
        reason=(
            "Rule "
            "'supports_rag_improves_reliability' "
            "matched retrieved evidence that "
            "supports the claim."
        ),
        verifier_type="rule",
        matched_evidence_ids=(
            "seed-002",
        ),
        matched_rule=(
            "supports_rag_improves_reliability"
        ),
    )

    return VerificationRun(
        claim=claim,
        result=result,
        evidence=(
            {
                "evidence_id": "seed-002",
                "title": (
                    "Retrieval Augmented Generation"
                ),
                "text": (
                    "RAG can improve factual reliability "
                    "by grounding answers in documents."
                ),
            },
        ),
    )


def prepare_ready_service(
    active_verifier: FakeRuleVerifier,
) -> None:
    """Populate the state required by the API service."""

    services.system_state.update(
        {
            "evidence_db": [],
            "verification_rules": [],
            "model": object(),
            "evidence_embeddings": object(),
            "config": AppConfig(
                verifier_mode=RULE_ONLY_MODE
            ),
            "active_verifier": active_verifier,
            "initialization_error": None,
        }
    )


def test_service_calls_active_verifier_interface(
    monkeypatch: pytest.MonkeyPatch,
):
    """The service should call active_verifier.verify()."""

    verification_run = build_verification_run()

    active_verifier = FakeRuleVerifier(
        verification_run
    )

    prepare_ready_service(active_verifier)

    monkeypatch.setattr(
        services.verifier,
        "validate_claim",
        lambda claim: (
            True,
            "",
        ),
    )

    def fail_if_legacy_core_is_called(**kwargs):
        del kwargs

        raise AssertionError(
            "Service called the legacy core directly."
        )

    monkeypatch.setattr(
        services.verifier,
        "verify_claim",
        fail_if_legacy_core_is_called,
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: None,
    )

    response = services.verify_claim_service(
        verification_run.claim
    )

    assert (
        active_verifier.received_claim
        == verification_run.claim
    )

    assert response["status"] == "success"


def test_service_returns_legacy_and_unified_results(
    monkeypatch: pytest.MonkeyPatch,
):
    """The old prediction and new verification should coexist."""

    verification_run = build_verification_run()

    active_verifier = FakeRuleVerifier(
        verification_run
    )

    prepare_ready_service(active_verifier)

    monkeypatch.setattr(
        services.verifier,
        "validate_claim",
        lambda claim: (
            True,
            "",
        ),
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: None,
    )

    response = services.verify_claim_service(
        verification_run.claim
    )

    assert response["status"] == "success"

    assert response["data"]["prediction"] == {
        "label": "Supported",
        "confidence": 0.86,
    }

    verification = response["data"][
        "verification"
    ]

    assert verification["label"] == "Supported"
    assert verification["confidence"] == 0.86
    assert verification["verifier_type"] == "rule"

    assert verification[
        "matched_evidence_ids"
    ] == ["seed-002"]

    assert verification["matched_rule"] == (
        "supports_rag_improves_reliability"
    )

    assert verification[
        "abstention_reason"
    ] is None

    assert verification["reason"]

    assert response["data"]["evidence"][0][
        "evidence_id"
    ] == "seed-002"

    assert response["metadata"][
        "active_verifier_mode"
    ] == "rule"


def test_invalid_claim_does_not_call_active_verifier(
    monkeypatch: pytest.MonkeyPatch,
):
    """Input validation should run before the verifier."""

    verification_run = build_verification_run()

    active_verifier = FakeRuleVerifier(
        verification_run
    )

    prepare_ready_service(active_verifier)

    monkeypatch.setattr(
        services.verifier,
        "validate_claim",
        lambda claim: (
            False,
            "Claim cannot be empty.",
        ),
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: None,
    )

    response = services.verify_claim_service("")

    assert response["status"] == "error"
    assert active_verifier.received_claim is None


def test_service_requires_active_verifier(
    monkeypatch: pytest.MonkeyPatch,
):
    """Resources without a verifier should not be ready."""

    services.system_state.update(
        {
            "evidence_db": [],
            "verification_rules": [],
            "model": object(),
            "evidence_embeddings": object(),
            "config": AppConfig(
                verifier_mode=RULE_ONLY_MODE
            ),
            "active_verifier": None,
            "initialization_error": None,
        }
    )

    monkeypatch.setattr(
        services.verifier,
        "save_log",
        lambda response: None,
    )

    assert services.is_service_ready() is False

    response = services.verify_claim_service(
        "A valid test claim."
    )

    assert response["status"] == "error"
    assert response["error"]["message"] == (
        "Service is not ready."
    )
