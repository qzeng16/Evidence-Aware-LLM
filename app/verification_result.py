"""Shared verification result contract.

Rule-based, LLM-based, and hybrid verifiers should all produce this
structure before their results are serialized into an API response.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Tuple, Type, TypeVar


class VerificationResultError(ValueError):
    """Raised when a verification result is invalid."""


class VerificationLabel(str, Enum):
    """Labels supported by every verifier implementation."""

    SUPPORTED = "Supported"
    REFUTED = "Refuted"
    UNCERTAIN = "Uncertain"


class VerifierType(str, Enum):
    """Verifier implementations supported by the application."""

    RULE = "rule"
    LLM = "llm"
    HYBRID = "hybrid"


EnumType = TypeVar("EnumType", bound=Enum)


def _normalize_enum(
    value: Any,
    enum_type: Type[EnumType],
    field_name: str,
) -> EnumType:
    """Convert a string or enum instance into a validated enum."""

    if isinstance(value, enum_type):
        return value

    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        allowed_values = ", ".join(
            item.value
            for item in enum_type
        )

        raise VerificationResultError(
            f"Invalid {field_name} '{value}'. "
            f"Allowed values: {allowed_values}"
        ) from error


def _normalize_optional_text(
    value: Optional[str],
) -> Optional[str]:
    """Normalize optional text fields."""

    if value is None:
        return None

    normalized_value = value.strip()

    if not normalized_value:
        return None

    return normalized_value


def _normalize_evidence_ids(
    values: Iterable[str],
) -> Tuple[str, ...]:
    """Normalize evidence IDs while preserving order."""

    normalized_ids = []
    seen_ids = set()

    for value in values:
        normalized_value = str(value).strip()

        if not normalized_value:
            continue

        if normalized_value in seen_ids:
            continue

        seen_ids.add(normalized_value)
        normalized_ids.append(normalized_value)

    return tuple(normalized_ids)


@dataclass(frozen=True)
class VerificationResult:
    """Validated result returned by any verifier implementation."""

    label: VerificationLabel
    confidence: float
    reason: str
    verifier_type: VerifierType
    matched_evidence_ids: Tuple[str, ...] = ()
    matched_rule: Optional[str] = None
    abstention_reason: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize and validate result fields."""

        normalized_label = _normalize_enum(
            self.label,
            VerificationLabel,
            "verification label",
        )

        normalized_verifier_type = _normalize_enum(
            self.verifier_type,
            VerifierType,
            "verifier type",
        )

        try:
            normalized_confidence = float(
                self.confidence
            )
        except (TypeError, ValueError) as error:
            raise VerificationResultError(
                "Confidence must be a number."
            ) from error

        if not 0.0 <= normalized_confidence <= 1.0:
            raise VerificationResultError(
                "Confidence must be between 0.0 and 1.0."
            )

        normalized_reason = str(self.reason).strip()

        if not normalized_reason:
            raise VerificationResultError(
                "Verification reason cannot be empty."
            )

        normalized_evidence_ids = (
            _normalize_evidence_ids(
                self.matched_evidence_ids
            )
        )

        normalized_matched_rule = (
            _normalize_optional_text(
                self.matched_rule
            )
        )

        normalized_abstention_reason = (
            _normalize_optional_text(
                self.abstention_reason
            )
        )

        if (
            normalized_label
            != VerificationLabel.UNCERTAIN
            and normalized_abstention_reason is not None
        ):
            raise VerificationResultError(
                "Only an Uncertain result may contain "
                "an abstention reason."
            )

        object.__setattr__(
            self,
            "label",
            normalized_label,
        )
        object.__setattr__(
            self,
            "confidence",
            normalized_confidence,
        )
        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )
        object.__setattr__(
            self,
            "verifier_type",
            normalized_verifier_type,
        )
        object.__setattr__(
            self,
            "matched_evidence_ids",
            normalized_evidence_ids,
        )
        object.__setattr__(
            self,
            "matched_rule",
            normalized_matched_rule,
        )
        object.__setattr__(
            self,
            "abstention_reason",
            normalized_abstention_reason,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the result into a JSON-compatible dictionary."""

        return {
            "label": self.label.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "verifier_type": self.verifier_type.value,
            "matched_evidence_ids": list(
                self.matched_evidence_ids
            ),
            "matched_rule": self.matched_rule,
            "abstention_reason": (
                self.abstention_reason
            ),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Dict[str, Any],
    ) -> "VerificationResult":
        """Create a validated result from a dictionary."""

        required_fields = {
            "label",
            "confidence",
            "reason",
            "verifier_type",
        }

        missing_fields = (
            required_fields - set(payload)
        )

        if missing_fields:
            raise VerificationResultError(
                "Verification result is missing fields: "
                f"{sorted(missing_fields)}"
            )

        return cls(
            label=payload["label"],
            confidence=payload["confidence"],
            reason=payload["reason"],
            verifier_type=payload["verifier_type"],
            matched_evidence_ids=tuple(
                payload.get(
                    "matched_evidence_ids",
                    [],
                )
            ),
            matched_rule=payload.get(
                "matched_rule"
            ),
            abstention_reason=payload.get(
                "abstention_reason"
            ),
        )
