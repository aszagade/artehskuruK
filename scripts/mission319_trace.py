"""Mission 3.19 — Trace and benchmark the current end-to-end RAG path."""
import sys, time
sys.path.insert(0, '.')

from kurukshetra.registry.database import get_connection

conn = get_connection()

print("=== DATABASE STATE ===")
for table in ['documents', 'chunks', 'vectors', 'glossary', 'unknown_terms',
              'graph_entities', 'graph_relationships', 'graph_evidence',
              'rag_feedback', 'agent_registry']:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")
    except Exception:
        print(f"  {table}: (not found)")

print("\n=== SCHEMA: documents ===")
try:
    cols = conn.execute("PRAGMA table_info(documents)").fetchall()
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== SAMPLE DOCUMENTS (internal) ===")
try:
    rows = conn.execute(
        "SELECT document_id, title, visibility FROM documents "
        "WHERE visibility = 'internal' LIMIT 10"
    ).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1][:60]} (vis={r[2]})")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== SAMPLE CHUNKS (first 5) ===")
rows = conn.execute(
    "SELECT chunk_id, document_id, substr(text, 1, 80) FROM chunks LIMIT 5"
).fetchall()
for r in rows:
    print(f"  {r[0]} ({r[1]}): {r[2]}...")

print("\n=== GLOSSARY ENTRIES ===")
try:
    rows = conn.execute("SELECT term, definition, status FROM glossary LIMIT 10").fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1][:50] if r[1] else '(no def)'} [{r[2]}]")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== SAMPLE UNKNOWN TERMS (pending) ===")
try:
    rows = conn.execute(
        "SELECT term, occurrence_count, first_seen_doc FROM unknown_terms "
        "WHERE status = 'pending' ORDER BY occurrence_count DESC LIMIT 10"
    ).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} occurrences (doc: {r[2][:40] if r[2] else '?'})")
except Exception as e:
    print(f"  Error: {e}")

conn.close()

# ---- Test the /api/ask path ----
print("\n\n=== TEST: AnswerGenerator with BM25 ===")
from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
from kurukshetra.agent.answer_generator import AnswerGenerator

bm25 = DatabaseBM25Retriever()
gen = AnswerGenerator()

test_queries = [
    "What is the data feed configuration process?",
    "How does the installation workflow work?",
    "What are the steps for AMS Recoding?",
]

for q in test_queries:
    start = time.time()
    results = bm25.search(q, top_k=5)
    elapsed = (time.time() - start) * 1000
    
    answer = gen.generate(query=q, results=results, strategy="bm25")
    
    print(f"\nQ: {q}")
    print(f"  Retrieved: {len(results)} chunks in {elapsed:.0f}ms")
    print(f"  Answer ({answer.confidence:.2f}): {answer.answer[:150]}...")
    print(f"  Citations: {len(answer.citations)}")
    print(f"  Abstained: {answer.abstained}")
    print(f"  Evidence quality: {answer.evidence_quality}")
    if answer.conflicts:
        print(f"  Conflicts: {answer.conflicts}")

# ---- Test SANJAYA planner ----
print("\n\n=== TEST: SANJAYA Planner ===")
from kurukshetra.agent.planner import SANJAYAPlanner

planner = SANJAYAPlanner()
for q in test_queries:
    plan = planner.create_plan(q)
    print(f"\nQ: {q}")
    print(f"  Intent: {plan.intent}, Tool: {plan.tool.value}")
    print(f"  Confidence: {plan.confidence:.2f}")
    print(f"  Reason: {plan.reason}")

# ---- Test the full /api/ask path ----
print("\n\n=== TEST: Full /api/ask Path ===")
from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel

vf = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
hybrid = vf.wrap(HybridRetriever())

for q in test_queries:
    start = time.time()
    results = hybrid.search(q, top_k=5)
    elapsed = (time.time() - start) * 1000
    
    answer = gen.generate(query=q, results=results, strategy="hybrid+visibility")
    
    print(f"\nQ: {q}")
    print(f"  Retrieved: {len(results)} chunks in {elapsed:.0f}ms")
    print(f"  Answer ({answer.confidence:.2f}): {answer.answer[:200]}...")
    print(f"  Source docs: {answer.source_documents[:3]}")
    print(f"  Evidence quality: {answer.evidence_quality}")
    print(f"  Limitations: {answer.limitations}")

print("\n=== TRACE COMPLETE ===")
