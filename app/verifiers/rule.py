"""Rule-based implementation of the shared verifier interface."""

from typing import Any, Dict, List, Sequence

import layer0_verifier as core_verifier

from app.rule_verifier_adapter import (
    build_rule_verification_result,
)
from app.verification_result import VerifierType
from app.verifiers.base import VerificationRun


class RuleVerifier:
    """Wrap the legacy rule verifier behind the shared interface."""

    verifier_type = VerifierType.RULE

    def __init__(
        self,
        evidence_db: List[Dict[str, str]],
        verification_rules: List[Dict[str, Any]],
        model: Any,
        evidence_embeddings: Any,
    ) -> None:
        """Store dependencies required by the rule verifier."""

        self._evidence_db = evidence_db
        self._verification_rules = verification_rules
        self._model = model
        self._evidence_embeddings = (
            evidence_embeddings
        )

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        """Verify a claim through the legacy rule engine."""

        legacy_result = core_verifier.verify_claim(
            claim=claim,
            evidence_db=self._evidence_db,
            verification_rules=(
                self._verification_rules
            ),
            model=self._model,
            evidence_embeddings=(
                self._evidence_embeddings
            ),
        )

        verification_result = (
            build_rule_verification_result(
                legacy_result
            )
        )

        evidence: Sequence[Dict[str, Any]] = (
            legacy_result.get(
                "evidence",
                [],
            )
        )

        return VerificationRun(
            claim=legacy_result.get(
                "claim",
                claim,
            ),
            result=verification_result,
            evidence=tuple(evidence),
        )
