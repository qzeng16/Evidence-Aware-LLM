#!/usr/bin/env python3
"""Render the committed performance baseline into README.md."""

import json
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

BASELINE_PATH = (
    PROJECT_ROOT
    / "performance"
    / "baselines"
    / "local_rule_only.json"
)

README_PATH = PROJECT_ROOT / "README.md"

START_MARKER = (
    "<!-- performance-baseline:start -->"
)

END_MARKER = (
    "<!-- performance-baseline:end -->"
)

ENDPOINT_ORDER = {
    "/live": 0,
    "/ready": 1,
    "/verify": 2,
}


def load_baseline() -> Dict[str, Any]:
    """Load the generated JSON baseline."""

    if not BASELINE_PATH.exists():
        raise SystemExit(
            "Performance baseline does not exist: "
            + str(BASELINE_PATH)
        )

    return json.loads(
        BASELINE_PATH.read_text(
            encoding="utf-8"
        )
    )


def ordered_scenarios(
    baseline: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return scenarios in endpoint/concurrency order."""

    scenarios = baseline.get(
        "scenarios",
        [],
    )

    if not isinstance(scenarios, list):
        raise SystemExit(
            "Baseline scenarios must be a list."
        )

    return sorted(
        scenarios,
        key=lambda scenario: (
            ENDPOINT_ORDER.get(
                scenario.get(
                    "endpoint",
                    "",
                ),
                99,
            ),
            int(
                scenario.get(
                    "concurrency",
                    0,
                )
            ),
        ),
    )


def build_section(
    baseline: Dict[str, Any],
) -> str:
    """Build the complete generated README section."""

    scenarios = ordered_scenarios(
        baseline
    )

    source = baseline["source"]
    environment = baseline["environment"]
    configuration = baseline["configuration"]

    rows = []

    for scenario in scenarios:
        results = scenario["results"]
        latency = results["latency_ms"]

        rows.append(
            "| {endpoint} | {concurrency} | "
            "{success:.1%} | {rps:.3f} | "
            "{average:.3f} | {p95:.3f} | "
            "{p99:.3f} |".format(
                endpoint=results["endpoint"],
                concurrency=scenario[
                    "concurrency"
                ],
                success=results[
                    "success_rate"
                ],
                rps=results[
                    "throughput_rps"
                ],
                average=latency["average"],
                p95=latency["p95"],
                p99=latency["p99"],
            )
        )

    verify_scenarios = [
        scenario
        for scenario in scenarios
        if scenario["endpoint"] == "/verify"
    ]

    best_verify = max(
        verify_scenarios,
        key=lambda scenario: scenario[
            "results"
        ]["throughput_rps"],
    )

    best_results = best_verify["results"]

    section_lines = [
        START_MARKER,
        "",
        "## Local API performance baseline",
        "",
        (
            "The repository includes a repeatable "
            "local Docker load test for the "
            "`rule_only` API."
        ),
        "",
        (
            "This is a development regression "
            "baseline, not a production capacity "
            "or service-level claim."
        ),
        "",
        "| Endpoint | Concurrency | Success | "
        "Throughput (req/s) | Average (ms) | "
        "P95 (ms) | P99 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        (
            "The highest measured `/verify` "
            "throughput in this run was "
            "**{rps:.3f} requests/second** at "
            "concurrency **{concurrency}**."
        ).format(
            rps=best_results[
                "throughput_rps"
            ],
            concurrency=best_verify[
                "concurrency"
            ],
        ),
        "",
        "Test configuration:",
        "",
        (
            "- Source commit: "
            "`{}`"
        ).format(
            source["git_commit"]
        ),
        (
            "- Container resources: "
            "`{} CPU / {} memory`"
        ).format(
            environment[
                "container_cpu_limit"
            ],
            environment[
                "container_memory_limit"
            ],
        ),
        (
            "- Requests per scenario: `{}`"
        ).format(
            configuration[
                "requests_per_scenario"
            ]
        ),
        (
            "- Warmup requests per scenario: `{}`"
        ).format(
            configuration[
                "warmup_requests"
            ]
        ),
        (
            "- Concurrency levels: `{}`"
        ).format(
            ", ".join(
                str(value)
                for value in configuration[
                    "concurrencies"
                ]
            )
        ),
        "",
        "Run the benchmark locally with:",
        "",
        "```bash",
        "./scripts/run_performance_baseline.sh",
        "```",
        "",
        (
            "The complete machine-readable report "
            "is stored at "
            "`performance/baselines/"
            "local_rule_only.json`."
        ),
        "",
        END_MARKER,
    ]

    return "\n".join(
        section_lines
    )


def update_readme(
    generated_section: str,
) -> None:
    """Insert or replace the generated README section."""

    readme = README_PATH.read_text(
        encoding="utf-8"
    )

    start_index = readme.find(
        START_MARKER
    )

    end_index = readme.find(
        END_MARKER
    )

    if (
        start_index == -1
        and end_index == -1
    ):
        updated = (
            readme.rstrip()
            + "\n\n"
            + generated_section
            + "\n"
        )

    elif (
        start_index != -1
        and end_index != -1
        and end_index > start_index
    ):
        end_index += len(
            END_MARKER
        )

        updated = (
            readme[:start_index]
            + generated_section
            + readme[end_index:]
        )

        if not updated.endswith("\n"):
            updated += "\n"

    else:
        raise SystemExit(
            "README performance markers "
            "are incomplete."
        )

    README_PATH.write_text(
        updated,
        encoding="utf-8",
    )


def main() -> None:
    """Render and write the baseline section."""

    baseline = load_baseline()

    if baseline.get(
        "benchmark_type"
    ) != "local_docker_rule_only_baseline":
        raise SystemExit(
            "Unexpected performance "
            "benchmark type."
        )

    update_readme(
        build_section(baseline)
    )

    print(
        "README performance baseline updated."
    )


if __name__ == "__main__":
    main()
