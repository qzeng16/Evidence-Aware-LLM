# Evidence-Aware LLM Claim Verification System

This project is a small evidence-aware claim verification system.

It retrieves relevant evidence for a user claim, compares the claim against the evidence, and returns one of three labels:

    Supported
    Refuted
    Uncertain

The goal is not to build a general-purpose fact-checking system.  
The goal is to demonstrate a practical AI engineering pipeline for retrieval, verification, uncertainty handling, evaluation, API serving, and testing.

---

## What This Project Demonstrates

This project includes:

    Evidence retrieval
    Embedding-based semantic search
    Lightweight reranking
    Claim-evidence verification
    Abstention / uncertainty handling
    JSON response formatting
    Logging
    Evaluation
    Error analysis
    Threshold tuning
    FastAPI service
    API smoke tests
    Pytest unit tests
    Makefile workflow

---

## Project Structure

    evidence_llm_project/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── routes.py
    │   ├── schemas.py
    │   └── services.py
    ├── data/
    │   ├── evidence.csv
    │   ├── rules.json
    │   └── claims_test.csv
    ├── logs/
    │   ├── evaluation_report.json
    │   └── evaluation_results.csv
    ├── scripts/
    │   ├── test_api.sh
    │   └── test_api.py
    ├── tests/
    │   └── test_verifier_core.py
    ├── api.py
    ├── layer0_verifier.py
    ├── layer1_evaluate.py
    ├── layer1_error_analysis.py
    ├── layer1_threshold_tuning.py
    ├── Makefile
    ├── requirements.txt
    ├── .gitignore
    └── README.md

---

## Core Pipeline

The system follows this pipeline:

    User claim
        ↓
    Claim validation
        ↓
    Evidence retrieval
        ↓
    Embedding similarity search
        ↓
    Lightweight reranking
        ↓
    Abstention check
        ↓
    Claim-evidence verification
        ↓
    JSON response
        ↓
    Logging / evaluation

---

## Retrieval Method

The project uses:

    sentence-transformers/all-MiniLM-L6-v2

Evidence retrieval combines:

    1. Embedding cosine similarity
    2. Lightweight keyword overlap reranking

The final retrieval score is computed as:

    final_score = 0.8 * embedding_score + 0.2 * keyword_score

---

## Labels

The verifier returns one of three labels:

    Supported

The retrieved evidence supports the claim.

    Refuted

The retrieved evidence contradicts the claim.

    Uncertain

The system does not have enough relevant evidence, or the claim is out of scope.

---

## Example Claims

Supported example:

    Retrieval augmented generation can improve factual reliability.

Refuted example:

    Retrieval augmented generation cannot improve factual reliability.

Uncertain example:

    Do bananas improve AI model reliability?

---

## Installation

Install dependencies:

    make install

or:

    python3 -m pip install -r requirements.txt

---

## Run the CLI Verifier

Run:

    python3 layer0_verifier.py

Then enter a claim interactively.

---

## Run Evaluation

Run:

    make evaluate

or:

    python3 layer1_evaluate.py

This evaluates the verifier on the manual test set in:

    data/claims_test.csv

Evaluation outputs are saved under:

    logs/evaluation_report.json
    logs/evaluation_results.csv

---

## Run Error Analysis

Run:

    make error-analysis

or:

    python3 layer1_error_analysis.py

This helps inspect which claims failed and why.

---

## Run Threshold Tuning

Run:

    make tune-thresholds

or:

    python3 layer1_threshold_tuning.py

This tests different abstention thresholds and reports the best setting on the current manual test set.

---

## FastAPI Service

Start the API server:

    make api

or:

    python3 -m uvicorn app.main:app --reload

The API can also be started through the compatibility entry point:

    python3 -m uvicorn api:app --reload

The recommended command is:

    python3 -m uvicorn app.main:app --reload

---

## API Endpoints

Root endpoint:

    GET /

Health check:

    GET /health

Example response:

    {
      "status": "ready"
    }

Verify claim:

    POST /verify

Example request:

    {
      "claim": "Are AI models always reliable on small biased datasets?"
    }

Example response:

    {
      "status": "success",
      "data": {
        "claim": "Are AI models always reliable on small biased datasets?",
        "prediction": {
          "label": "Refuted",
          "confidence": 0.86
        },
        "evidence": [
          {
            "title": "Small Dataset Problem",
            "score": 0.9273,
            "embedding_score": 0.9091,
            "keyword_score": 1.0
          }
        ]
      },
      "metadata": {
        "retrieval_method": "embedding_plus_lightweight_reranking",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
      }
    }

---

## Interactive API Docs

After starting the API server, open:

    http://127.0.0.1:8000/docs

This opens the FastAPI Swagger UI.

---

## API Smoke Test

Start the API server first:

    make api

Then open another terminal and run:

    make test-api

or:

    python3 scripts/test_api.py

Expected output:

    Passed: 4/4
    All API smoke tests passed.

The API smoke test checks:

    GET /health
    POST /verify with a Refuted claim
    POST /verify with an Uncertain claim
    POST /verify with a Supported claim

---

## Core Unit Tests

Run:

    make test

or:

    python3 -m pytest tests -q

The tests cover:

    Claim input validation
    Supported claim prediction
    Refuted claim prediction
    Uncertain claim prediction
    Success response structure
    Error response structure

These tests do not require starting the FastAPI server.

---

## Makefile Commands

    make install             Install dependencies
    make api                 Start FastAPI server
    make test                Run pytest core tests
    make test-api            Run API smoke tests
    make evaluate            Run evaluation
    make error-analysis      Run error analysis
    make tune-thresholds     Run threshold tuning
    make clean               Remove Python cache files
    make help                Show available commands

---

## Current Limitations

This project is a small engineering prototype.

Current limitations:

    The evidence database is small.
    The evaluation set is manually created.
    The verifier uses lightweight rule-based reasoning.
    The reported test performance is not a benchmark result.
    The system should not be treated as a general-purpose fact checker.

---

## Future Improvements

Possible next improvements:

    Add a larger evidence corpus.
    Add an LLM-based verifier or judge.
    Add source-level citations.
    Add Docker support.
    Add deployment configuration.
    Add a simple frontend.
    Add more realistic evaluation data.

---

## Positioning

This project is best understood as an AI engineering portfolio project.

It demonstrates how to build a small but structured evidence-aware verification system with retrieval, uncertainty handling, API serving, testing, and evaluation.


---

## Examples

Example API request files are stored in:

    examples/

Run the curl example while the API server is running:

    ./examples/curl_verify_example.sh

