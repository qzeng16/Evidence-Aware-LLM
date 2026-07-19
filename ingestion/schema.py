"""Schema definitions and validation for evidence ingestion records.

The ingestion schema contains richer source metadata than the runtime
verifier currently requires. The verifier remains compatible because it
continues to depend only on the ``title`` and ``text`` columns.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


REQUIRED_FIELDS = [
    "evidence_id",
    "title",
    "text",
    "source_name",
    "source_type",
    "topic",
]

OPTIONAL_FIELDS = [
    "source_url",
    "published_at",
    "retrieved_at",
]

ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

SUPPORTED_SOURCE_TYPES = {
    "paper",
    "documentation",
    "report",
    "article",
    "dataset",
    "book",
    "other",
}

EVIDENCE_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{2,99}$"
)

MIN_TITLE_LENGTH = 5
MAX_TITLE_LENGTH = 300

MIN_TEXT_LENGTH = 20
MAX_TEXT_LENGTH = 10000

MIN_SOURCE_NAME_LENGTH = 2
MAX_SOURCE_NAME_LENGTH = 200

MIN_TOPIC_LENGTH = 2
MAX_TOPIC_LENGTH = 100


@dataclass
class EvidenceRecord:
    """Canonical record used by the evidence ingestion pipeline."""

    evidence_id: str
    title: str
    text: str
    source_name: str
    source_type: str
    topic: str
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, str]:
        """Convert the record to a CSV-serializable dictionary."""

        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "text": self.text,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "topic": self.topic,
            "source_url": self.source_url or "",
            "published_at": self.published_at or "",
            "retrieved_at": self.retrieved_at or "",
        }


def normalize_string(value: Any) -> str:
    """Convert a value to a stripped string."""

    if value is None:
        return ""

    return str(value).strip()


def find_missing_required_fields(
    record: Dict[str, Any],
) -> List[str]:
    """Return required fields that are missing or empty."""

    missing_fields = []

    for field_name in REQUIRED_FIELDS:
        value = normalize_string(record.get(field_name))

        if not value:
            missing_fields.append(field_name)

    return missing_fields


def validate_source_type(source_type: Any) -> bool:
    """Return whether the source type is supported."""

    normalized_source_type = normalize_string(
        source_type
    ).lower()

    return normalized_source_type in SUPPORTED_SOURCE_TYPES


def validate_evidence_id(evidence_id: Any) -> bool:
    """Return whether the evidence ID uses the canonical format."""

    normalized_id = normalize_string(evidence_id).lower()

    return bool(EVIDENCE_ID_PATTERN.fullmatch(normalized_id))


def validate_url(url: Any) -> bool:
    """Validate an optional HTTP or HTTPS URL."""

    normalized_url = normalize_string(url)

    if not normalized_url:
        return True

    parsed_url = urlparse(normalized_url)

    return (
        parsed_url.scheme in {"http", "https"}
        and bool(parsed_url.netloc)
    )


def validate_iso_date(value: Any) -> bool:
    """Validate an optional ISO date in YYYY-MM-DD format."""

    normalized_value = normalize_string(value)

    if not normalized_value:
        return True

    try:
        parsed_date = datetime.strptime(
            normalized_value,
            "%Y-%m-%d",
        )
    except ValueError:
        return False

    return parsed_date.strftime("%Y-%m-%d") == normalized_value


def validate_length(
    value: str,
    minimum: int,
    maximum: int,
) -> bool:
    """Return whether a string is within an allowed length range."""

    return minimum <= len(value) <= maximum


def build_evidence_record(
    record: Dict[str, Any],
) -> EvidenceRecord:
    """Validate a dictionary and convert it to an EvidenceRecord.

    Raises:
        ValueError: If one or more validation rules fail.
    """

    missing_fields = find_missing_required_fields(record)

    if missing_fields:
        missing_text = ", ".join(sorted(missing_fields))
        raise ValueError(
            "Evidence record is missing required fields: "
            f"{missing_text}"
        )

    evidence_id = normalize_string(
        record["evidence_id"]
    ).lower()

    title = normalize_string(record["title"])
    text = normalize_string(record["text"])
    source_name = normalize_string(record["source_name"])
    source_type = normalize_string(
        record["source_type"]
    ).lower()
    topic = normalize_string(record["topic"]).lower()

    source_url = (
        normalize_string(record.get("source_url")) or None
    )
    published_at = (
        normalize_string(record.get("published_at")) or None
    )
    retrieved_at = (
        normalize_string(record.get("retrieved_at")) or None
    )

    validation_errors = []

    if not validate_evidence_id(evidence_id):
        validation_errors.append(
            "evidence_id must contain 3 to 100 lowercase "
            "letters, numbers, periods, underscores, or hyphens"
        )

    if not validate_length(
        title,
        MIN_TITLE_LENGTH,
        MAX_TITLE_LENGTH,
    ):
        validation_errors.append(
            "title must contain between "
            f"{MIN_TITLE_LENGTH} and {MAX_TITLE_LENGTH} characters"
        )

    if not validate_length(
        text,
        MIN_TEXT_LENGTH,
        MAX_TEXT_LENGTH,
    ):
        validation_errors.append(
            "text must contain between "
            f"{MIN_TEXT_LENGTH} and {MAX_TEXT_LENGTH} characters"
        )

    if not validate_length(
        source_name,
        MIN_SOURCE_NAME_LENGTH,
        MAX_SOURCE_NAME_LENGTH,
    ):
        validation_errors.append(
            "source_name must contain between "
            f"{MIN_SOURCE_NAME_LENGTH} and "
            f"{MAX_SOURCE_NAME_LENGTH} characters"
        )

    if not validate_length(
        topic,
        MIN_TOPIC_LENGTH,
        MAX_TOPIC_LENGTH,
    ):
        validation_errors.append(
            "topic must contain between "
            f"{MIN_TOPIC_LENGTH} and {MAX_TOPIC_LENGTH} characters"
        )

    if not validate_source_type(source_type):
        supported_types = ", ".join(
            sorted(SUPPORTED_SOURCE_TYPES)
        )
        validation_errors.append(
            f"unsupported source_type '{source_type}'; "
            f"supported values: {supported_types}"
        )

    if not validate_url(source_url):
        validation_errors.append(
            "source_url must be empty or use a valid "
            "http:// or https:// URL"
        )

    if not validate_iso_date(published_at):
        validation_errors.append(
            "published_at must be empty or use YYYY-MM-DD"
        )

    if not validate_iso_date(retrieved_at):
        validation_errors.append(
            "retrieved_at must be empty or use YYYY-MM-DD"
        )

    if validation_errors:
        raise ValueError("; ".join(validation_errors))

    return EvidenceRecord(
        evidence_id=evidence_id,
        title=title,
        text=text,
        source_name=source_name,
        source_type=source_type,
        topic=topic,
        source_url=source_url,
        published_at=published_at,
        retrieved_at=retrieved_at,
    )
