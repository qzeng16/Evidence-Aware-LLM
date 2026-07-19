"""Tests for evidence schema validation and ingestion."""

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from ingestion.schema import build_evidence_record


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INGESTION_SCRIPT = (
    PROJECT_ROOT / "scripts" / "ingest_evidence.py"
)


def build_valid_record(
    evidence_id: str = "test-001",
) -> dict:
    """Return a valid evidence dictionary for tests."""

    return {
        "evidence_id": evidence_id,
        "title": "Example Evidence Title",
        "text": (
            "This is a sufficiently long evidence statement "
            "used for ingestion testing."
        ),
        "source_name": "Test source",
        "source_type": "report",
        "topic": "testing",
        "source_url": "https://example.com/report",
        "published_at": "2026-01-15",
        "retrieved_at": "2026-07-19",
    }


def write_jsonl(
    path: Path,
    records: List[Dict[str, str]],
) -> None:
    """Write records to a JSONL file."""

    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )


def run_ingestion(
    input_path: Path,
    output_path: Path,
    report_path: Optional[Path] = None,
    dry_run: bool = False,
) -> subprocess.CompletedProcess:
    """Execute the ingestion CLI in a subprocess."""

    command = [
        sys.executable,
        str(INGESTION_SCRIPT),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]

    if report_path is not None:
        command.extend(
            [
                "--report",
                str(report_path),
            ]
        )

    if dry_run:
        command.append("--dry-run")

    return subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_schema_accepts_valid_record():
    record = build_evidence_record(
        build_valid_record()
    )

    assert record.evidence_id == "test-001"
    assert record.source_type == "report"
    assert record.topic == "testing"
    assert record.source_url == (
        "https://example.com/report"
    )


def test_schema_rejects_invalid_evidence_id():
    record = build_valid_record()
    record["evidence_id"] = "Invalid ID"

    with pytest.raises(
        ValueError,
        match="evidence_id",
    ):
        build_evidence_record(record)


def test_schema_rejects_invalid_url():
    record = build_valid_record()
    record["source_url"] = "not-a-url"

    with pytest.raises(
        ValueError,
        match="source_url",
    ):
        build_evidence_record(record)


def test_schema_rejects_invalid_date():
    record = build_valid_record()
    record["published_at"] = "01/15/2026"

    with pytest.raises(
        ValueError,
        match="published_at",
    ):
        build_evidence_record(record)


def test_schema_rejects_short_text():
    record = build_valid_record()
    record["text"] = "Too short"

    with pytest.raises(
        ValueError,
        match="text must contain",
    ):
        build_evidence_record(record)


def test_ingestion_writes_csv_and_report(
    tmp_path: Path,
):
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "evidence.csv"
    report_path = tmp_path / "report.json"

    records = [
        build_valid_record("test-002"),
        build_valid_record("test-001"),
    ]

    records[0]["topic"] = "z-topic"
    records[0]["title"] = "Second Example Evidence"
    records[0]["text"] = (
        "This is the second distinct evidence statement "
        "used to verify deterministic ingestion sorting."
    )

    records[1]["topic"] = "a-topic"
    records[1]["title"] = "First Example Evidence"
    records[1]["text"] = (
        "This is the first distinct evidence statement "
        "used to verify deterministic ingestion sorting."
    )

    write_jsonl(input_path, records)

    result = run_ingestion(
        input_path=input_path,
        output_path=output_path,
        report_path=report_path,
    )

    assert result.returncode == 0, result.stderr
    assert output_path.exists()
    assert report_path.exists()

    with output_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        output_rows = list(csv.DictReader(file))

    assert len(output_rows) == 2
    assert output_rows[0]["evidence_id"] == "test-001"
    assert output_rows[1]["evidence_id"] == "test-002"

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["statistics"]["accepted_records"] == 2
    assert (
        report["statistics"]["duplicate_ids_skipped"]
        == 0
    )


def test_ingestion_skips_duplicate_content(
    tmp_path: Path,
):
    input_path = tmp_path / "duplicates.jsonl"
    output_path = tmp_path / "evidence.csv"
    report_path = tmp_path / "report.json"

    first_record = build_valid_record("test-001")
    second_record = build_valid_record("test-002")

    write_jsonl(
        input_path,
        [
            first_record,
            second_record,
        ],
    )

    result = run_ingestion(
        input_path=input_path,
        output_path=output_path,
        report_path=report_path,
    )

    assert result.returncode == 0, result.stderr

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["statistics"]["accepted_records"] == 1
    assert (
        report["statistics"]["duplicate_content_skipped"]
        == 1
    )

    duplicate_detail = report[
        "duplicate_content_details"
    ][0]

    assert duplicate_detail["skipped_evidence_id"] == (
        "test-002"
    )
    assert duplicate_detail["original_evidence_id"] == (
        "test-001"
    )


def test_ingestion_rejects_conflicting_duplicate_id(
    tmp_path: Path,
):
    input_path = tmp_path / "conflict.jsonl"
    output_path = tmp_path / "evidence.csv"

    first_record = build_valid_record("test-001")
    second_record = build_valid_record("test-001")
    second_record["text"] = (
        "This is a different evidence statement that "
        "creates an identifier conflict."
    )

    write_jsonl(
        input_path,
        [
            first_record,
            second_record,
        ],
    )

    result = run_ingestion(
        input_path=input_path,
        output_path=output_path,
    )

    assert result.returncode == 1
    assert "Conflicting records" in result.stderr
    assert not output_path.exists()


def test_dry_run_does_not_write_csv(
    tmp_path: Path,
):
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "evidence.csv"
    report_path = tmp_path / "report.json"

    write_jsonl(
        input_path,
        [build_valid_record()],
    )

    result = run_ingestion(
        input_path=input_path,
        output_path=output_path,
        report_path=report_path,
        dry_run=True,
    )

    assert result.returncode == 0, result.stderr
    assert not output_path.exists()
    assert report_path.exists()

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["dry_run"] is True
    assert report["statistics"]["accepted_records"] == 1
