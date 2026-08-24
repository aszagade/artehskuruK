"""
Mission 3.7 — Controlled Real Knowledge Ingestion

Ingests ONLY: \\ina6fs01\Dept_shares\ICS\Omkar\Process Documents

READ-ONLY on source. Uses canonical IngestionPipeline.
Captures structured ingestion report.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kurukshetra.extractors.text_extractor import TextExtractor
from kurukshetra.pipeline.ingest import IngestionPipeline, IngestionResult


SOURCE = Path(r"\\ina6fs01\Dept_shares\ICS\Omkar\Process Documents")
REPORT_PATH = Path("reports/omkar_ingestion_report.json")
SUPPORTED = TextExtractor.supported_extensions()


@dataclass
class IngestionReport:
    """Machine-readable ingestion report."""
    source_path: str
    started_at: str
    completed_at: str = ""
    elapsed_seconds: float = 0.0
    documents_seen: int = 0
    documents_ingested: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    chunks_created: int = 0
    entities_created: int = 0
    relationships_created: int = 0
    evidence_created: int = 0
    unknown_terms: int = 0
    teams_detected: list[str] = field(default_factory=list)
    content_types: dict[str, int] = field(default_factory=dict)
    extensions: dict[str, int] = field(default_factory=dict)
    failure_reasons: list[dict] = field(default_factory=list)
    document_details: list[dict] = field(default_factory=list)
    source_was_modified: bool = False


def run() -> IngestionReport:
    report = IngestionReport(
        source_path=str(SOURCE),
        started_at=datetime.now().isoformat(),
    )

    # Capture pre-ingestion baseline
    from kurukshetra.registry import get_connection
    conn = get_connection()
    baseline = {
        "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "graph_entities": conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0],
        "graph_relationships": conn.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()[0],
        "graph_evidence": conn.execute("SELECT COUNT(*) FROM graph_evidence").fetchone()[0],
        "unknown_terms": conn.execute("SELECT COUNT(*) FROM unknown_terms").fetchone()[0],
    }
    conn.close()

    print(f"\n{'='*60}")
    print(f"MISSION 3.7 — CONTROLLED REAL KNOWLEDGE INGESTION")
    print(f"{'='*60}")
    print(f"  Source:   {SOURCE}")
    print(f"  Mode:     READ-ONLY (source not modified)")
    print(f"  Started:  {report.started_at}")
    print(f"\n  BASELINE:")
    for k, v in baseline.items():
        print(f"    {k:<22} {v:>10,}")

    # 1. Discover files
    print(f"\n{'='*60}")
    print(f"SCANNING SOURCE...")
    print(f"{'='*60}")

    files = []
    unsupported_files = []
    for entry in SOURCE.rglob("*"):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        report.extensions[ext] = report.extensions.get(ext, 0) + 1
        report.documents_seen += 1

        if ext in SUPPORTED:
            files.append(entry)
        else:
            unsupported_files.append(entry.name)
            report.documents_skipped += 1

    print(f"  Files discovered:   {report.documents_seen}")
    print(f"  Supported:          {len(files)}")
    print(f"  Unsupported:        {len(unsupported_files)}")
    if unsupported_files:
        for name in unsupported_files:
            print(f"    - {name}")

    # 2. Ingest
    print(f"\n{'='*60}")
    print(f"INGESTING...")
    print(f"{'='*60}")

    pipeline = IngestionPipeline(use_semantic_chunking=False, build_embeddings=False)
    start_time = time.time()

    for i, file_path in enumerate(sorted(files), start=1):
        ext = file_path.suffix.lower()
        name = file_path.name[:55]
        print(f"  [{i:>2}/{len(files)}] {name:<55} ", end="", flush=True)

        try:
            # Verify source is not modified before ingestion
            mtime_before = file_path.stat().st_mtime

            result = pipeline.ingest(file_path)

            # Verify source was not modified after ingestion
            mtime_after = file_path.stat().st_mtime
            if mtime_before != mtime_after:
                report.source_was_modified = True
                print("WARNING: SOURCE MODIFIED!")

            if result.error:
                report.documents_failed += 1
                report.failure_reasons.append({
                    "file": file_path.name,
                    "error": result.error,
                })
                print(f"FAIL: {result.error[:40]}")
            else:
                report.documents_ingested += 1
                report.chunks_created += result.chunks_stored
                report.entities_created += result.entities_extracted
                report.relationships_created += result.relationships_extracted
                report.unknown_terms += result.unknown_terms

                if result.team_id and result.team_id != "unknown":
                    if result.team_id not in report.teams_detected:
                        report.teams_detected.append(result.team_id)

                ct = result.stages.get("classify_content", "unknown")
                report.content_types[ct] = report.content_types.get(ct, 0) + 1

                report.document_details.append({
                    "file": file_path.name,
                    "document_id": result.document_id,
                    "team": result.team_id,
                    "chunks": result.chunks_stored,
                    "entities": result.entities_extracted,
                    "relationships": result.relationships_extracted,
                    "unknown_terms": result.unknown_terms,
                    "stages": result.stages,
                })

                stages_str = " -> ".join(
                    f"{k}:{v.split(':')[0]}" for k, v in result.stages.items()
                )
                print(f"OK  {result.chunks_stored}ch {result.entities_extracted}en {result.unknown_terms}ut")

        except Exception as e:
            report.documents_failed += 1
            report.failure_reasons.append({
                "file": file_path.name,
                "error": str(e),
            })
            print(f"ERR: {str(e)[:40]}")

    elapsed = time.time() - start_time
    report.elapsed_seconds = round(elapsed, 1)
    report.completed_at = datetime.now().isoformat()

    # 3. Post-ingestion baseline
    conn = get_connection()
    after = {
        "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "graph_entities": conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0],
        "graph_relationships": conn.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()[0],
        "graph_evidence": conn.execute("SELECT COUNT(*) FROM graph_evidence").fetchone()[0],
        "unknown_terms": conn.execute("SELECT COUNT(*) FROM unknown_terms").fetchone()[0],
    }
    conn.close()

    # 4. Print summary
    print(f"\n{'='*60}")
    print(f"INGESTION COMPLETE")
    print(f"{'='*60}")
    print(f"  Elapsed:            {elapsed:.1f}s")
    print(f"  Documents seen:     {report.documents_seen}")
    print(f"  Documents ingested: {report.documents_ingested}")
    print(f"  Documents skipped:  {report.documents_skipped}")
    print(f"  Documents failed:   {report.documents_failed}")
    print(f"  Chunks created:     {report.chunks_created}")
    print(f"  Entities created:   {report.entities_created}")
    print(f"  Relationships:      {report.relationships_created}")
    print(f"  Unknown terms:      {report.unknown_terms}")
    print(f"  Teams detected:     {report.teams_detected}")
    print(f"  Source modified:    {report.source_was_modified}")

    print(f"\n  DELTA:")
    for k in baseline:
        delta = after[k] - baseline[k]
        if delta > 0:
            print(f"    {k:<22} {baseline[k]:>10,} -> {after[k]:>10,} (+{delta:,})")
        else:
            print(f"    {k:<22} {after[k]:>10,} (unchanged)")

    if report.failure_reasons:
        print(f"\n  FAILURES:")
        for f in report.failure_reasons:
            print(f"    - {f['file']}: {f['error'][:60]}")

    # 5. Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(asdict(report), f, indent=2, default=str)
    print(f"\n  Report saved: {REPORT_PATH}")

    pipeline.close()
    return report


if __name__ == "__main__":
    run()
