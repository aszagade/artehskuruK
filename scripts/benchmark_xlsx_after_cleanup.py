"""
Mission 3.13 Phase 3-4: XLSX extraction benchmark after corpus cleanup.
Tests improved extraction with same chunk boundaries to avoid Q09/Q12 regressions.
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
from kurukshetra.retrieval.bm25 import BM25Retriever
from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
from kurukshetra.retrieval.models import RetrievalResult


def improved_extract_xlsx(file_path: Path) -> str:
    """Improved extraction that handles SFDC workflow label-value layouts."""
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

FAILING = {"Q01", "Q10", "Q13", "Q17", "Q18"}
REGRESSION_RISK = {"Q09", "Q12"}


def main() -> None:
    conn = get_connection()

    # Load current chunks
    all_chunks = conn.execute(
        "SELECT chunk_id, document_id, text FROM chunks"
    ).fetchall()
    print(f"Current chunks: {len(all_chunks)}")

    # Get ICS XLSX/XLS document IDs
    xlsx_docs = conn.execute("""
        SELECT document_id, source_path FROM documents
        WHERE source_path LIKE '%ina6fs01%'
        AND (source_path LIKE '%.xlsx' OR source_path LIKE '%.xls')
    """).fetchall()
    print(f"ICS XLSX/XLS documents: {len(xlsx_docs)}")

    # Build experimental chunks: improve XLSX text, re-chunk at same 1000-char boundaries
    experimental_chunks: list[RetrievalResult] = []
    improved_count = 0
    xlsx_doc_ids = {did for did, _ in xlsx_docs}
    xlsx_source = {did: src for did, src in xlsx_docs}

    for cid, did, text in all_chunks:
        if did in xlsx_doc_ids:
            path = Path(xlsx_source[did])
            if path.exists():
                try:
                    improved = improved_extract_xlsx(path)
                    if improved and len(improved) > 50:
                        for i in range(0, len(improved), 1000):
                            experimental_chunks.append(RetrievalResult(
                                chunk_id=f"{cid}-IMP{i:06d}",
                                document_id=did,
                                score=0.0,
                                text=improved[i:i + 1000],
                                metadata={},
                            ))
                        improved_count += 1
                    else:
                        experimental_chunks.append(RetrievalResult(
                            chunk_id=cid, document_id=did, score=0.0,
                            text=text, metadata={},
                        ))
                except Exception:
                    experimental_chunks.append(RetrievalResult(
                        chunk_id=cid, document_id=did, score=0.0,
                        text=text, metadata={},
                    ))
            else:
                experimental_chunks.append(RetrievalResult(
                    chunk_id=cid, document_id=did, score=0.0,
                    text=text, metadata={},
                ))
        else:
            experimental_chunks.append(RetrievalResult(
                chunk_id=cid, document_id=did, score=0.0,
                text=text, metadata={},
            ))

    print(f"Experimental chunks: {len(experimental_chunks)}")
    print(f"XLSX docs improved: {improved_count}")

    # Build indices
    current_bm25 = DatabaseBM25Retriever()
    exp_bm25 = BM25Retriever(experimental_chunks)

    # Benchmark
    print()
    print("=" * 70)
    print("BENCHMARK: Current vs Improved XLSX (same chunk boundaries)")
    print("=" * 70)
    header = f"{'QID':5s} {'Type':12s} {'Current':9s} {'Improved':9s} {'Status':12s}"
    print(header)
    print("-" * 55)

    c_h3 = c_h5 = c_mrr = 0
    i_h3 = i_h5 = i_mrr = 0
    regressions = []

    for qid, query, expected, qtype in QUESTIONS:
        curr = current_bm25.search(query, top_k=5)
        imp = exp_bm25.search(query, top_k=5)

        c_docs = [r.document_id for r in curr]
        i_docs = [r.document_id for r in imp]

        c_rank = c_docs.index(expected) + 1 if expected in c_docs else 0
        i_rank = i_docs.index(expected) + 1 if expected in i_docs else 0

        c_h3 += 1 if expected in c_docs[:3] else 0
        c_h5 += 1 if expected in c_docs[:5] else 0
        i_h3 += 1 if expected in i_docs[:3] else 0
        i_h5 += 1 if expected in i_docs[:5] else 0
        if c_rank > 0:
            c_mrr += 1.0 / c_rank
        if i_rank > 0:
            i_mrr += 1.0 / i_rank

        status = ""
        if qid in FAILING:
            if c_rank == 0 and i_rank > 0:
                status = "*** FIXED"
            elif i_rank > 0 and (c_rank == 0 or i_rank < c_rank):
                status = "IMPROVED"
            elif i_rank == 0 and c_rank > 0:
                status = "REGRESSION"
            else:
                status = "unchanged"
        elif qid in REGRESSION_RISK:
            if c_rank > 0 and i_rank == 0:
                status = "REGRESSION!"
                regressions.append(qid)
            elif c_rank > 0 and i_rank > c_rank:
                status = "regression"
                regressions.append(qid)
            elif c_rank == i_rank:
                status = "safe"
            else:
                status = "improved"
        else:
            if c_rank == i_rank:
                status = "safe"
            elif c_rank > 0 and i_rank == 0:
                status = "REGRESSION"
                regressions.append(qid)
            elif i_rank > 0 and c_rank == 0:
                status = "improved"
            elif i_rank < c_rank:
                status = "improved"
            else:
                status = "regression"

        c_str = f"r{c_rank}" if c_rank else "-"
        i_str = f"r{i_rank}" if i_rank else "-"
        print(f"{qid:5s} {qtype:12s} {c_str:9s} {i_str:9s} {status:12s}")

    n = len(QUESTIONS)
    print()
    print("--- Summary ---")
    print(f"  Current:  R@3={c_h3}/{n}={c_h3/n*100:.0f}%  R@5={c_h5}/{n}={c_h5/n*100:.0f}%  MRR={c_mrr/n:.3f}")
    print(f"  Improved: R@3={i_h3}/{n}={i_h3/n*100:.0f}%  R@5={i_h5}/{n}={i_h5/n*100:.0f}%  MRR={i_mrr/n:.3f}")
    print(f"  Delta:    R@3={i_h3-c_h3:+d}  R@5={i_h5-c_h5:+d}  MRR={i_mrr-c_mrr:+.3f}")

    print()
    if regressions:
        print(f"REGRESSIONS: {regressions}")
    else:
        print("NO REGRESSIONS DETECTED")

    conn.close()


if __name__ == "__main__":
    main()
