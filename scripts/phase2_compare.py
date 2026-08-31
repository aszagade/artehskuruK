"""
Mission 3.14 Phase 2: Compare extraction representations.

A. Current (original)
B. Mission 3.13 improved (full restructure)
C. Minimal NaN/header cleanup (strip noise, preserve structure)
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


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_current(file_path: Path) -> str:
    """Current production extraction."""
    from kurukshetra.extractors.text_extractor import TextExtractor
    return TextExtractor().extract(file_path) or ""


def extract_improved(file_path: Path) -> str:
    """Mission 3.13 improved extraction (full restructure)."""
    try:
        xl = pd.ExcelFile(str(file_path), engine="openpyxl")
    except Exception:
        return ""
    parts: list[str] = []
    header_keywords = {
        "task subject", "trigger", "due date", "assigned to",
        "task comments", "case opens", "changes", "any other comments",
        "workflow", "description", "requested by",
    }
    for sheet_name in xl.sheet_names:
        df_raw = pd.read_excel(
            str(file_path), sheet_name=sheet_name,
            engine="openpyxl", header=None,
        )
        if df_raw.empty:
            continue
        header_row_idx = None
        for i in range(min(10, len(df_raw))):
            row_text = " ".join(
                str(v).lower() for v in df_raw.iloc[i].values if pd.notna(v)
            )
            if any(kw in row_text for kw in header_keywords):
                header_row_idx = i
                break
        if header_row_idx is not None:
            headers = [
                str(v).strip() if pd.notna(v) else f"col_{j}"
                for j, v in enumerate(df_raw.iloc[header_row_idx].values)
            ]
            data_df = df_raw.iloc[header_row_idx + 1:].copy()
            data_df.columns = headers
            keep_cols = [c for c in data_df.columns if not c.startswith("col_")]
            if not keep_cols:
                keep_cols = list(data_df.columns)
            data_df = data_df[keep_cols]
            data_df = data_df.dropna(how="all")
            parts.append(f"--- Sheet: {sheet_name} ---")
            parts.append(data_df.to_string(index=False))
        else:
            parts.append(f"--- Sheet: {sheet_name} ---")
            df_clean = df_raw.dropna(how="all")
            if not df_clean.empty:
                parts.append(df_clean.to_string(index=False))
    return "\n".join(parts)


def extract_minimal_cleanup(file_path: Path) -> str:
    """Minimal cleanup: strip NaN padding and Unnamed headers, preserve structure."""
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
        # Drop rows that are ALL NaN
        df_clean = df_raw.dropna(how="all")
        if df_clean.empty:
            continue

        # For each row, drop trailing NaN cells
        cleaned_rows = []
        for _, row in df_clean.iterrows():
            vals = [str(v) if pd.notna(v) else "" for v in row.values]
            # Strip trailing empty cells
            while vals and vals[-1] == "":
                vals.pop()
            # Strip leading empty cells
            while vals and vals[0] == "":
                vals.pop(0)
            if vals:
                cleaned_rows.append(" | ".join(vals))

        if cleaned_rows:
            parts.append(f"--- Sheet: {sheet_name} ---")
            parts.append("\n".join(cleaned_rows))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

KEY_QUERIES = [
    ("Q09", "What is the Property Merge-Split workflow?", "DOC-000489"),
    ("Q12", "What is the SSD to OCIM migration?", "DOC-000495"),
    ("Q13", "What is the AMS Recoding process?", "DOC-000493"),
    ("Q17", "What is G3 Proactive Monitoring for Data Discrepancy?", "DOC-000487"),
    ("Q18", "What is the G3 Stats to Inventory Transition?", "DOC-000488"),
]

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


def build_bm25_for_doc(doc_id: str, text: str) -> list[RetrievalResult]:
    """Create chunks from text at 1000-char boundaries."""
    chunks = []
    for i in range(0, len(text), 1000):
        chunks.append(RetrievalResult(
            chunk_id=f"{doc_id}-EXP{i:06d}",
            document_id=doc_id,
            score=0.0,
            text=text[i:i + 1000],
            metadata={},
        ))
    return chunks


def main() -> None:
    conn = get_connection()

    # Get all current chunks
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

    print("=" * 70)
    print("PHASE 2: COMPARE EXTRACTION REPRESENTATIONS")
    print("=" * 70)

    # For each representation, build chunks and benchmark
    extractors = {
        "A_current": extract_current,
        "B_improved": extract_improved,
        "C_minimal": extract_minimal_cleanup,
    }

    all_results = {}

    for ext_name, ext_func in extractors.items():
        print(f"\n--- Building chunks for {ext_name} ---")

        # Build experimental chunks
        exp_chunks: list[RetrievalResult] = []
        improved_count = 0
        for cid, did, text in all_chunks_data:
            if did in xlsx_ids:
                path = Path(xlsx_sources[did])
                if path.exists():
                    try:
                        improved = ext_func(path)
                        if improved and len(improved) > 50:
                            exp_chunks.extend(build_bm25_for_doc(did, improved))
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

        # Benchmark key queries
        results = {}
        for qid, query, expected in FULL_BENCHMARK:
            search_results = bm25.search(query, top_k=5)
            docs = [r.document_id for r in search_results]
            rank = docs.index(expected) + 1 if expected in docs else 0
            results[qid] = rank

        all_results[ext_name] = results

    # Compare key queries
    print("\n" + "=" * 70)
    print("KEY QUERY COMPARISON")
    print("=" * 70)
    header = f"{'QID':5s} {'A_current':10s} {'B_improved':10s} {'C_minimal':10s}"
    print(header)
    print("-" * 40)

    for qid, query, expected in KEY_QUERIES:
        a = all_results["A_current"].get(qid, 0)
        b = all_results["B_improved"].get(qid, 0)
        c = all_results["C_minimal"].get(qid, 0)
        a_str = f"r{a}" if a else "-"
        b_str = f"r{b}" if b else "-"
        c_str = f"r{c}" if c else "-"
        print(f"{qid:5s} {a_str:10s} {b_str:10s} {c_str:10s}")

    # Full benchmark comparison
    print("\n" + "=" * 70)
    print("FULL 20-QUESTION BENCHMARK")
    print("=" * 70)

    for ext_name in ["A_current", "B_improved", "C_minimal"]:
        h3 = sum(1 for qid, _, _ in FULL_BENCHMARK
                 if all_results[ext_name].get(qid, 0) in (1, 2, 3))
        h5 = sum(1 for qid, _, _ in FULL_BENCHMARK
                 if 0 < all_results[ext_name].get(qid, 0) <= 5)
        mrr = sum(
            1.0 / all_results[ext_name][qid]
            for qid, _, _ in FULL_BENCHMARK
            if all_results[ext_name].get(qid, 0) > 0
        ) / len(FULL_BENCHMARK)
        print(f"  {ext_name:15s} R@3={h3}/20={h3/20*100:.0f}%  R@5={h5}/20={h5/20*100:.0f}%  MRR={mrr:.3f}")

    # Extraction quality comparison for key docs
    print("\n" + "=" * 70)
    print("EXTRACTION QUALITY")
    print("=" * 70)

    for qid, query, expected in KEY_QUERIES:
        row = conn.execute(
            "SELECT source_path FROM documents WHERE document_id = ?", [expected]
        ).fetchone()
        if not row:
            continue
        path = Path(row[0])
        if not path.exists():
            continue

        print(f"\n  {qid}: {expected}")
        for ext_name, ext_func in extractors.items():
            try:
                text = ext_func(path)
                nan_count = text.lower().count("nan")
                unnamed_count = text.count("Unnamed")
                print(f"    {ext_name:12s}: {len(text):6d} chars  NaN={nan_count:4d}  Unnamed={unnamed_count:3d}")
            except Exception as e:
                print(f"    {ext_name:12s}: ERROR {e}")

    conn.close()


if __name__ == "__main__":
    main()
