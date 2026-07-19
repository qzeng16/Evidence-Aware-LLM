import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from sentence_transformers import SentenceTransformer

import layer0_verifier as verifier


CLAIMS_PATH = Path(__file__).parent / "data" / "claims_test.csv"

LOG_DIR = Path(__file__).parent / "logs"
THRESHOLD_TUNING_JSON_PATH = LOG_DIR / "threshold_tuning_report.json"
THRESHOLD_TUNING_CSV_PATH = LOG_DIR / "threshold_tuning_results.csv"

FINAL_SCORE_THRESHOLDS = [0.35, 0.40, 0.45, 0.50, 0.55]
EMBEDDING_SCORE_THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50]


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

            if claim and expected_label:
                test_cases.append({
                    "claim": claim,
                    "expected_label": expected_label
                })

    return test_cases


def evaluate_threshold_pair(
    final_score_threshold: float,
    embedding_score_threshold: float,
    test_cases: List[Dict[str, str]],
    evidence_db: List[Dict[str, str]],
    verification_rules: List[Dict],
    model: SentenceTransformer,
    evidence_embeddings
) -> Dict:
    verifier.MIN_FINAL_SCORE_FOR_VERIFICATION = final_score_threshold
    verifier.MIN_EMBEDDING_SCORE_FOR_VERIFICATION = embedding_score_threshold

    total = len(test_cases)
    correct = 0
    uncertain_count = 0
    case_results = []

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

        if predicted_label == "Uncertain":
            uncertain_count += 1

        case_results.append({
            "claim": claim,
            "expected_label": expected_label,
            "predicted_label": predicted_label,
            "correct": is_correct,
            "confidence": result["confidence"],
            "abstention_reason": result.get("abstention_reason")
        })

    accuracy = correct / total if total > 0 else 0.0
    uncertain_rate = uncertain_count / total if total > 0 else 0.0

    return {
        "final_score_threshold": final_score_threshold,
        "embedding_score_threshold": embedding_score_threshold,
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "uncertain_count": uncertain_count,
        "uncertain_rate": round(uncertain_rate, 4),
        "case_results": case_results
    }


def save_results(all_results: List[Dict], best_result: Dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "model_name": verifier.MODEL_NAME,
        "best_result": best_result,
        "all_results": all_results
    }

    with open(THRESHOLD_TUNING_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    with open(THRESHOLD_TUNING_CSV_PATH, "w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "final_score_threshold",
            "embedding_score_threshold",
            "total",
            "correct",
            "accuracy",
            "uncertain_count",
            "uncertain_rate"
        ]

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for result in all_results:
            writer.writerow({
                "final_score_threshold": result["final_score_threshold"],
                "embedding_score_threshold": result["embedding_score_threshold"],
                "total": result["total"],
                "correct": result["correct"],
                "accuracy": result["accuracy"],
                "uncertain_count": result["uncertain_count"],
                "uncertain_rate": result["uncertain_rate"]
            })


def main() -> None:
    evidence_db = verifier.load_evidence(verifier.DATA_PATH)
    verification_rules = verifier.load_rules(verifier.RULES_PATH)

    print(f"Loading embedding model: {verifier.MODEL_NAME}")
    model = SentenceTransformer(verifier.MODEL_NAME)

    evidence_embeddings = verifier.get_or_build_evidence_embeddings(evidence_db, model)
    test_cases = load_test_claims(CLAIMS_PATH)

    all_results = []

    for final_threshold in FINAL_SCORE_THRESHOLDS:
        for embedding_threshold in EMBEDDING_SCORE_THRESHOLDS:
            result = evaluate_threshold_pair(
                final_score_threshold=final_threshold,
                embedding_score_threshold=embedding_threshold,
                test_cases=test_cases,
                evidence_db=evidence_db,
                verification_rules=verification_rules,
                model=model,
                evidence_embeddings=evidence_embeddings
            )

            all_results.append(result)

    best_result = max(
        all_results,
        key=lambda item: (item["accuracy"], -item["uncertain_rate"])
    )

    save_results(all_results, best_result)

    print("\nThreshold Tuning Results")
    print("-" * 50)
    print("Best final score threshold:", best_result["final_score_threshold"])
    print("Best embedding score threshold:", best_result["embedding_score_threshold"])
    print("Best accuracy:", best_result["accuracy"])
    print("Uncertain rate:", best_result["uncertain_rate"])
    print("-" * 50)

    print(f"Saved JSON report to: {THRESHOLD_TUNING_JSON_PATH}")
    print(f"Saved CSV results to: {THRESHOLD_TUNING_CSV_PATH}")


if __name__ == "__main__":
    main()