"""Build the runtime evidence corpus from JSONL source records.

The script performs:

1. JSONL parsing
2. Evidence schema validation
3. Text normalization
4. Duplicate ID detection
5. Duplicate content detection
6. Deterministic sorting
7. Atomic CSV output
8. Optional JSON ingestion report

Examples:

    python3 scripts/ingest_evidence.py

    python3 scripts/ingest_evidence.py --dry-run

    python3 scripts/ingest_evidence.py \
        --report /tmp/ingestion_report.json
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_PATH = (
    PROJECT_ROOT / "data" / "raw" / "evidence_seed.jsonl"
)
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "evidence.csv"


if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.schema import (
    ALL_FIELDS,
    EvidenceRecord,
    build_evidence_record,
)


class IngestionError(Exception):
    """Raised when evidence ingestion cannot continue."""


def normalize_whitespace(value: Any) -> str:
    """Convert a value to text and collapse repeated whitespace."""

    if value is None:
        return ""

    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


def normalize_raw_record(
    record: Dict[str, Any],
) -> Dict[str, str]:
    """Normalize recognized fields before schema validation."""

    normalized = {}

    for field_name in ALL_FIELDS:
        normalized[field_name] = normalize_whitespace(
            record.get(field_name)
        )

    normalized["evidence_id"] = (
        normalized["evidence_id"].lower()
    )
    normalized["source_type"] = (
        normalized["source_type"].lower()
    )
    normalized["topic"] = normalized["topic"].lower()

    return normalized


def build_content_fingerprint(
    record: EvidenceRecord,
) -> str:
    """Return a stable fingerprint for duplicate detection."""

    canonical_text = (
        normalize_whitespace(record.title).lower()
        + "\n"
        + normalize_whitespace(record.text).lower()
    )

    return hashlib.sha256(
        canonical_text.encode("utf-8")
    ).hexdigest()


def read_jsonl_records(
    input_path: Path,
) -> Tuple[List[EvidenceRecord], Dict[str, Any]]:
    """Read, validate, normalize, and deduplicate JSONL records."""

    if not input_path.exists():
        raise IngestionError(
            f"Input file does not exist: {input_path}"
        )

    if not input_path.is_file():
        raise IngestionError(
            f"Input path is not a file: {input_path}"
        )

    accepted_records = []
    records_by_id = {}
    seen_content_fingerprints = set()
    content_owner_by_fingerprint = {}

    report = {
        "non_empty_lines": 0,
        "accepted_records": 0,
        "duplicate_ids_skipped": 0,
        "duplicate_content_skipped": 0,
        "accepted_evidence_ids": [],
        "duplicate_id_details": [],
        "duplicate_content_details": [],
    }

    with input_path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            stripped_line = raw_line.strip()

            if not stripped_line:
                continue

            report["non_empty_lines"] += 1

            try:
                raw_record = json.loads(stripped_line)
            except json.JSONDecodeError as error:
                raise IngestionError(
                    f"Invalid JSON on line {line_number}: {error}"
                )

            if not isinstance(raw_record, dict):
                raise IngestionError(
                    f"Line {line_number} must contain a JSON object."
                )

            normalized_record = normalize_raw_record(raw_record)

            try:
                evidence_record = build_evidence_record(
                    normalized_record
                )
            except ValueError as error:
                raise IngestionError(
                    f"Invalid evidence on line {line_number}: "
                    f"{error}"
                )

            existing_record = records_by_id.get(
                evidence_record.evidence_id
            )

            if existing_record is not None:
                if (
                    existing_record.to_dict()
                    == evidence_record.to_dict()
                ):
                    report["duplicate_ids_skipped"] += 1
                    report["duplicate_id_details"].append(
                        {
                            "line_number": line_number,
                            "evidence_id": (
                                evidence_record.evidence_id
                            ),
                        }
                    )
                    continue

                raise IngestionError(
                    "Conflicting records use the same evidence_id "
                    f"'{evidence_record.evidence_id}'. "
                    f"Conflict found on line {line_number}."
                )

            content_fingerprint = build_content_fingerprint(
                evidence_record
            )

            if content_fingerprint in seen_content_fingerprints:
                original_id = content_owner_by_fingerprint[
                    content_fingerprint
                ]

                report["duplicate_content_skipped"] += 1
                report["duplicate_content_details"].append(
                    {
                        "line_number": line_number,
                        "skipped_evidence_id": (
                            evidence_record.evidence_id
                        ),
                        "original_evidence_id": original_id,
                    }
                )
                continue

            records_by_id[evidence_record.evidence_id] = (
                evidence_record
            )
            seen_content_fingerprints.add(content_fingerprint)
            content_owner_by_fingerprint[
                content_fingerprint
            ] = evidence_record.evidence_id

            accepted_records.append(evidence_record)

    if not accepted_records:
        raise IngestionError(
            "No valid evidence records were found."
        )

    accepted_records.sort(
        key=lambda record: (
            record.topic.lower(),
            record.source_name.lower(),
            record.evidence_id.lower(),
        )
    )

    report["accepted_records"] = len(accepted_records)
    report["accepted_evidence_ids"] = [
        record.evidence_id
        for record in accepted_records
    ]

    return accepted_records, report


def create_temporary_file(
    destination_path: Path,
    mode: str,
):
    """Create a temporary file beside its final destination."""

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return tempfile.NamedTemporaryFile(
        mode=mode,
        encoding="utf-8",
        newline="",
        delete=False,
        dir=str(destination_path.parent),
        prefix=f"{destination_path.name}.",
        suffix=".tmp",
    )


def write_csv_atomically(
    records: List[EvidenceRecord],
    output_path: Path,
) -> None:
    """Write evidence records using atomic file replacement."""

    temporary_path = None

    try:
        with create_temporary_file(
            destination_path=output_path,
            mode="w",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            writer = csv.DictWriter(
                temporary_file,
                fieldnames=ALL_FIELDS,
                extrasaction="ignore",
            )

            writer.writeheader()

            for record in records:
                writer.writerow(record.to_dict())

        os.replace(
            str(temporary_path),
            str(output_path),
        )

    except Exception:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise


def write_json_atomically(
    payload: Dict[str, Any],
    output_path: Path,
) -> None:
    """Write a JSON document using atomic file replacement."""

    temporary_path = None

    try:
        with create_temporary_file(
            destination_path=output_path,
            mode="w",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            json.dump(
                payload,
                temporary_file,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            temporary_file.write("\n")

        os.replace(
            str(temporary_path),
            str(output_path),
        )

    except Exception:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise


def build_report_payload(
    input_path: Path,
    output_path: Path,
    report: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    """Build the complete ingestion report payload."""

    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "dry_run": dry_run,
        "statistics": {
            "non_empty_lines": report[
                "non_empty_lines"
            ],
            "accepted_records": report[
                "accepted_records"
            ],
            "duplicate_ids_skipped": report[
                "duplicate_ids_skipped"
            ],
            "duplicate_content_skipped": report[
                "duplicate_content_skipped"
            ],
        },
        "accepted_evidence_ids": report[
            "accepted_evidence_ids"
        ],
        "duplicate_id_details": report[
            "duplicate_id_details"
        ],
        "duplicate_content_details": report[
            "duplicate_content_details"
        ],
    }


def print_summary(
    input_path: Path,
    output_path: Path,
    report: Dict[str, Any],
    dry_run: bool,
    report_path: Optional[Path],
) -> None:
    """Print a human-readable ingestion summary."""

    print("Evidence ingestion summary")
    print("--------------------------")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(
        "Non-empty input lines: "
        f"{report['non_empty_lines']}"
    )
    print(
        "Accepted records: "
        f"{report['accepted_records']}"
    )
    print(
        "Duplicate IDs skipped: "
        f"{report['duplicate_ids_skipped']}"
    )
    print(
        "Duplicate content skipped: "
        f"{report['duplicate_content_skipped']}"
    )
    print(f"Dry run: {'yes' if dry_run else 'no'}")

    if report_path is not None:
        print(f"Report: {report_path}")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate JSONL evidence and build evidence.csv."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=(
            "Path to the source JSONL file. "
            f"Default: {DEFAULT_INPUT_PATH}"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "Path to the generated CSV file. "
            f"Default: {DEFAULT_OUTPUT_PATH}"
        ),
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help=(
            "Optional path for a JSON ingestion report."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate input without writing the evidence CSV."
        ),
    )

    return parser.parse_args()


def main() -> int:
    """Run the evidence ingestion process."""

    arguments = parse_arguments()

    input_path = arguments.input.expanduser().resolve()
    output_path = arguments.output.expanduser().resolve()

    report_path = None

    if arguments.report is not None:
        report_path = arguments.report.expanduser().resolve()

    try:
        records, report = read_jsonl_records(input_path)

        if not arguments.dry_run:
            write_csv_atomically(records, output_path)

        report_payload = build_report_payload(
            input_path=input_path,
            output_path=output_path,
            report=report,
            dry_run=arguments.dry_run,
        )

        if report_path is not None:
            write_json_atomically(
                report_payload,
                report_path,
            )

        print_summary(
            input_path=input_path,
            output_path=output_path,
            report=report,
            dry_run=arguments.dry_run,
            report_path=report_path,
        )

    except IngestionError as error:
        print(
            f"Evidence ingestion failed: {error}",
            file=sys.stderr,
        )
        return 1

    except OSError as error:
        print(
            "Evidence ingestion failed due to a file error: "
            f"{error}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
