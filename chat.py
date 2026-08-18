from pathlib import Path

from kurukshetra.pipeline.bulk_ingest import BulkIngestionPipeline
from kurukshetra.pipeline.indexer import KnowledgeIndexer


KNOWLEDGE_FOLDER = Path("General_Documents")


def build_engine():
    print("Loading knowledge...")

    bulk = BulkIngestionPipeline()
    docs = bulk.ingest_folder(KNOWLEDGE_FOLDER)

    indexer = KnowledgeIndexer()

    for doc in docs:
        indexer.add(doc["chunks"])

    print(f"Loaded {len(docs)} documents.\n")

    return indexer.build()


def main():
    retriever = build_engine()

    print("=" * 60)
    print("KURUKSHETRA Knowledge Chat")
    print("Type 'exit' to quit")
    print("=" * 60)

    while True:
        question = input("\nYou: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        results = retriever.search(question)

        if not results:
            print("\nKURUKSHETRA: No relevant knowledge found.")
            continue

        best = results[0]

        print("\nKURUKSHETRA")
        print(f"Document : {best.document_id}")
        print(f"Score    : {best.score:.2f}")
        print("-" * 60)
        print(best.text[:1500])
        print("-" * 60)


if __name__ == "__main__":
    main()