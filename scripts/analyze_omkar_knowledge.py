"""
Mission 3.7 — Phase 4-8: Knowledge Quality Analysis

Inspect what the system discovered from the 23 ingested documents.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kurukshetra.registry import get_connection


def main():
    conn = get_connection()

    # ========================================================
    # PHASE 4: Knowledge Quality
    # ========================================================
    print(f"\n{'='*60}")
    print(f"PHASE 4 — KNOWLEDGE QUALITY ANALYSIS")
    print(f"{'='*60}")

    # New documents (Omkar corpus)
    docs = conn.execute("""
        SELECT document_id, title, team_owner, sha256, source_path
        FROM documents
        WHERE source_path LIKE '%Omkar%Process Documents%'
        ORDER BY title
    """).fetchall()

    print(f"\n  Documents ingested: {len(docs)}")
    print(f"\n  {'Title':<55} {'Team':<8} {'DocID':<12}")
    print(f"  {'-'*75}")
    for doc_id, title, team, sha, src in docs:
        t = title[:52] if title else "?"
        print(f"  {t:<55} {(team or '?'):<8} {doc_id:<12}")

    # New entities
    new_entities = conn.execute("""
        SELECT e.id, e.name, e.entity_type, e.description, e.owner
        FROM graph_entities e
        WHERE e.id LIKE 'ENT-%'
        ORDER BY e.entity_type, e.name
        LIMIT 50
    """).fetchall()

    print(f"\n  New graph entities (sample):")
    print(f"  {'Name':<30} {'Type':<20} {'Owner':<15}")
    print(f"  {'-'*65}")
    for eid, name, etype, desc, owner in new_entities[:30]:
        print(f"  {(name or '?')[:28]:<30} {(etype or '?'):<20} {(owner or '?'):<15}")

    # Entity type distribution
    entity_types = conn.execute("""
        SELECT entity_type, COUNT(*)
        FROM graph_entities
        GROUP BY entity_type
        ORDER BY COUNT(*) DESC
    """).fetchall()

    print(f"\n  Entity type distribution:")
    for etype, count in entity_types:
        print(f"    {etype:<25} {count:>6,}")

    # Relationship types
    rel_types = conn.execute("""
        SELECT relation_type, COUNT(*)
        FROM graph_relationships
        GROUP BY relation_type
        ORDER BY COUNT(*) DESC
        LIMIT 15
    """).fetchall()

    print(f"\n  Relationship type distribution:")
    for rtype, count in rel_types:
        print(f"    {rtype:<30} {count:>6,}")

    # ========================================================
    # PHASE 5: Retrieval Tests
    # ========================================================
    print(f"\n{'='*60}")
    print(f"PHASE 5 — RETRIEVAL TESTS")
    print(f"{'='*60}")

    from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever

    bm25 = DatabaseBM25Retriever()

    test_queries = [
        "What is G3 Data Feed Configuration?",
        "How does the SFDC workflow work?",
        "What is the RMS D360 configuration?",
        "What is RPM Reputation Pricing Model?",
        "What is Delphi Installation?",
        "How to handle duplicate group deletion?",
        "What is the Price Grid workflow?",
        "What is Synthetic History to Standard Switch?",
        "What is G3 RSS Configuration?",
        "What are the KB Group Pricing Evaluation steps?",
    ]

    print(f"\n  Running {len(test_queries)} BM25 queries...\n")

    for q in test_queries:
        results = bm25.search(q, top_k=3)
        print(f"  Q: {q}")
        if results:
            for i, r in enumerate(results[:2], 1):
                text_preview = r.text[:100].replace("\n", " ") if hasattr(r, 'text') else str(r)[:100]
                score = getattr(r, 'score', '?')
                print(f"    [{i}] (score={score:.3f}) {text_preview}...")
        else:
            print(f"    [no results]")
        print()

    # ========================================================
    # PHASE 6: Graph Validation
    # ========================================================
    print(f"\n{'='*60}")
    print(f"PHASE 6 — KNOWLEDGE GRAPH VALIDATION")
    print(f"{'='*60}")

    # Sample relationships with evidence
    sample_rels = conn.execute("""
        SELECT r.source_id, r.target_id, r.relation_type, r.confidence,
               e.source_document, e.source_text
        FROM graph_relationships r
        LEFT JOIN graph_evidence e ON r.source_id = e.entity_id
        WHERE r.confidence > 0.5
        ORDER BY r.confidence DESC
        LIMIT 10
    """).fetchall()

    print(f"\n  Sample high-confidence relationships:")
    for src, tgt, rtype, conf, sdoc, stxt in sample_rels:
        stxt_short = (stxt[:60] + "...") if stxt and len(stxt) > 60 else (stxt or "")
        print(f"    {src[:20]:<20} --[{rtype}]--> {tgt[:20]:<20} (conf={conf:.2f})")
        if stxt_short:
            print(f"      evidence: {stxt_short}")

    # Check for the new entities from this corpus specifically
    new_evidence = conn.execute("""
        SELECT e.source_document, e.source_text, e.confidence
        FROM graph_evidence e
        WHERE e.source_document IN (
            SELECT document_id FROM documents
            WHERE source_path LIKE '%Omkar%Process Documents%'
        )
        ORDER BY e.confidence DESC
        LIMIT 15
    """).fetchall()

    print(f"\n  Evidence from Omkar corpus (sample):")
    for sdoc, stxt, conf in new_evidence:
        stxt_short = (stxt[:80] + "...") if stxt and len(stxt) > 80 else (stxt or "")
        print(f"    doc={sdoc} conf={conf:.2f}")
        if stxt_short:
            print(f"      {stxt_short}")

    # ========================================================
    # PHASE 7: SEAL Unknown Terms
    # ========================================================
    print(f"\n{'='*60}")
    print(f"PHASE 7 — SEAL UNKNOWN TERMS")
    print(f"{'='*60}")

    unknowns = conn.execute("""
        SELECT term, status, document_id, source_text
        FROM unknown_terms
        ORDER BY term
        LIMIT 50
    """).fetchall()

    print(f"\n  Unknown terms (sample of 50 from {len(unknowns)}+):")
    for term, status, doc_id, src in unknowns:
        src_short = (src[:50] + "...") if src and len(src) > 50 else (src or "")
        print(f"    [{status}] {term:<30} {src_short}")

    # Group unknowns by likely category
    all_unknowns = conn.execute("""
        SELECT term FROM unknown_terms
    """).fetchall()
    terms = [t[0] for t in all_unknowns]

    print(f"\n  Total unknown terms: {len(terms)}")

    # Simple heuristic categorization
    import re
    systems = [t for t in terms if re.search(r"(G3|RMS|SFDC|NGI|D360|CRM|SFTP|EDF|STR|PMS|BMR|RDC|DV|AMS|OCIM|RPM|RSS|OPERA|DATADOG)", t.upper())]
    acronyms = [t for t in terms if re.match(r"^[A-Z]{2,5}$", t)]
    people = [t for t in terms if re.search(r"^(Mr|Ms|Mrs|Dr)\s|(?<!\w)[A-Z][a-z]+(?<!\w)\s(?<!\w)[A-Z][a-z]+", t)]
    ids = [t for t in terms if re.search(r"\d{5,}", t)]

    print(f"\n  Likely systems: {len(systems)} — {systems[:10]}")
    print(f"  Likely acronyms: {len(acronyms)} — {acronyms[:10]}")
    print(f"  Likely identifiers: {len(ids)} — {ids[:5]}")

    # ========================================================
    # PHASE 8: SANJAYA Verification
    # ========================================================
    print(f"\n{'='*60}")
    print(f"PHASE 8 — SANJAYA VERIFICATION")
    print(f"{'='*60}")

    from kurukshetra.agent.planner import SANJAYAPlanner
    from kurukshetra.executors.knowledge import KnowledgeExecutor

    planner = SANJAYAPlanner()
    executor = KnowledgeExecutor()

    sanjaya_queries = [
        "What is G3 Data Feed Configuration?",
        "How does the SFDC workflow work for RMS D360?",
        "What is the RPM configuration process?",
        "What systems are involved in the ICS installation process?",
        "What is the Delphi Installation?",
    ]

    for q in sanjaya_queries:
        print(f"\n  Q: {q}")
        try:
            plan = planner.classify(q)
            print(f"    Intent: {plan.intent} (confidence={plan.confidence:.2f})")
            if hasattr(plan, 'team') and plan.team:
                print(f"    Team: {plan.team}")

            answer = executor.execute(plan)
            if answer:
                text = answer.get("answer", str(answer))[:200]
                print(f"    A: {text}")
                source = answer.get("source", answer.get("sources", "unknown"))
                print(f"    Source: {source}")
            else:
                print(f"    A: [no answer returned]")
        except Exception as e:
            print(f"    Error: {e}")

    conn.close()
    print(f"\n{'='*60}")
    print(f"ANALYSIS COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
