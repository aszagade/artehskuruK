"""
Graph Population Bridge
=======================

Connects the existing RAG document registry to the Knowledge Graph.

For every registered document:
  1. Read chunks and concatenate text
  2. Classify team via OrgMap (in-memory)
  3. Ingest into graph (extract + persist)
  4. Link chunks as CONTAINS relationships

Idempotent: safe to re-run. Existing entities are upserted.

Usage:
    python -m kurukshetra.pipeline.graph_indexer
    python -m kurukshetra.pipeline.graph_indexer --limit 10
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kurukshetra.agent.org_map import OrgMap
from kurukshetra.graph.registry import GraphRegistry


class GraphIndexer:
    """Bridges the RAG document registry to the Knowledge Graph."""

    def __init__(self, db_path: str = "kurukshetra_registry.duckdb") -> None:
        self.registry = GraphRegistry(db_path=db_path)
        self.org_map = OrgMap()

    def index_all(self, limit: Optional[int] = None) -> dict:
        """Index all registered documents. Returns stats dict."""
        stats = {
            "documents_processed": 0,
            "entities_created": 0,
            "relationships_created": 0,
            "chunks_linked": 0,
            "duplicates_skipped": 0,
        }
        start = time.time()
        conn = self.registry.repository.get_connection()

        rows = conn.execute(
            "SELECT document_id, title FROM documents ORDER BY document_id"
        ).fetchall()
        if limit:
            rows = rows[:limit]
        total = len(rows)

        # Preload all chunks (single query)
        all_chunks = conn.execute(
            "SELECT document_id, chunk_id, text FROM chunks "
            "ORDER BY document_id, chunk_index"
        ).fetchall()
        chunks_by_doc: dict[str, list[tuple[str, str]]] = {}
        for doc_id, chunk_id, text in all_chunks:
            chunks_by_doc.setdefault(doc_id, []).append((chunk_id, text))

        for i, (doc_id, title) in enumerate(rows):
            chunks = chunks_by_doc.get(doc_id, [])
            if not chunks:
                stats["documents_processed"] += 1
                continue

            full_text = "\n\n".join(t for _, t in chunks)
            chunk_ids = [c for c, _ in chunks]
            if not full_text.strip():
                stats["documents_processed"] += 1
                continue

            # Classify team (in-memory)
            team_id = None
            matches = self.org_map.classify_document(full_text, title or "")
            if matches and matches[0]["confidence"] > 0.05:
                team_id = matches[0]["team_id"]

            # Ingest into graph
            extraction = self.registry.ingest_document(
                text=full_text,
                document_id=doc_id,
                document_title=title or "",
                team_id=team_id,
            )
            stats["entities_created"] += len(extraction.entities)
            stats["relationships_created"] += len(extraction.relationships)

            # Link chunks
            doc_entity_id = f"DOC-{doc_id}"
            for chunk_id in chunk_ids:
                cid = f"CHUNK-{chunk_id}"
                conn.execute(
                    "INSERT INTO graph_entities "
                    "(id,name,entity_type,description,metadata,owner,visibility) "
                    "VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET description=excluded.description",
                    [cid, f"Chunk {chunk_id}", "knowledge_article",
                     f"Chunk of {doc_id}", "{}", None, "internal"],
                )
                conn.execute(
                    "INSERT INTO graph_relationships "
                    "(source_id,target_id,relation_type,description,confidence,metadata) "
                    "VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(source_id,target_id,relation_type) "
                    "DO UPDATE SET confidence=GREATEST(excluded.confidence,graph_relationships.confidence)",
                    [doc_entity_id, cid, "contains",
                     f"Document contains {chunk_id}", 1.0, "{}"],
                )
                conn.execute(
                    "INSERT INTO graph_evidence "
                    "(evidence_id,entity_id,source_document,source_chunk,source_text,"
                    "confidence,human_confirmed,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,FALSE,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) "
                    "ON CONFLICT(evidence_id) DO UPDATE SET updated_at=excluded.updated_at",
                    [f"EVD-{cid}", cid, doc_id, chunk_id, f"Chunk from {doc_id}", 1.0],
                )

            stats["chunks_linked"] += len(chunk_ids)
            stats["documents_processed"] += 1

            if (i + 1) % 25 == 0 or (i + 1) == total:
                elapsed = time.time() - start
                pct = (i + 1) / total * 100
                print(
                    f"  [{i+1}/{total}] {pct:.1f}%\n"
                    f"  Entities: {stats['entities_created']}\n"
                    f"  Relationships: {stats['relationships_created']}\n"
                    f"  Elapsed: {elapsed:.0f}s"
                )

        stats["elapsed_seconds"] = round(time.time() - start, 1)
        return stats

    def close(self) -> None:
        self.registry.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="KURUKSHETRA Graph Population Bridge")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to index")
    parser.add_argument("--db", default="kurukshetra_registry.duckdb", help="DuckDB path")
    args = parser.parse_args()

    print("KURUKSHETRA Graph Population Bridge\n")

    indexer = GraphIndexer(db_path=args.db)
    stats = indexer.index_all(limit=args.limit)
    indexer.close()

    print(f"\n{'=' * 50}")
    print(f"Documents Indexed:  {stats['documents_processed']}")
    print(f"Chunks Processed:   {stats['chunks_linked']}")
    print(f"Entities:           {stats['entities_created']}")
    print(f"Relationships:      {stats['relationships_created']}")
    print(f"Duplicates Skipped: {stats['duplicates_skipped']}")
    print(f"Elapsed:            {stats['elapsed_seconds']}s")
    print("=" * 50)


if __name__ == "__main__":
    main()
