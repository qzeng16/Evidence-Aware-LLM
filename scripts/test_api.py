import json
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8000"


TEST_CASES = [
    {
        "name": "Refuted claim",
        "claim": "Are AI models always reliable on small biased datasets?",
        "expected_label": "Refuted"
    },
    {
        "name": "Uncertain claim",
        "claim": "Do bananas improve AI model reliability?",
        "expected_label": "Uncertain"
    },
    {
        "name": "Supported claim",
        "claim": "Retrieval augmented generation can improve factual reliability.",
        "expected_label": "Supported"
    }
]


def get_json(path: str) -> dict:
    url = BASE_URL + path

    with urllib.request.urlopen(url) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def post_json(path: str, payload: dict) -> dict:
    url = BASE_URL + path

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def test_health() -> bool:
    print("Testing GET /health...")

    try:
        response = get_json("/health")
        status = response.get("status")

        if status == "ready":
            print("PASS: health check is ready")
            return True

        print(f"FAIL: health status is {status}")
        return False

    except Exception as error:
        print(f"FAIL: health check failed: {error}")
        return False


def test_verify_case(test_case: dict) -> bool:
    name = test_case["name"]
    claim = test_case["claim"]
    expected_label = test_case["expected_label"]

    print(f"\nTesting POST /verify: {name}")

    try:
        response = post_json("/verify", {"claim": claim})

        actual_label = (
            response
            .get("data", {})
            .get("prediction", {})
            .get("label")
        )

        print("Claim:", claim)
        print("Expected:", expected_label)
        print("Actual:", actual_label)

        if actual_label == expected_label:
            print("PASS")
            return True

        print("FAIL")
        print("Full response:")
        print(json.dumps(response, indent=2))
        return False

    except urllib.error.HTTPError as error:
        print(f"FAIL: HTTP error {error.code}")
        print(error.read().decode("utf-8"))
        return False

    except Exception as error:
        print(f"FAIL: request failed: {error}")
        return False


def main() -> None:
    print("API Smoke Test")
    print("=" * 50)

    results = []

    results.append(test_health())

    for test_case in TEST_CASES:
        results.append(test_verify_case(test_case))

    passed = sum(results)
    total = len(results)

    print("\nSummary")
    print("=" * 50)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("All API smoke tests passed.")
    else:
        print("Some API smoke tests failed.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()