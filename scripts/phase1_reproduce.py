"""
Mission 3.14 Phase 1: Reproduce baseline.
Establishes clean measurements for the 5 key queries.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from kurukshetra.registry.database import get_connection
from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
from kurukshetra.retrieval.hybrid import HybridRetriever

KEY_QUERIES = [
    ("Q09", "What is the Property Merge-Split workflow?", "DOC-000489"),
    ("Q12", "What is the SSD to OCIM migration?", "DOC-000495"),
    ("Q13", "What is the AMS Recoding process?", "DOC-000493"),
    ("Q17", "What is G3 Proactive Monitoring for Data Discrepancy?", "DOC-000487"),
    ("Q18", "What is the G3 Stats to Inventory Transition?", "DOC-000488"),
]


def main() -> None:
    conn = get_connection()
    bm25 = DatabaseBM25Retriever()
    hybrid = HybridRetriever()

    print("=" * 70)
    print("PHASE 1: REPRODUCE BASELINE")
    print("=" * 70)

    for qid, query, expected in KEY_QUERIES:
        print(f"\n{'=' * 60}")
        print(f"  {qid}: {query}")
        print(f"  Expected: {expected}")
        print(f"{'=' * 60}")

        # Document metadata
        row = conn.execute("""
            SELECT title, source_path, sha256, team_owner, visibility
            FROM documents WHERE document_id = ?
        """, [expected]).fetchone()
        if row:
            print(f"  Title: {row[0]}")
            print(f"  Source: {row[1]}")
            print(f"  SHA256: {str(row[2])[:16] if row[2] else 'NONE'}...")
            print(f"  Team: {row[3]}")
            print(f"  Visibility: {row[4]}")

        # Chunks
        chunks = conn.execute("""
            SELECT chunk_id, length(text) FROM chunks
            WHERE document_id = ? ORDER BY chunk_id
        """, [expected]).fetchall()
        print(f"  Chunks: {len(chunks)}")
        total_chars = sum(c[1] for c in chunks)
        print(f"  Total chars: {total_chars}")
        for cid, clen in chunks:
            print(f"    {cid}: {clen} chars")

        # Term frequencies in chunks
        all_text = " ".join(
            t[0] for t in conn.execute(
                "SELECT text FROM chunks WHERE document_id = ?", [expected]
            ).fetchall()
        )
        terms = ["merge", "split", "property", "workflow", "ssd", "ocim",
                 "migration", "ams", "recoding", "proactive", "monitoring",
                 "data discrepancy", "stats", "inventory", "transition",
                 "unnamed", "nan"]
        print(f"  Term frequencies:")
        for term in terms:
            count = all_text.lower().count(term.lower())
            if count > 0:
                print(f"    '{term}': {count}")

        # BM25 results
        bm25_results = bm25.search(query, top_k=10)
        bm25_docs = [r.document_id for r in bm25_results]
        bm25_rank = bm25_docs.index(expected) + 1 if expected in bm25_docs else 0
        print(f"  BM25 rank: {bm25_rank or 'NOT FOUND'}")
        if bm25_rank:
            bm25_score = bm25_results[bm25_rank - 1].score
            print(f"  BM25 score: {bm25_score:.3f}")

        # Hybrid results
        hybrid_results = hybrid.search(query, top_k=10)
        hybrid_docs = [r.document_id for r in hybrid_results]
        hybrid_rank = hybrid_docs.index(expected) + 1 if expected in hybrid_docs else 0
        print(f"  Hybrid rank: {hybrid_rank or 'NOT FOUND'}")
        if hybrid_rank:
            hybrid_score = hybrid_results[hybrid_rank - 1].score
            print(f"  Hybrid score: {hybrid_score:.4f}")

        # Top-3 competitors
        print(f"  BM25 top-3:")
        for i, r in enumerate(bm25_results[:3]):
            marker = " <--" if r.document_id == expected else ""
            print(f"    r{i+1}: {r.document_id} score={r.score:.3f}{marker}")

    conn.close()


if __name__ == "__main__":
    main()
