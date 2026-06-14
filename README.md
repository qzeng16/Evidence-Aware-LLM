# Evidence-Aware Claim Verification System

![Python](https://img.shields.io/badge/Python-3.10-blue)
![NLP](https://img.shields.io/badge/NLP-Retrieval-green)
![AI Reliability](https://img.shields.io/badge/AI-Reliability-purple)
![Status](https://img.shields.io/badge/Status-Prototype-orange)

This project implements a lightweight **evidence-aware claim verification system** for AI reliability research. It retrieves relevant evidence using sentence-transformer embeddings and applies query-aware reasoning rules to classify claims as **Supported**, **Refuted**, or **Uncertain**.

The goal of this project is to explore how retrieval-grounded reasoning can improve the reliability and transparency of AI systems when evaluating scientific or technical claims.

---

## Motivation

Modern AI systems, especially large language models, can generate fluent and confident responses that are not always grounded in reliable evidence. This creates challenges in scientific, technical, and decision-making contexts, where unsupported claims may lead to incorrect conclusions.

This project investigates a simple and interpretable approach:

1. Retrieve relevant evidence.
2. Rank evidence using semantic similarity.
3. Verify the claim based on the retrieved evidence.
4. Return a decision with confidence and supporting evidence.

By separating retrieval from reasoning, the system makes the verification process more transparent and easier to inspect.

---

## System Pipeline

```text
Input Claim
    ↓
Evidence Database
    ↓
Sentence-Transformer Embedding
    ↓
Cosine Similarity Retrieval
    ↓
Top-K Evidence Selection
    ↓
Query-Aware Reasoning Rules
    ↓
Supported / Refuted / Uncertain + Confidence + Evidence
```

---

## Demo

![Demo](assets/demo.png)

---

## Features

- Semantic evidence retrieval using `sentence-transformers`
- Cosine similarity ranking for evidence selection
- Query-aware reasoning rules
- Three-way claim classification: `Supported`, `Refuted`, or `Uncertain`
- Confidence score for each verification result
- Interpretable retrieved evidence display
- Lightweight and modular Python implementation
- Designed as a research prototype for AI reliability and claim verification

---

## Project Structure

```text
Evidence-Aware-LLM/
├── assets/
│   └── demo.png          # Demo screenshot
├── claims.csv            # Small evaluation claim set
├── papers.csv            # Local evidence database
├── retrieve.py           # Semantic evidence retrieval module
├── reason.py             # Evidence-aware reasoning baseline
├── verifier.py           # Main claim verification pipeline
├── evaluation.py         # Evaluation script
├── requirements.txt      # Python dependencies
├── .gitignore            # Files ignored by Git
└── README.md             # Project documentation
```

---

## Methods

### 1. Evidence Retrieval

The system converts each evidence passage into an embedding using the sentence-transformer model `all-MiniLM-L6-v2`.

Given an input claim, the system computes cosine similarity between the claim embedding and each evidence embedding. The top-ranked evidence passages are then returned for verification.

This retrieval step helps the system focus on evidence that is semantically related to the claim instead of relying only on keyword matching.

### 2. Query-Aware Verification

After retrieving relevant evidence, the verifier applies query-aware reasoning rules to determine whether the evidence supports, refutes, or does not sufficiently address the claim.

The current system handles several types of claims, including:

- AI hallucination or unsupported scientific claims
- Reliability and factuality claims
- Retrieval-augmented generation claims
- Human oversight and expert review claims
- Claims involving biased or limited datasets
- Claims where available evidence is insufficient or inconclusive

### 3. Interpretable Output

For each claim, the system returns:

- A final decision: `Supported`, `Refuted`, or `Uncertain`
- A confidence score
- A short reasoning explanation
- Retrieved evidence passages used by the system

This makes the decision process easier to inspect and debug.

---

## Quick Start

Clone the repository:

```bash
git clone https://github.com/qzeng16/Evidence-Aware-LLM.git
cd Evidence-Aware-LLM
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the verifier:

```bash
python3 verifier.py
```

Then enter a claim or question when prompted.

---

## Example Outputs

### Example 1: LLM Hallucination

**Question**

```text
Do large language models hallucinate scientific claims?
```

**Output**

```text
Decision: Supported
Confidence: 0.950
Reason: The retrieved evidence supports the claim that LLMs may generate unsupported or unreliable scientific statements.
```

**Top Evidence**

```text
Large language models can generate fluent but unsupported scientific statements without reliable evidence.
```

---

### Example 2: Retrieval-Augmented Generation

**Question**

```text
Does retrieval augmented generation improve factual reliability?
```

**Output**

```text
Decision: Supported
Confidence: 0.900
Reason: The retrieved evidence contains positive support for the claimed improvement or benefit.
```

**Top Evidence**

```text
Retrieval-augmented generation improves factual reliability by grounding model outputs in external documents.
```

---

### Example 3: Reliability on Biased Datasets

**Question**

```text
Are AI models always reliable on small biased datasets?
```

**Output**

```text
Decision: Refuted
Confidence: 0.793
Reason: The retrieved evidence suggests reliability problems or limitations that contradict the claim.
```

**Top Evidence**

```text
AI models trained on small or biased datasets often produce unreliable conclusions.
```

---

## Evaluation

A small evaluation set is included in `claims.csv`. The evaluation script runs the verifier on multiple claims and compares the predicted label with the expected label.

Run:

```bash
python3 evaluation.py
```

Current evaluation result:

```text
Total: 10
Correct: 8
Accuracy: 0.80
```

This small evaluation is designed to demonstrate the verification workflow rather than serve as a large-scale benchmark.

The current errors also help reveal limitations of the prototype, such as difficulty handling abstract claims about uncertainty and cases where the retrieved evidence is relevant but not decisive.

---

## Dataset

The current version uses a small local evidence corpus stored in `papers.csv`.

The evidence database includes short passages related to:

- Large language model hallucination
- Retrieval-augmented generation
- Human oversight in AI systems
- Dataset bias and reliability
- Evidence-grounded factual reasoning
- AI system limitations and uncertainty

This dataset is designed for prototype demonstration rather than large-scale benchmark evaluation.

---

## Current Limitations

This project is a lightweight research prototype and has several limitations:

- The evidence database is small and manually constructed.
- The reasoning module is rule-based rather than a trained neural verifier.
- Retrieval quality strongly affects the final decision.
- The system may struggle with complex causal claims or claims requiring domain expertise.
- The system may be less reliable when evaluating abstract claims about uncertainty or evidence sufficiency.
- The confidence score is heuristic and should not be interpreted as a calibrated probability.
- The current version is designed for demonstration rather than production use.

These limitations are intentional for the current prototype stage and help identify directions for future improvement.

---

## Future Work

Possible extensions include:

- Expanding the evidence database with real scientific abstracts or papers
- Increasing the evaluation set size and diversity
- Adding quantitative evaluation metrics such as precision, recall, and F1 score
- Evaluating the system on public fact-checking or claim verification datasets
- Replacing rule-based reasoning with a fine-tuned neural classifier or NLI model
- Adding citation-level evidence attribution
- Improving confidence calibration
- Comparing retrieval-only, rule-based, and LLM-based verification methods
- Incorporating LLM-generated explanations grounded in retrieved evidence
- Building a simple web interface for interactive claim verification

---

## Technical Skills Demonstrated

- Python programming
- NLP pipeline construction
- Sentence embeddings
- Semantic search
- Cosine similarity ranking
- Evidence retrieval
- Claim verification
- Query-aware reasoning
- Basic evaluation workflow
- Machine learning prototyping
- AI reliability system design
- Interpretable AI workflow design

---

## Project Positioning

This project is positioned as a small research-oriented prototype in **AI reliability**, **retrieval-grounded reasoning**, and **claim verification**.

Rather than relying on generated answers alone, the system demonstrates how an AI pipeline can retrieve evidence first and then make a more transparent verification decision based on that evidence.

---

## Author

**Qihong Zeng**  
MS in Systems Engineering  
Johns Hopkins University