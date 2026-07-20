"""Shared interface for verifier implementations."""

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    Mapping,
    Protocol,
    Tuple,
    runtime_checkable,
)

from app.verification_result import (
    VerificationResult,
    VerifierType,
)


class VerificationRunError(ValueError):
    """Raised when a verifier execution result is invalid."""


def _normalize_evidence(
    evidence_items: Iterable[Mapping[str, Any]],
) -> Tuple[Dict[str, Any], ...]:
    """Normalize evidence records into independent dictionaries."""

    normalized_items = []

    for item in evidence_items:
        if not isinstance(item, Mapping):
            raise VerificationRunError(
                "Every evidence item must be a mapping."
            )

        normalized_items.append(dict(item))

    return tuple(normalized_items)


@dataclass(frozen=True)
class VerificationRun:
    """Complete output from one verifier execution.

    ``VerificationResult`` contains the actual decision.

    ``evidence`` contains the retrieved evidence shown to the
    verifier and returned through the API.
    """

    claim: str
    result: VerificationResult
    evidence: Tuple[Dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        """Normalize and validate execution fields."""

        normalized_claim = str(self.claim).strip()

        if not normalized_claim:
            raise VerificationRunError(
                "Verification claim cannot be empty."
            )

        if not isinstance(
            self.result,
            VerificationResult,
        ):
            raise VerificationRunError(
                "result must be a VerificationResult."
            )

        normalized_evidence = _normalize_evidence(
            self.evidence
        )

        object.__setattr__(
            self,
            "claim",
            normalized_claim,
        )
        object.__setattr__(
            self,
            "evidence",
            normalized_evidence,
        )

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convert the unified run into the legacy result format.

        This method lets the existing response builder keep working
        while the project transitions to the new interface.
        """

        result_payload = self.result.to_dict()

        return {
            "claim": self.claim,
            "label": result_payload["label"],
            "confidence": result_payload["confidence"],
            "evidence": [
                dict(item)
                for item in self.evidence
            ],
            "matched_evidence_ids": result_payload[
                "matched_evidence_ids"
            ],
            "matched_rule": result_payload[
                "matched_rule"
            ],
            "abstention_reason": result_payload[
                "abstention_reason"
            ],
        }


@runtime_checkable
class Verifier(Protocol):
    """Interface implemented by all verifier backends."""

    @property
    def verifier_type(self) -> VerifierType:
        """Return the implementation type."""

        ...

    def verify(
        self,
        claim: str,
    ) -> VerificationRun:
        """Verify one claim and return a unified execution result."""

        ...
