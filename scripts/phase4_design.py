"""
Mission 3.14 Phase 4: Design representation D.

D: Replace "Unnamed: X" and "NaN" with empty strings, preserve everything else.
This preserves content length, chunk count, and term distribution while removing noise.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd

from kurukshetra.registry.database import get_connection
from kurukshetra.retrieval.bm25 import BM25Retriever
from kurukshetra.retrieval.models import RetrievalResult


def extract_noise_cleanup(file_path: Path) -> str:
    """Replace NaN and Unnamed: X with empty strings, preserve everything else."""
    try:
        xl = pd.ExcelFile(str(file_path), engine="openpyxl")
    except Exception:
        return ""

    parts: list[str] = []
    for sheet_name in xl.sheet_names:
        df_raw = pd.read_excel(
            str(file_path), sheet_name=sheet_name,
            engine="openpyxl", header=None,
        )
        if df_raw.empty:
            continue

        # Drop all-NaN rows
        df_clean = df_raw.dropna(how="all")
        if df_clean.empty:
            continue

        # Convert to string, replacing NaN with empty and Unnamed with empty
        text = df_clean.to_string(index=False)
        # Remove "Unnamed: N" column headers
        text = re.sub(r"Unnamed:\s*\d+", "", text)
        # Remove standalone NaN values (but not NaN inside words)
        text = re.sub(r"\bNaN\b", "", text)

        parts.append(f"--- Sheet: {sheet_name} ---")
        parts.append(text)

    return "\n".join(parts)


# Full benchmark
FULL_BENCHMARK = [
    ("Q01", "What is G3 Data Feed Configuration?", "DOC-000498"),
    ("Q02", "What is the RPM configuration process?", "DOC-000505"),
    ("Q03", "What is the Delphi Installation process?", "DOC-000497"),
    ("Q04", "How to configure Demand360 in G3 RMS?", "DOC-000499"),
    ("Q05", "How to configure STR in G3 RMS?", "DOC-000500"),
    ("Q06", "What is G3 RSS Configuration?", "DOC-000501"),
    ("Q07", "How does RMS D360 SFDC workflow work?", "DOC-000491"),
    ("Q08", "How to handle duplicate group deletion?", "DOC-000502"),
    ("Q09", "What is the Property Merge-Split workflow?", "DOC-000489"),
    ("Q10", "What is the Rate Shopping Migration workflow?", "DOC-000490"),
    ("Q11", "What is the Include/Exclude Room Types workflow?", "DOC-000492"),
    ("Q12", "What is the SSD to OCIM migration?", "DOC-000495"),
    ("Q13", "What is the AMS Recoding process?", "DOC-000493"),
    ("Q14", "What is the De-Installation NGI process?", "DOC-000494"),
    ("Q15", "What is Synthetic History to Standard Switch?", "DOC-000506"),
    ("Q16", "What is the ClientSpecific MS Recoding Process?", "DOC-000496"),
    ("Q17", "What is G3 Proactive Monitoring for Data Discrepancy?", "DOC-000487"),
    ("Q18", "What is the G3 Stats to Inventory Transition?", "DOC-000488"),
    ("Q19", "What is the Price Grid to Daily Continuous Pricing workflow?", "DOC-000504"),
    ("Q20", "What are the Pricing Issues procedures?", "DOC-000507"),
]

KEY_QUERIES = {"Q09", "Q12", "Q13", "Q17", "Q18"}


def main() -> None:
    conn = get_connection()

    # Load current chunks
    all_chunks_data = conn.execute(
        "SELECT chunk_id, document_id, text FROM chunks"
    ).fetchall()

    # Get XLSX doc IDs
    xlsx_docs = conn.execute("""
        SELECT document_id, source_path FROM documents
        WHERE source_path LIKE '%.xlsx' OR source_path LIKE '%.xls'
    """).fetchall()
    xlsx_ids = {did for did, _ in xlsx_docs}
    xlsx_sources = {did: src for did, src in xlsx_docs}

    # Build experimental chunks with D extraction
    print("Building D (noise cleanup) chunks...")
    exp_chunks: list[RetrievalResult] = []
    improved_count = 0
    for cid, did, text in all_chunks_data:
        if did in xlsx_ids:
            path = Path(xlsx_sources[did])
            if path.exists():
                try:
                    improved = extract_noise_cleanup(path)
                    if improved and len(improved) > 50:
                        for i in range(0, len(improved), 1000):
                            exp_chunks.append(RetrievalResult(
                                chunk_id=f"{cid}-D{i:06d}",
                                document_id=did,
                                score=0.0,
                                text=improved[i:i + 1000],
                                metadata={},
                            ))
                        improved_count += 1
                    else:
                        exp_chunks.append(RetrievalResult(
                            chunk_id=cid, document_id=did, score=0.0,
                            text=text, metadata={},
                        ))
                except Exception:
                    exp_chunks.append(RetrievalResult(
                        chunk_id=cid, document_id=did, score=0.0,
                        text=text, metadata={},
                    ))
            else:
                exp_chunks.append(RetrievalResult(
                    chunk_id=cid, document_id=did, score=0.0,
                    text=text, metadata={},
                ))
        else:
            exp_chunks.append(RetrievalResult(
                chunk_id=cid, document_id=did, score=0.0,
                text=text, metadata={},
            ))

    print(f"  Total chunks: {len(exp_chunks)}")
    print(f"  XLSX docs improved: {improved_count}")

    # Build BM25 index
    bm25 = BM25Retriever(exp_chunks)

    # Benchmark
    print()
    print("=" * 70)
    print("REPRESENTATION D: NOISE-ONLY CLEANUP")
    print("=" * 70)
    header = f"{'QID':5s} {'Rank':6s} {'Status':15s}"
    print(header)
    print("-" * 30)

    h3 = h5 = mrr = 0
    for qid, query, expected in FULL_BENCHMARK:
        results = bm25.search(query, top_k=5)
        docs = [r.document_id for r in results]
        rank = docs.index(expected) + 1 if expected in docs else 0

        if expected in docs[:3]:
            h3 += 1
        if expected in docs[:5]:
            h5 += 1
        if rank > 0:
            mrr += 1.0 / rank

        rank_str = f"r{rank}" if rank else "-"
        status = ""
        if qid in KEY_QUERIES:
            if rank > 0:
                status = f"rank={rank}"
            else:
                status = "MISS"
        print(f"{qid:5s} {rank_str:6s} {status:15s}")

    n = len(FULL_BENCHMARK)
    print(f"\n--- Summary ---")
    print(f"  D (noise cleanup): R@3={h3}/{n}={h3/n*100:.0f}%  R@5={h5}/{n}={h5/n*100:.0f}%  MRR={mrr/n:.3f}")

    # Compare extraction quality for key docs
    print(f"\n--- Extraction Quality ---")
    for qid, query, expected in FULL_BENCHMARK:
        if qid not in KEY_QUERIES:
            continue
        row = conn.execute(
            "SELECT source_path FROM documents WHERE document_id = ?", [expected]
        ).fetchone()
        if not row:
            continue
        path = Path(row[0])
        if not path.exists():
            continue

        # A: current
        from kurukshetra.extractors.text_extractor import TextExtractor
        a_text = TextExtractor().extract(path) or ""

        # D: noise cleanup
        d_text = extract_noise_cleanup(path)

        print(f"  {qid}: A={len(a_text)} chars  D={len(d_text)} chars  ratio={len(d_text)/max(len(a_text),1):.2f}")

    conn.close()


if __name__ == "__main__":
    main()
