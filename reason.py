from retrieve import load_retriever, retrieve_evidence


def judge_from_evidence(evidence):
    top_score = evidence[0]["score"]
    second_score = evidence[1]["score"]

    if top_score >= 0.65:
        judgment = "Likely answerable with strong evidence"
    elif top_score >= 0.45:
        judgment = "Partially supported by retrieved evidence"
    else:
        judgment = "Insufficient evidence"

    confidence_gap = top_score - second_score

    return judgment, confidence_gap


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

    judgment, confidence_gap = judge_from_evidence(evidence)

    print("\nEvidence-Aware Judgment:")
    print(judgment)
    print(f"Confidence Gap: {confidence_gap:.3f}")

    print("\nRetrieved Evidence:\n")

    for item in evidence:
        print("=" * 50)
        print(f"Title: {item['title']}")
        print(f"Score: {item['score']:.3f}")
        print(item["text"])
        print()