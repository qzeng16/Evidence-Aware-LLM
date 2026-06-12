from retrieve import load_retriever, retrieve_evidence


print("RUNNING QUERY-AWARE VERIFIER V2")


def contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def verify_claim(query, evidence):
    query_lower = query.lower()

    top_score = evidence[0]["score"]
    second_score = evidence[1]["score"]
    confidence_gap = top_score - second_score

    evidence_text = " ".join(
        item["text"].lower() for item in evidence
    )

    if top_score < 0.40:
        return {
            "decision": "Uncertain",
            "confidence": top_score,
            "reason": "The retrieved evidence is not sufficiently relevant to the query."
        }

    hallucination_terms = [
        "hallucinate",
        "hallucination",
        "unsupported",
        "without reliable evidence",
        "unreliable",
        "fabricate",
        "false scientific claims"
    ]

    improvement_terms = [
        "improve",
        "improves",
        "improved",
        "accelerate",
        "accelerates",
        "help",
        "helps",
        "helped",
        "enhance",
        "enhances"
    ]

    limitation_terms = [
        "fail",
        "fails",
        "limitations",
        "different patient populations",
        "biased",
        "small dataset",
        "small or biased datasets",
        "unreliable conclusions",
        "unreliable"
    ]

    oversight_terms = [
        "human oversight",
        "expert review",
        "human expert",
        "combined with human"
    ]

    # Case 1: hallucination claim
    if contains_any(query_lower, hallucination_terms):
        if contains_any(evidence_text, hallucination_terms):
            confidence = min(0.95, top_score + confidence_gap)
            return {
                "decision": "Supported",
                "confidence": confidence,
                "reason": "The retrieved evidence supports the claim that LLMs may generate unsupported or unreliable scientific statements."
            }

    # Case 2: reliability claim
    if "reliable" in query_lower or "trustworthy" in query_lower:
        if contains_any(evidence_text, limitation_terms):
            confidence = min(0.90, top_score)
            return {
                "decision": "Refuted",
                "confidence": confidence,
                "reason": "The retrieved evidence suggests reliability problems or limitations that contradict the claim."
            }

    # Case 3: improvement claim
    if contains_any(query_lower, improvement_terms):
        if contains_any(evidence_text, improvement_terms):
            confidence = min(0.90, top_score + 0.5 * confidence_gap)
            return {
                "decision": "Supported",
                "confidence": confidence,
                "reason": "The retrieved evidence contains positive support for the claimed improvement or benefit."
            }

        if contains_any(evidence_text, limitation_terms):
            confidence = min(0.80, top_score)
            return {
                "decision": "Uncertain",
                "confidence": confidence,
                "reason": "The retrieved evidence contains limitations or mixed findings, so the claim is not fully supported."
            }

    # Case 4: human oversight claim
    if contains_any(query_lower, oversight_terms):
        if contains_any(evidence_text, oversight_terms):
            confidence = min(0.90, top_score + 0.5 * confidence_gap)
            return {
                "decision": "Supported",
                "confidence": confidence,
                "reason": "The retrieved evidence supports the need for human oversight or expert review."
            }

    return {
        "decision": "Uncertain",
        "confidence": min(0.75, top_score),
        "reason": "Relevant evidence was retrieved, but the system could not confidently determine whether it supports or refutes the claim."
    }


if __name__ == "__main__":
    papers, model, paper_embeddings = load_retriever()

    query = input("Question: ")

    evidence = retrieve_evidence(
        query=query,
        papers=papers,
        model=model,
        paper_embeddings=paper_embeddings,
        top_k=3
    )

    result = verify_claim(query, evidence)

    print("\nFinal Verification Result:")
    print(f"Decision: {result['decision']}")
    print(f"Confidence: {result['confidence']:.3f}")
    print(f"Reason: {result['reason']}")

    print("\nRetrieved Evidence:\n")

    for item in evidence:
        print("=" * 50)
        print(f"Title: {item['title']}")
        print(f"Score: {item['score']:.3f}")
        print(item["text"])
        print()
