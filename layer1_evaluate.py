import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from sentence_transformers import SentenceTransformer

from layer0_verifier import (
    DATA_PATH,
    RULES_PATH,
    MODEL_NAME,
    load_evidence,
    load_rules,
    get_or_build_evidence_embeddings,
    verify_claim,
)


CLAIMS_PATH = Path(__file__).parent / "data" / "claims_test.csv"

LOG_DIR = Path(__file__).parent / "logs"
EVALUATION_REPORT_PATH = LOG_DIR / "evaluation_report.json"
EVALUATION_RESULTS_PATH = LOG_DIR / "evaluation_results.csv"

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


def initialize_confusion_matrix() -> Dict[str, Dict[str, int]]:
    matrix = {}

    for actual_label in LABELS:
        matrix[actual_label] = {}

        for predicted_label in LABELS:
            matrix[actual_label][predicted_label] = 0

    return matrix


def compute_label_metrics(results: List[Dict]) -> Dict:
    metrics = {}

    for label in LABELS:
        true_positive = 0
        false_positive = 0
        false_negative = 0

        for item in results:
            expected = item["expected_label"]
            predicted = item["predicted_label"]

            if expected == label and predicted == label:
                true_positive += 1
            elif expected != label and predicted == label:
                false_positive += 1
            elif expected == label and predicted != label:
                false_negative += 1

        precision = (
            true_positive / (true_positive + false_positive)
            if (true_positive + false_positive) > 0
            else 0.0
        )

        recall = (
            true_positive / (true_positive + false_negative)
            if (true_positive + false_negative) > 0
            else 0.0
        )

        metrics[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative
        }

    return metrics


def save_evaluation_report(report: Dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)

    with open(EVALUATION_REPORT_PATH, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)


def save_evaluation_results(results: List[Dict]) -> None:
    LOG_DIR.mkdir(exist_ok=True)

    with open(EVALUATION_RESULTS_PATH, "w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "claim",
            "expected_label",
            "predicted_label",
            "correct",
            "confidence",
            "top_evidence_title",
            "top_evidence_score",
            "abstention_reason"
        ]

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for item in results:
            writer.writerow({
                "claim": item["claim"],
                "expected_label": item["expected_label"],
                "predicted_label": item["predicted_label"],
                "correct": item["correct"],
                "confidence": item["confidence"],
                "top_evidence_title": item["top_evidence_title"],
                "top_evidence_score": item["top_evidence_score"],
                "abstention_reason": item["abstention_reason"]
            })


def evaluate() -> None:
    evidence_db = load_evidence(DATA_PATH)
    verification_rules = load_rules(RULES_PATH)

    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    evidence_embeddings = get_or_build_evidence_embeddings(evidence_db, model)

    test_cases = load_test_claims(CLAIMS_PATH)

    total = len(test_cases)
    correct = 0
    results = []
    confusion_matrix = initialize_confusion_matrix()

    for case in test_cases:
        claim = case["claim"]
        expected_label = case["expected_label"]

        result = verify_claim(
            claim=claim,
            evidence_db=evidence_db,
            verification_rules=verification_rules,
            model=model,
            evidence_embeddings=evidence_embeddings
        )

        predicted_label = result["label"]
        confidence = result["confidence"]
        is_correct = predicted_label == expected_label

        if is_correct:
            correct += 1

        confusion_matrix[expected_label][predicted_label] += 1

        evidence = result.get("evidence", [])

        if evidence:
            top_evidence_title = evidence[0].get("title", "")
            top_evidence_score = evidence[0].get("score", "")
        else:
            top_evidence_title = ""
            top_evidence_score = ""

        results.append({
            "claim": claim,
            "expected_label": expected_label,
            "predicted_label": predicted_label,
            "correct": is_correct,
            "confidence": confidence,
            "top_evidence_title": top_evidence_title,
            "top_evidence_score": top_evidence_score,
            "abstention_reason": result.get("abstention_reason")
        })

    accuracy = correct / total if total > 0 else 0.0
    label_metrics = compute_label_metrics(results)

    report = {
        "timestamp": datetime.now().isoformat(),
        "model_name": MODEL_NAME,
        "total_cases": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "label_metrics": label_metrics,
        "confusion_matrix": confusion_matrix,
        "results": results
    }

    save_evaluation_report(report)
    save_evaluation_results(results)

    print("\nEvaluation Results")
    print("-" * 50)
    print(f"Total cases: {total}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.2f}")
    print("-" * 50)

    print("\nPer-label Metrics")
    print("-" * 50)

    for label, metric in label_metrics.items():
        print(f"{label}:")
        print(f"  Precision: {metric['precision']}")
        print(f"  Recall: {metric['recall']}")

    print("-" * 50)

    print("\nCase Results")
    print("-" * 50)

    for item in results:
        status = "PASS" if item["correct"] else "FAIL"

        print(f"[{status}]")
        print("Claim:", item["claim"])
        print("Expected:", item["expected_label"])
        print("Predicted:", item["predicted_label"])
        print("Confidence:", item["confidence"])
        print("Top Evidence:", item["top_evidence_title"])
        print("Top Evidence Score:", item["top_evidence_score"])

        if item["abstention_reason"]:
            print("Abstention Reason:", item["abstention_reason"])

        print("-" * 50)

    print(f"\nSaved JSON report to: {EVALUATION_REPORT_PATH}")
    print(f"Saved CSV results to: {EVALUATION_RESULTS_PATH}")


if __name__ == "__main__":
    evaluate()