import csv
import re
import subprocess
import sys


CLAIMS_FILE = "claims.csv"


def run_verifier(claim):
    """
    Runs verifier.py as a subprocess and extracts the predicted decision.
    This version works even if verifier.py does not expose an importable function.
    """
    try:
        result = subprocess.run(
            [sys.executable, "verifier.py"],
            input=claim + "\n",
            capture_output=True,
            text=True,
            timeout=90
        )

        output = result.stdout + result.stderr

        match = re.search(r"Decision:\s*(Supported|Refuted|Uncertain)", output)

        if match:
            return match.group(1), output

        return "ParseError", output

    except subprocess.TimeoutExpired:
        return "Timeout", ""


def main():
    total = 0
    correct = 0
    results = []

    with open(CLAIMS_FILE, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            claim = row["claim"]
            expected = row["expected_label"]

            predicted, output = run_verifier(claim)

            total += 1
            if predicted == expected:
                correct += 1

            results.append({
                "claim": claim,
                "expected": expected,
                "predicted": predicted
            })

    print("\nEvaluation Results")
    print("=" * 50)

    for item in results:
        status = "✓" if item["expected"] == item["predicted"] else "✗"
        print(f"{status} Claim: {item['claim']}")
        print(f"  Expected:  {item['expected']}")
        print(f"  Predicted: {item['predicted']}")
        print()

    accuracy = correct / total if total > 0 else 0

    print("=" * 50)
    print(f"Total: {total}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.2f}")


if __name__ == "__main__":
    main()