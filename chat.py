from kurukshetra.registry.documents import DocumentRepository
from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.reranking import BGEReranker


def build_engine():
    print("Loading KURUKSHETRA Knowledge Base...\n")

    return (
        HybridRetriever(),
        BGEReranker(),
        DocumentRepository(),
    )


def confidence(score: float):
    if score >= 0.08:
        return "HIGH"
    if score >= 0.03:
        return "MEDIUM"
    return "LOW"


def main():
    retriever, reranker, docs = build_engine()

    print("=" * 60)
    print("KURUKSHETRA Hybrid RAG Chat")
    print("Type 'exit' to quit")
    print("=" * 60)

    while True:
        question = input("\nYou: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        # Hybrid Retrieval
        results = retriever.search(question, top_k=10)

        # AI Reranking
        results = reranker.rerank(question, results, top_k=3)

        if not results:
            print("\nKURUKSHETRA: No relevant knowledge found.")
            continue

        best = results[0]
        doc = docs.get(best.document_id)

        print("\nKURUKSHETRA")
        print(f"Source     : {doc[1]}")
        print(f"Document   : {best.document_id}")
        print(f"Chunk      : {best.chunk_id}")
        print(f"Confidence : {confidence(best.score)} ({best.score:.3f})")
        print("-" * 60)
        print(best.text[:1500])
        print("-" * 60)


if __name__ == "__main__":
    main()