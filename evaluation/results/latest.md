# Verifier Evaluation Report

- Benchmark: `evaluation/benchmark.jsonl`
- Generated at: `2026-07-20T04:34:14.399867+00:00`
- Configured LLM model: `gpt-5-mini`

## Summary

| Mode | Accuracy | Coverage | Abstention | Avg latency | P95 latency | LLM calls | Tokens | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rule_only | 55.6% | 22.2% | 77.8% | 208.9 ms | 731.3 ms | 0 | 0 | 0 |
| llm_only | 66.7% | 55.6% | 44.4% | 3681.0 ms | 5016.5 ms | 9 | 8351 | 0 |
| hybrid | 77.8% | 66.7% | 33.3% | 3457.5 ms | 6509.2 ms | 7 | 6572 | 0 |

## Results: `rule_only`

| ID | Expected | Predicted | Correct | Confidence | Latency | LLM calls |
|---|---|---|---:|---:|---:|---:|
| eval-001 | Supported | Supported | Yes | 0.86 | 731.3 ms | 0 |
| eval-002 | Supported | Uncertain | No | 0.50 | 335.3 ms | 0 |
| eval-003 | Supported | Uncertain | No | 0.50 | 68.1 ms | 0 |
| eval-004 | Refuted | Uncertain | No | 0.35 | 255.2 ms | 0 |
| eval-005 | Refuted | Refuted | Yes | 0.86 | 72.6 ms | 0 |
| eval-006 | Refuted | Uncertain | No | 0.35 | 196.2 ms | 0 |
| eval-007 | Uncertain | Uncertain | Yes | 0.35 | 37.3 ms | 0 |
| eval-008 | Uncertain | Uncertain | Yes | 0.50 | 31.3 ms | 0 |
| eval-009 | Uncertain | Uncertain | Yes | 0.35 | 152.7 ms | 0 |

## Results: `llm_only`

| ID | Expected | Predicted | Correct | Confidence | Latency | LLM calls |
|---|---|---|---:|---:|---:|---:|
| eval-001 | Supported | Supported | Yes | 0.86 | 4097.2 ms | 1 |
| eval-002 | Supported | Supported | Yes | 0.88 | 3575.5 ms | 1 |
| eval-003 | Supported | Supported | Yes | 0.86 | 2621.5 ms | 1 |
| eval-004 | Refuted | Uncertain | No | 0.78 | 5016.5 ms | 1 |
| eval-005 | Refuted | Refuted | Yes | 0.91 | 2868.2 ms | 1 |
| eval-006 | Refuted | Uncertain | No | 0.72 | 3405.7 ms | 1 |
| eval-007 | Uncertain | Uncertain | Yes | 0.67 | 3521.7 ms | 1 |
| eval-008 | Uncertain | Uncertain | Yes | 0.78 | 4440.2 ms | 1 |
| eval-009 | Uncertain | Refuted | No | 0.78 | 3581.9 ms | 1 |

## Results: `hybrid`

| ID | Expected | Predicted | Correct | Confidence | Latency | LLM calls |
|---|---|---|---:|---:|---:|---:|
| eval-001 | Supported | Supported | Yes | 0.86 | 35.8 ms | 0 |
| eval-002 | Supported | Supported | Yes | 0.77 | 6509.2 ms | 1 |
| eval-003 | Supported | Supported | Yes | 0.74 | 3354.5 ms | 1 |
| eval-004 | Refuted | Refuted | Yes | 0.74 | 5463.0 ms | 1 |
| eval-005 | Refuted | Refuted | Yes | 0.86 | 42.3 ms | 0 |
| eval-006 | Refuted | Uncertain | No | 0.81 | 3041.4 ms | 1 |
| eval-007 | Uncertain | Uncertain | Yes | 0.84 | 5040.8 ms | 1 |
| eval-008 | Uncertain | Uncertain | Yes | 0.50 | 3741.9 ms | 1 |
| eval-009 | Uncertain | Refuted | No | 0.68 | 3888.9 ms | 1 |

## Interpretation

This is a small, manually curated regression benchmark for comparing the three project modes. It is not evidence of general-purpose fact-checking accuracy.
