from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd


def load_retriever():
    papers = pd.read_csv("papers.csv")

    print("Loading model...")

    model = SentenceTransformer("all-MiniLM-L6-v2")

    paper_embeddings = model.encode(
        papers["text"].tolist()
    )

    print("Ready.\n")

    return papers, model, paper_embeddings


def retrieve_evidence(query, papers, model, paper_embeddings, top_k=3):
    query_embedding = model.encode([query])

    scores = cosine_similarity(
        query_embedding,
        paper_embeddings
    )[0]

    top_indices = scores.argsort()[-top_k:][::-1]

    results = []

    for i in top_indices:
        results.append({
            "title": papers.iloc[i]["title"],
            "text": papers.iloc[i]["text"],
            "label": papers.iloc[i]["label"],
            "score": float(scores[i])
        })

    return results


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

    print("\nMost Relevant Evidence:\n")

    
    for item in evidence:
        print("=" * 50)
        print(f"Title: {item['title']}")
        print(f"Score: {item['score']:.3f}")
        print(item["text"])
        print()