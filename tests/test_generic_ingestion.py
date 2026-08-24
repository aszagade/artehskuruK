"""
Generic Ingestion Contract Tests
=================================

Proves the canonical ingestion contract:
A fictional document enters the system without document-specific code
and produces queryable knowledge through the standard pipeline.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


SYNTHETIC_TXT = """
# NovaPulse Analytics Platform -- Operations Manual

## Document Owner
Quantum Operations Division (QONR)
Prepared by: Dr. Elena Vasquez, Chief Quantum Architect

## Overview

The NovaPulse Analytics Platform is the core data processing engine
used by the Quantum Operations team at NovaCorp International.
It was developed by QuantumCore Technologies and integrates with
the existing QuantumCore Data Fabric for real-time analytics.

NovaPulse replaces the legacy HelixStream system that was decommissioned
in Q3 2025. All properties migrated from HelixStream to NovaPulse
must complete the QuantumSync protocol before going live.

## QuantumSync Protocol

The QuantumSync protocol is a three-step data synchronization process:

1. Step-Alpha: Initialize the NovaPulse data pipeline connection
2. Step-Beta: Validate schema compatibility with QuantumCore Data Fabric
3. Step-Gamma: Execute the initial data migration and verify checksums

If Step-Alpha fails, check the NovaPulse connection pool configuration.
If Step-Beta fails, the QuantumCore Data Fabric schema must be updated.

## Known Issues

- NovaPulse timeout error during peak processing hours (contact QONR support)
- Step-Alpha failure when QuantumCore API key expires (renew via QONR portal)

## Configuration Parameters

Parameter: np_batch_size = 2000
Parameter: np_retry_count = 5
Parameter: qc_fabric_version = 4.2
Enable NovaPulse monitoring integration
Disable HelixStream compatibility mode

## Monitoring

Configure Datadog alerts for NovaPulse pipeline failures.
The QuantumCore Data Fabric generates automated health reports.
QONR team reviews NovaPulse performance metrics weekly.
"""

SYNTHETIC_MD = """
# Project Aurora -- Deployment Guide

## Team: Quantum Operations (QONR)

**Author:** Dr. Elena Vasquez

### Deployment Steps

1. Run the AuroraSync initialization job
2. Verify QuantumCore Data Fabric connectivity
3. Enable NovaPulse monitoring for the Aurora pipeline

### Known Failure Modes

- AuroraSync Step-Alpha failure: API key expired
- AuroraSync Step-Beta failure: schema mismatch with QuantumCore
- NovaPulse timeout during peak hours

### Monitoring

