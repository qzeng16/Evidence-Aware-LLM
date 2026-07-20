#!/usr/bin/env python3
"""Run a lightweight concurrent HTTP load test."""

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from app.performance import (  # noqa: E402
    RequestSample,
    summarize_samples,
)


DEFAULT_CLAIM = (
    "Retrieval augmented generation can "
    "improve factual reliability."
)


def positive_integer(value: str) -> int:
    """Parse one positive integer."""

    parsed = int(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "Value must be greater than zero."
        )

    return parsed


def positive_float(value: str) -> float:
    """Parse one positive floating-point value."""

    parsed = float(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "Value must be greater than zero."
        )

    return parsed


def success_rate_value(value: str) -> float:
    """Parse a success-rate threshold."""

    parsed = float(value)

    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(
            "Value must be between 0 and 1."
        )

    return parsed


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Measure API throughput, success rate, "
            "and latency percentiles."
        )
    )

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL.",
    )

    parser.add_argument(
        "--endpoint",
        choices=(
            "live",
            "ready",
            "health",
            "verify",
        ),
        default="verify",
        help="Endpoint to test.",
    )

    parser.add_argument(
        "--requests",
        type=positive_integer,
        default=20,
        help="Number of measured requests.",
    )

    parser.add_argument(
        "--concurrency",
        type=positive_integer,
        default=4,
        help="Maximum concurrent requests.",
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=2,
        help=(
            "Sequential warmup requests excluded "
            "from measurements."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=30.0,
        help="Per-request timeout in seconds.",
    )

    parser.add_argument(
        "--claim",
        default=DEFAULT_CLAIM,
        help=(
            "Claim sent to POST /verify. "
            "It is not included in the report."
        ),
    )

    parser.add_argument(
        "--min-success-rate",
        type=success_rate_value,
        default=1.0,
        help=(
            "Fail when success rate is below "
            "this threshold."
        ),
    )

    parser.add_argument(
        "--output",
        help="Optional JSON report path.",
    )

    arguments = parser.parse_args()

    if arguments.warmup < 0:
        parser.error(
            "--warmup cannot be negative."
        )

    return arguments


def request_sample(
    *,
    url: str,
    endpoint: str,
    timeout_seconds: float,
    claim: str,
    request_index: int,
    request_id_prefix: str,
) -> RequestSample:
    """Execute and measure one HTTP request."""

    payload = None
    method = "GET"

    headers = {
        "Accept": "application/json",
        "X-Request-ID": "{}-{}".format(
            request_id_prefix,
            request_index,
        ),
    }

    if endpoint == "verify":
        method = "POST"

        payload = json.dumps(
            {
                "claim": claim,
            }
        ).encode("utf-8")

        headers[
            "Content-Type"
        ] = "application/json"

    request = Request(
        url,
        data=payload,
        headers=headers,
        method=method,
    )

    started_at = time.perf_counter()

    status_code: Optional[int]
    error_type: Optional[str]

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            response.read()
            status_code = response.status

        success = (
            200 <= status_code < 300
        )

        error_type = (
            None
            if success
            else "http_status"
        )

    except HTTPError as error:
        error.read()

        status_code = error.code
        success = False
        error_type = "http_error"

    except URLError:
        status_code = None
        success = False
        error_type = "url_error"

    except TimeoutError:
        status_code = None
        success = False
        error_type = "timeout"

    except OSError:
        status_code = None
        success = False
        error_type = "network_error"

    except Exception:
        status_code = None
        success = False
        error_type = "unexpected_error"

    latency_ms = (
        time.perf_counter()
        - started_at
    ) * 1000.0

    return RequestSample(
        latency_ms=latency_ms,
        status_code=status_code,
        success=success,
        error_type=error_type,
    )


def main() -> int:
    """Run warmup and measured requests."""

    arguments = parse_arguments()

    base_url = arguments.base_url.rstrip(
        "/"
    )

    endpoint_path = (
        "/" + arguments.endpoint
    )

    url = base_url + endpoint_path

    request_id_prefix = (
        "loadtest-"
        + uuid.uuid4().hex[:8]
    )

    print(
        "Warming up {} with {} request(s)...".format(
            endpoint_path,
            arguments.warmup,
        ),
        file=sys.stderr,
    )

    for index in range(
        arguments.warmup
    ):
        request_sample(
            url=url,
            endpoint=arguments.endpoint,
            timeout_seconds=arguments.timeout,
            claim=arguments.claim,
            request_index=index,
            request_id_prefix=(
                request_id_prefix
                + "-warmup"
            ),
        )

    print(
        "Sending {} measured request(s) "
        "with concurrency {}...".format(
            arguments.requests,
            arguments.concurrency,
        ),
        file=sys.stderr,
    )

    started_at = time.perf_counter()

    samples = []

    with ThreadPoolExecutor(
        max_workers=arguments.concurrency
    ) as executor:
        futures = [
            executor.submit(
                request_sample,
                url=url,
                endpoint=arguments.endpoint,
                timeout_seconds=arguments.timeout,
                claim=arguments.claim,
                request_index=index,
                request_id_prefix=(
                    request_id_prefix
                ),
            )
            for index in range(
                arguments.requests
            )
        ]

        for future in as_completed(
            futures
        ):
            samples.append(
                future.result()
            )

    elapsed_seconds = (
        time.perf_counter()
        - started_at
    )

    summary = summarize_samples(
        samples,
        elapsed_seconds=elapsed_seconds,
        endpoint=endpoint_path,
        concurrency=arguments.concurrency,
    )

    report = {
        "benchmark_type": (
            "lightweight_http_load_test"
        ),
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "base_url": base_url,
        "configuration": {
            "endpoint": endpoint_path,
            "requests": arguments.requests,
            "concurrency": (
                arguments.concurrency
            ),
            "warmup_requests": (
                arguments.warmup
            ),
            "timeout_seconds": (
                arguments.timeout
            ),
            "minimum_success_rate": (
                arguments.min_success_rate
            ),
        },
        "results": summary,
    }

    serialized_report = json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    )

    print(serialized_report)

    if arguments.output:
        output_path = Path(
            arguments.output
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            serialized_report + "\n",
            encoding="utf-8",
        )

        print(
            "Report written to {}".format(
                output_path
            ),
            file=sys.stderr,
        )

    if (
        summary["success_rate"]
        < arguments.min_success_rate
    ):
        print(
            "Success rate {:.2%} was below "
            "the required {:.2%}.".format(
                summary["success_rate"],
                arguments.min_success_rate,
            ),
            file=sys.stderr,
        )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
