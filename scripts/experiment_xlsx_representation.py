"""
Offline Experiment: XLSX Representation
========================================

Compares current vs improved XLSX extraction for the 5 failing queries.

DOES NOT modify production code.
DOES NOT modify DuckDB.
DOES NOT modify the benchmark.
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd

from kurukshetra.registry.database import get_connection
from kurukshetra.retrieval.hybrid import HybridRetriever
from kurukshetra.retrieval.models import RetrievalResult


# ---------------------------------------------------------------------------
# Improved XLSX extraction
# ---------------------------------------------------------------------------

def improved_extract_xlsx(file_path: Path) -> str:
    """Improved extraction that handles SFDC workflow label-value layouts.

    Key differences from current extractor:
    1. Reads with header=None to see raw structure
    2. Detects if Row 0 is empty (label-value layout)
    3. Finds the actual header row (contains 'Task Subject', 'Trigger', etc.)
    4. Uses detected headers instead of 'Unnamed: X'
    5. Skips NaN-only rows
    6. Prepends sheet name and document title context
    """
    try:
        xl = pd.ExcelFile(str(file_path), engine="openpyxl")
    except Exception:
        return ""

    parts: list[str] = []

    for sheet_name in xl.sheet_names:
        df_raw = pd.read_excel(
            str(file_path), sheet_name=sheet_name,
            engine="openpyxl", header=None
        )

        if df_raw.empty:
            continue

        # Find the header row: look for rows containing known workflow terms
        header_keywords = {
            "task subject", "trigger", "due date", "assigned to",
            "task comments", "case opens", "changes", "any other comments",
            "workflow", "description", "requested by",
        }
        header_row_idx = None
        for i in range(min(10, len(df_raw))):
            row_text = " ".join(
                str(v).lower() for v in df_raw.iloc[i].values if pd.notna(v)
            )
            if any(kw in row_text for kw in header_keywords):
                header_row_idx = i
                break

        if header_row_idx is not None:
            # Use detected row as headers
            headers = [
                str(v).strip() if pd.notna(v) else f"col_{j}"
                for j, v in enumerate(df_raw.iloc[header_row_idx].values)
            ]
            # Drop the header row and any empty rows before it
            data_df = df_raw.iloc[header_row_idx + 1:].copy()
            data_df.columns = headers

            # Drop columns that are all NaN or named 'col_N'
            keep_cols = [c for c in data_df.columns if not c.startswith("col_")]
            if not keep_cols:
                keep_cols = list(data_df.columns)
            data_df = data_df[keep_cols]

            # Drop rows that are mostly NaN
            data_df = data_df.dropna(how="all")
            # Also drop rows where all non-NaN values are in just one column
            # (these are often label-only rows with no value)

            parts.append(f"--- Sheet: {sheet_name} ---")
            parts.append(data_df.to_string(index=False))
        else:
            # Fallback: no header row found, use raw extraction but skip empty rows
            parts.append(f"--- Sheet: {sheet_name} ---")
            # Drop all-NaN rows
            df_clean = df_raw.dropna(how="all")
            if not df_clean.empty:
                parts.append(df_clean.to_string(index=False))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

QUESTIONS = [
    ("Q01", "What is G3 Data Feed Configuration?", "DOC-000498", "exact"),
    ("Q02", "What is the RPM configuration process?", "DOC-000505", "exact"),
    ("Q03", "What is the Delphi Installation process?", "DOC-000497", "exact"),
    ("Q04", "How to configure Demand360 in G3 RMS?", "DOC-000499", "exact"),
    ("Q05", "How to configure STR in G3 RMS?", "DOC-000500", "exact"),
    ("Q06", "What is G3 RSS Configuration?", "DOC-000501", "acronym"),
    ("Q07", "How does RMS D360 SFDC workflow work?", "DOC-000491", "acronym"),
    ("Q08", "How to handle duplicate group deletion?", "DOC-000502", "workflow"),
    ("Q09", "What is the Property Merge-Split workflow?", "DOC-000489", "workflow"),
    ("Q10", "What is the Rate Shopping Migration workflow?", "DOC-000490", "workflow"),
    ("Q11", "What is the Include/Exclude Room Types workflow?", "DOC-000492", "configuration"),
    ("Q12", "What is the SSD to OCIM migration?", "DOC-000495", "configuration"),
    ("Q13", "What is the AMS Recoding process?", "DOC-000493", "process"),
    ("Q14", "What is the De-Installation NGI process?", "DOC-000494", "process"),
    ("Q15", "What is Synthetic History to Standard Switch?", "DOC-000506", "process"),
    ("Q16", "What is the ClientSpecific MS Recoding Process?", "DOC-000496", "process"),
    ("Q17", "What is G3 Proactive Monitoring for Data Discrepancy?", "DOC-000487", "cross-doc"),
    ("Q18", "What is the G3 Stats to Inventory Transition?", "DOC-000488", "cross-doc"),
    ("Q19", "What is the Price Grid to Daily Continuous Pricing workflow?", "DOC-000504", "semantic"),
    ("Q20", "What are the Pricing Issues procedures?", "DOC-000507", "semantic"),
]

# The 5 failing queries
FAILING = {"Q01", "Q10", "Q13", "Q17", "Q18"}

# XLSX docs that could benefit from improved extraction
XLSX_DOCS = {
    "DOC-000490", "DOC-000493", "DOC-000487", "DOC-000488",
    "DOC-000489", "DOC-000491", "DOC-000492", "DOC-000495",
    "DOC-000496", "DOC-000497", "DOC-000498", "DOC-000499",
    "DOC-000500", "DOC-000501", "DOC-000502", "DOC-000504",
    "DOC-000505", "DOC-000506", "DOC-000507",
}


def main() -> None:
    conn = get_connection()
    extractor_text = __import__(
        "kurukshetra.extractors.text_extractor", fromlist=["TextExtractor"]
    ).TextExtractor()

    print("=" * 70)
    print("OFFLINE EXPERIMENT: XLSX REPRESENTATION")
    print("=" * 70)

    # Step 1: Show improved extraction for failing XLSX docs
    print("\n--- Improved extraction examples ---")
    for doc_id in ["DOC-000493", "DOC-000487", "DOC-000488"]:
        row = conn.execute(
            "SELECT source_path, title FROM documents WHERE document_id = ?",
            [doc_id],
        ).fetchone()
        if not row:
            continue
        source_path, title = row
        path = Path(source_path)

        print(f"\n  {doc_id}: {title}")

        # Current extraction
        try:
            current = extractor_text.extract(path) or ""
            print(f"  CURRENT: {len(current)} chars, starts with: {current[:80]}...")
        except Exception as e:
            print(f"  CURRENT: ERROR {e}")
            current = ""

        # Improved extraction
        try:
            improved = improved_extract_xlsx(path)
            print(f"  IMPROVED: {len(improved)} chars, starts with: {improved[:80]}...")
        except Exception as e:
            print(f"  IMPROVED: ERROR {e}")
            improved = ""

    # Step 2: Build experimental retrieval index with improved XLSX chunks
    print("\n--- Building experimental chunks ---")

    # Load current chunks
    all_chunks = conn.execute("SELECT chunk_id, document_id, text FROM chunks").fetchall()
    chunk_map = {cid: (did, text) for cid, did, text in all_chunks}
    print(f"  Current chunks: {len(chunk_map)}")

    # Build improved chunks for XLSX docs
    improved_texts = {}
    for doc_id in XLSX_DOCS:
        row = conn.execute(
            "SELECT source_path FROM documents WHERE document_id = ?", [doc_id]
        ).fetchone()
        if not row:
            continue
        path = Path(row[0])
        if not path.exists():
            continue
        try:
            improved = improved_extract_xlsx(path)
            if improved and len(improved) > 100:
                improved_texts[doc_id] = improved
        except Exception:
            pass

    print(f"  XLSX docs with improved extraction: {len(improved_texts)}")

    # Step 3: Create simulated retrieval using BM25 on improved texts
    # We'll build a simple BM25 index over the improved chunks
    from kurukshetra.retrieval.bm25 import BM25Retriever

    # Create experimental chunks: keep non-XLSX chunks, replace XLSX chunks
    experimental_chunks = []
    for cid, (did, text) in chunk_map.items():
        if did in improved_texts:
            # Replace with improved text, split into chunks
            imp_text = improved_texts[did]
            # Simple chunking: split at 1000 chars
            for i in range(0, len(imp_text), 1000):
                chunk_text = imp_text[i : i + 1000]
                experimental_chunks.append(
                    RetrievalResult(
                        chunk_id=f"{cid}-IMP-{i:06d}",
                        document_id=did,
                        score=0.0,
                        text=chunk_text,
                        metadata={},
                    )
                )
        else:
            experimental_chunks.append(
                RetrievalResult(
                    chunk_id=cid,
                    document_id=did,
                    score=0.0,
                    text=text,
                    metadata={},
                )
            )

    print(f"  Experimental chunks: {len(experimental_chunks)}")

    # Build BM25 index on experimental chunks
    exp_bm25 = BM25Retriever(experimental_chunks)

    # Also load the current BM25
    from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
    current_bm25 = DatabaseBM25Retriever()

    # Step 4: Run benchmark
    print("\n--- Benchmark ---")
    print(f"{'QID':5s} {'Type':12s} {'Current':10s} {'Improved':10s} {'Better?':8s}")
    print("-" * 50)

    current_h3 = 0
    improved_h3 = 0
    current_h5 = 0
    improved_h5 = 0
    current_mrr = 0.0
    improved_mrr = 0.0

    for qid, query, expected, qtype in QUESTIONS:
        # Current BM25
        t0 = time.time()
        curr_results = current_bm25.search(query, top_k=5)
        curr_lat = (time.time() - t0) * 1000

        # Improved BM25
        t0 = time.time()
        imp_results = exp_bm25.search(query, top_k=5)
        imp_lat = (time.time() - t0) * 1000

        curr_docs = [r.document_id for r in curr_results]
        imp_docs = [r.document_id for r in imp_results]

        curr_hit = expected in curr_docs[:3]
        imp_hit = expected in imp_docs[:3]
        curr_hit5 = expected in curr_docs[:5]
        imp_hit5 = expected in imp_docs[:5]

        curr_rank = curr_docs.index(expected) + 1 if expected in curr_docs else 0
        imp_rank = imp_docs.index(expected) + 1 if expected in imp_docs else 0

        if curr_hit:
            current_h3 += 1
        if imp_hit:
            improved_h3 += 1
        if curr_hit5:
            current_h5 += 1
        if imp_hit5:
            improved_h5 += 1
        if curr_rank > 0:
            current_mrr += 1.0 / curr_rank
        if imp_rank > 0:
            improved_mrr += 1.0 / imp_rank

        better = ""
        if not curr_hit and imp_hit:
            better = "***"
        elif curr_hit and not imp_hit:
            better = "WORSE"
        elif curr_rank != imp_rank and curr_rank > 0 and imp_rank > 0:
            better = f"r{curr_rank}->r{imp_rank}"

        marker = " <--FAIL" if qid in FAILING else ""
        curr_str = f"r{curr_rank}" if curr_rank else "-"
        imp_str = f"r{imp_rank}" if imp_rank else "-"
        print(
            f"{qid:5s} {qtype:12s} {curr_str:9s} {imp_str:9s} {better:8s}{marker}"
        )

    n = len(QUESTIONS)
    print(f"\n--- Summary ---")
    print(f"  Current:  R@3={current_h3}/{n}={current_h3/n*100:.0f}%  R@5={current_h5}/{n}={current_h5/n*100:.0f}%  MRR={current_mrr/n:.3f}")
    print(f"  Improved: R@3={improved_h3}/{n}={improved_h3/n*100:.0f}%  R@5={improved_h5}/{n}={improved_h5/n*100:.0f}%  MRR={improved_mrr/n:.3f}")
    print(f"  Delta:    R@3={improved_h3-current_h3:+d}  R@5={improved_h5-current_h5:+d}  MRR={improved_mrr-current_mrr:+.3f}")

    # Step 5: Focus on failing queries
    print(f"\n--- Failing Query Deep Dive ---")
    for qid, query, expected, qtype in QUESTIONS:
        if qid not in FAILING:
            continue

        curr_results = current_bm25.search(query, top_k=10)
        imp_results = exp_bm25.search(query, top_k=10)

        curr_docs = [r.document_id for r in curr_results]
        imp_docs = [r.document_id for r in imp_results]

        curr_rank = curr_docs.index(expected) + 1 if expected in curr_docs else 0
        imp_rank = imp_docs.index(expected) + 1 if expected in imp_docs else 0

        print(f"\n  {qid}: {query}")
        print(f"    Expected: {expected}")
        print(f"    Current BM25 rank: {curr_rank or 'NOT FOUND'}")
        print(f"    Improved BM25 rank: {imp_rank or 'NOT FOUND'}")

        if imp_rank and (not curr_rank or imp_rank < curr_rank):
            print(f"    IMPROVEMENT: {curr_rank or 'NOT FOUND'} -> {imp_rank}")
        elif imp_rank and curr_rank and imp_rank > curr_rank:
            print(f"    REGRESSION: {curr_rank} -> {imp_rank}")
        elif not imp_rank and not curr_rank:
            print(f"    NO CHANGE: both miss")
        else:
            print(f"    NO CHANGE: both find at same rank")

    conn.close()

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