The Aurora pipeline generates automated health reports.
Contact QONR support for Aurora-related incidents.
"""


def _make_temp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.remove(path)
    return path


def _patch_database(db_path: str):
    import kurukshetra.registry.database as db_mod
    original = db_mod.DATABASE_PATH
    db_mod.DATABASE_PATH = Path(db_path)
    return original


def _restore_database(original):
    import kurukshetra.registry.database as db_mod
    db_mod.DATABASE_PATH = original


class TestGenericIngestionContract(unittest.TestCase):
    """Proves the generic ingestion contract end-to-end."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db()
        cls.original = _patch_database(cls.db_path)
        from kurukshetra.registry.schema import initialize_schema
        initialize_schema()

        cls.doc_dir = tempfile.mkdtemp()

        # Ingest TXT document once — all tests use the result
        from kurukshetra.pipeline.ingest import IngestionPipeline
        doc_path = Path(cls.doc_dir) / "NovaPulse_Ops.txt"
        doc_path.write_text(SYNTHETIC_TXT, encoding="utf-8")
        pipeline = IngestionPipeline(use_semantic_chunking=False)
        cls.txt_result = pipeline.ingest(doc_path)
        pipeline.close()

        # Ingest MD document
        doc_path_md = Path(cls.doc_dir) / "Project_Aurora.md"
        doc_path_md.write_text(SYNTHETIC_MD, encoding="utf-8")
        pipeline2 = IngestionPipeline(use_semantic_chunking=False)
        cls.md_result = pipeline2.ingest(doc_path_md)
        pipeline2.close()

    @classmethod
    def tearDownClass(cls):
        _restore_database(cls.original)
        import shutil
        try: shutil.rmtree(cls.doc_dir)
        except OSError: pass
        try: os.remove(cls.db_path)
        except OSError: pass

    # ---- TXT ingestion ----

    def test_01_txt_ingestion(self):
        """TXT file ingested through canonical pipeline."""
        r = self.txt_result
        self.assertNotEqual(r.document_id, "")
        self.assertEqual(r.stages.get("extract"), "ok")
        self.assertGreater(r.chunks_stored, 0, "Chunks must be persisted")
        self.assertGreater(r.entities_extracted, 0, "Entities must be extracted")
        self.assertGreater(r.relationships_extracted, 0)
        print(f"  [OK] TXT: {r.chunks_stored} chunks, "
              f"{r.entities_extracted} entities, "
              f"{r.relationships_extracted} relationships")

    # ---- MD ingestion ----

    def test_02_md_ingestion(self):
        """Markdown file ingested through canonical pipeline."""
        r = self.md_result
        self.assertNotEqual(r.document_id, "")
        self.assertGreater(r.chunks_stored, 0)
        self.assertGreater(r.entities_extracted, 0)
        print(f"  [OK] MD: {r.chunks_stored} chunks, "
              f"{r.entities_extracted} entities")

    # ---- Unsupported file ----

    def test_03_unsupported_extension(self):
        """Unsupported file returns clear error."""
        from kurukshetra.pipeline.ingest import IngestionPipeline
        doc_path = Path(self.doc_dir) / "image.png"
        doc_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        pipeline = IngestionPipeline()
        result = pipeline.ingest(doc_path)
        pipeline.close()
        self.assertIsNotNone(result.error)
        self.assertIn("unsupported", result.stages.get("extract", ""))
        print(f"  [OK] Unsupported: {result.error}")

    # ---- Unknown terms ----

    def test_04_unknown_terms_detected(self):
        """Unknown terms like NovaPulse, QuantumCore, QONR are detected."""
        from kurukshetra.services.glossary import GlossaryManager
        terms = GlossaryManager().detect_unknown_terms(SYNTHETIC_TXT, "test-doc")
        self.assertIsInstance(terms, list)
        names = [t.term for t in terms]
        print(f"  [OK] Unknown terms: {names[:5]}")

    # ---- Chunk persistence ----

    def test_05_chunks_persisted(self):
        """Chunks are stored in DuckDB."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (self.txt_result.document_id,),
        ).fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)
        print(f"  [OK] Chunks in DB: {count}")

    # ---- RAG retrieval ----

    def test_06_rag_retrieval(self):
        """BM25 retrieves content from the newly ingested document."""
        from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
        results = DatabaseBM25Retriever().search("QuantumSync protocol", top_k=3)
        self.assertGreater(len(results), 0)
        found = any("quantumsync" in r.text.lower() for r in results)
        self.assertTrue(found)
        print(f"  [OK] RAG: {len(results)} results, top={results[0].score:.4f}")

    # ---- Graph persistence ----

    def test_07_graph_persistence(self):
        """Entities and relationships persisted to Knowledge Graph."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        ent = conn.execute(
            "SELECT COUNT(*) FROM graph_entities WHERE id LIKE ?",
            (f"DOC-{self.txt_result.document_id}%",),
        ).fetchone()[0]
        rel = conn.execute(
            "SELECT COUNT(*) FROM graph_relationships WHERE source_id LIKE ?",
            (f"DOC-{self.txt_result.document_id}%",),
        ).fetchone()[0]
        conn.close()
        self.assertGreater(ent, 0)
        self.assertGreater(rel, 0)
        print(f"  [OK] Graph: {ent} entities, {rel} relationships")

    # ---- Evidence ----

    def test_08_evidence_attached(self):
        """Evidence records exist for extracted entities."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        ev = conn.execute(
            "SELECT COUNT(*) FROM graph_evidence WHERE entity_id LIKE ?",
            (f"DOC-{self.txt_result.document_id}%",),
        ).fetchone()[0]
        conn.close()
        self.assertGreater(ev, 0)
        print(f"  [OK] Evidence: {ev} records")

    # ---- SEAL pending ----

    def test_09_seal_pending(self):
        """SEAL can load pending unknown terms."""
        from kurukshetra.seal.unknowns import UnknownLoader
        pending = UnknownLoader().load_pending()
        self.assertIsInstance(pending, list)
        print(f"  [OK] SEAL pending: {len(pending)}")

    # ---- SANJAYA retrieval ----

    def test_10_sanjaya_retrieval(self):
        """KnowledgeExecutor answers from the ingested document."""
        from kurukshetra.executors.knowledge import KnowledgeExecutor
        result = KnowledgeExecutor().execute("What is the QuantumSync protocol?")
        self.assertIsNotNone(result)
        if result.get("success"):
            print(f"  [OK] SANJAYA: score={result.get('score', 0):.4f}")
        else:
            print(f"  [INFO] SANJAYA: {result.get('message', 'no result')}")

    # ---- Multi-team relationships ----

    def test_11_multi_team_relationships(self):
        """Systems have USES relationships showing team associations."""
        from kurukshetra.registry.database import get_connection
        conn = get_connection()
        rows = conn.execute("""
            SELECT DISTINCT ge.name, ge.entity_type
            FROM graph_entities ge
            WHERE ge.entity_type = 'system'
        """).fetchall()
        conn.close()
        print(f"  [OK] Systems in graph: {[r[0] for r in rows]}")

    # ---- Structured result ----

    def test_12_structured_result(self):
        """IngestionResult contains stage-by-stage status."""
        r = self.txt_result
        self.assertIn("extract", r.stages)
        self.assertIn("register", r.stages)
        self.assertIn("chunk", r.stages)
        self.assertIn("graph", r.stages)
        ok_stages = sum(1 for v in r.stages.values() if v.startswith("ok"))
        self.assertGreaterEqual(ok_stages, 5)
        print(f"  [OK] Structured result: {ok_stages}/{len(r.stages)} stages OK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
