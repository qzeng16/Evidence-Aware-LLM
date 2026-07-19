import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from sentence_transformers import SentenceTransformer

import layer0_verifier as verifier


CLAIMS_PATH = Path(__file__).parent / "data" / "claims_test.csv"

LOG_DIR = Path(__file__).parent / "logs"
ERROR_ANALYSIS_CSV_PATH = LOG_DIR / "error_analysis.csv"
ERROR_ANALYSIS_JSON_PATH = LOG_DIR / "error_analysis_report.json"

LABELS = ["Supported", "Refuted", "Uncertain"]


def load_test_claims(file_path: Path) -> List[Dict[str, str]]:
    if not file_path.exists():
        raise FileNotFoundError(f"Test claims file not found: {file_path}")

    test_cases = []

    with open(file_path, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        required_columns = {"claim", "expected_label"}
        missing_columns = required_columns - set(reader.fieldnames or [])

        if missing_columns:
            raise ValueError(f"claims_test.csv is missing columns: {missing_columns}")

        for row in reader:
            claim = row["claim"].strip()
            expected_label = row["expected_label"].strip()

            if expected_label not in LABELS:
                raise ValueError(
                    f"Invalid expected_label: {expected_label}. "
                    f"Must be one of {LABELS}."
                )

            if claim and expected_label:
                test_cases.append({
                    "claim": claim,
                    "expected_label": expected_label
                })

    if not test_cases:
        raise ValueError("No valid test cases found in claims_test.csv.")

    return test_cases


def infer_error_type(result: Dict, expected_label: str, predicted_label: str) -> str:
    if expected_label == predicted_label:
        return "correct"

    evidence = result.get("evidence", [])

    if not evidence:
        return "retrieval_failure_no_evidence"

    abstention_reason = result.get("abstention_reason")

    if predicted_label == "Uncertain" and expected_label != "Uncertain":
        if abstention_reason:
            return "over_abstention_threshold_too_strict"
        return "verification_missed_supported_or_refuted_case"

    if predicted_label != "Uncertain" and expected_label == "Uncertain":
        return "overconfident_false_positive"

    if predicted_label != expected_label:
        return "verification_logic_or_rule_error"

    return "unknown"


def analyze_errors() -> None:
    evidence_db = verifier.load_evidence(verifier.DATA_PATH)
    verification_rules = verifier.load_rules(verifier.RULES_PATH)

    print(f"Loading embedding model: {verifier.MODEL_NAME}")
    model = SentenceTransformer(verifier.MODEL_NAME)

    evidence_embeddings = verifier.get_or_build_evidence_embeddings(evidence_db, model)
    test_cases = load_test_claims(CLAIMS_PATH)

    all_results = []
    error_results = []
    error_type_counter = Counter()

    total = len(test_cases)
    correct = 0

    for case in test_cases:
        claim = case["claim"]
        expected_label = case["expected_label"]

        result = verifier.verify_claim(
            claim=claim,
            evidence_db=evidence_db,
            verification_rules=verification_rules,
            model=model,
            evidence_embeddings=evidence_embeddings
        )

        predicted_label = result["label"]
        is_correct = predicted_label == expected_label

        if is_correct:
            correct += 1

        evidence = result.get("evidence", [])

        if evidence:
            top_evidence = evidence[0]
            top_evidence_title = top_evidence.get("title", "")
            top_evidence_text = top_evidence.get("text", "")
            top_final_score = top_evidence.get("score", "")
            top_embedding_score = top_evidence.get("embedding_score", "")
            top_keyword_score = top_evidence.get("keyword_score", "")
        else:
            top_evidence_title = ""
            top_evidence_text = ""
            top_final_score = ""
            top_embedding_score = ""
            top_keyword_score = ""

        error_type = infer_error_type(result, expected_label, predicted_label)

        row = {
            "claim": claim,
            "expected_label": expected_label,
            "predicted_label": predicted_label,
            "correct": is_correct,
            "confidence": result.get("confidence"),
            "error_type": error_type,
            "top_evidence_title": top_evidence_title,
            "top_evidence_text": top_evidence_text,
            "top_final_score": top_final_score,
            "top_embedding_score": top_embedding_score,
            "top_keyword_score": top_keyword_score,
            "matched_rule": result.get("matched_rule"),
            "abstention_reason": result.get("abstention_reason")
        }

        all_results.append(row)

        if not is_correct:
            error_results.append(row)
            error_type_counter[error_type] += 1

    accuracy = correct / total if total > 0 else 0.0

    report = {
        "timestamp": datetime.now().isoformat(),
        "model_name": verifier.MODEL_NAME,
        "total_cases": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "num_errors": len(error_results),
        "error_type_counts": dict(error_type_counter),
        "errors": error_results
    }

    LOG_DIR.mkdir(exist_ok=True)

    with open(ERROR_ANALYSIS_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    with open(ERROR_ANALYSIS_CSV_PATH, "w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "claim",
            "expected_label",
            "predicted_label",
            "correct",
            "confidence",
            "error_type",
            "top_evidence_title",
            "top_evidence_text",
            "top_final_score",
            "top_embedding_score",
            "top_keyword_score",
            "matched_rule",
            "abstention_reason"
        ]

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for row in error_results:
            writer.writerow(row)

    print("\nError Analysis Results")
    print("-" * 50)
    print(f"Total cases: {total}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.2f}")
    print(f"Errors: {len(error_results)}")
    print("-" * 50)

    print("\nError Type Counts")
    print("-" * 50)

    if error_type_counter:
        for error_type, count in error_type_counter.items():
            print(f"{error_type}: {count}")
    else:
        print("No errors found.")

    print("-" * 50)

    print("\nFailed Cases")
    print("-" * 50)

    for item in error_results:
        print("Claim:", item["claim"])
        print("Expected:", item["expected_label"])
        print("Predicted:", item["predicted_label"])
        print("Error Type:", item["error_type"])
        print("Top Evidence:", item["top_evidence_title"])
        print("Top Final Score:", item["top_final_score"])
        print("Matched Rule:", item["matched_rule"])
        print("Abstention Reason:", item["abstention_reason"])
        print("-" * 50)

    print(f"\nSaved error analysis CSV to: {ERROR_ANALYSIS_CSV_PATH}")
    print(f"Saved error analysis JSON to: {ERROR_ANALYSIS_JSON_PATH}")


if __name__ == "__main__":
    analyze_errors()