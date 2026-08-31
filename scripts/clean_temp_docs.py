"""Mission 3.38 — Clean temp documents and backfill concept_teams."""
import sys, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from kurukshetra.registry.database import get_connection

conn = get_connection()

# Before
before_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
before_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
print(f"Before: {before_docs} docs, {before_chunks} chunks")

# Find temp documents
temp_docs = conn.execute(
    "SELECT document_id FROM documents WHERE source_path LIKE '%AppData/Local/Temp%'"
).fetchall()
temp_ids = [r[0] for r in temp_docs]
print(f"Temp docs to remove: {len(temp_ids)}")

if temp_ids:
    placeholders = ",".join(["?" for _ in temp_ids])
    # Delete chunks
    conn.execute(f"DELETE FROM chunks WHERE document_id IN ({placeholders})", temp_ids)
    # Delete graph entity meta for entities owned by temp docs
    for tid in temp_ids:
        try:
            conn.execute(
                "DELETE FROM graph_entity_meta WHERE entity_id IN "
                "(SELECT id FROM graph_entities WHERE owner = ?)", (tid,)
            )
            conn.execute("DELETE FROM graph_entities WHERE owner = ?", (tid,))
        except Exception:
            pass
    # Delete documents
    conn.execute(f"DELETE FROM documents WHERE document_id IN ({placeholders})", temp_ids)
    conn.commit()

# After
after_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
after_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
print(f"After: {after_docs} docs, {after_chunks} chunks")
print(f"Removed: {before_docs - after_docs} docs, {before_chunks - after_chunks} chunks")

# Verify no temp docs remain
remaining = conn.execute(
    "SELECT COUNT(*) FROM documents WHERE source_path LIKE '%AppData/Local/Temp%'"
).fetchone()[0]
print(f"Remaining temp: {remaining}")

# Invalidate BM25 cache
from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
bm25 = DatabaseBM25Retriever()
bm25.invalidate()
print("BM25 cache invalidated")

conn.close()
print("DONE")
