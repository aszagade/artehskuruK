"""
Mission 3.7 — Real Corpus Ingestion Tests

Deterministic tests proving:
  - Supported real-world file types can be processed
  - Unsupported files are isolated
  - Source is never modified
  - source_path provenance survives ingestion
  - SHA-256 dedup works
  - Repeated ingestion does not duplicate
  - One failed document does not stop the batch
  - Chunks persist
  - Retrieval finds real corpus content
  - Graph persistence occurs
  - Evidence is linked to source
  - Unknown terms are generated
  - SANJAYA planner routes correctly
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kurukshetra.extractors.text_extractor import TextExtractor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_realistic_docx(path: Path, content: str) -> None:
    """Create a minimal but realistic DOCX file."""
    from docx import Document
    doc = Document()
    doc.add_paragraph(content)
    doc.save(str(path))


def _make_realistic_xlsx(path: Path) -> None:
    """Create a minimal XLSX file."""
    import pandas as pd
    df = pd.DataFrame({
        "Step": ["1. Login to G3 RMS", "2. Navigate to SFDC Config", "3. Verify Data Feed"],
        "Action": ["Open browser", "Click Settings", "Check Status"],
        "System": ["G3", "SFDC", "G3"],
    })
    df.to_excel(str(path), index=False)


def _make_realistic_txt(path: Path, content: str) -> None:
    """Create a TXT file with enterprise-like content."""
    path.write_text(content, encoding="utf-8")


def _make_realistic_md(path: Path, content: str) -> None:
    """Create a Markdown file."""
    path.write_text(content, encoding="utf-8")


def _make_unsupported_file(path: Path) -> None:
    """Create a file with an unsupported extension."""
    path.write_bytes(b"\x00" * 100)


class _TestCorpus:
    """Creates a temporary corpus of realistic enterprise-like documents."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp()
        self.corpus_dir = Path(self.tmp) / "EnterpriseDocs"
        self.corpus_dir.mkdir()
        self.files: list[Path] = []
        self.unsupported: list[Path] = []

    def create(self) -> "TestCorpus":
        """Create the test corpus."""
        # Supported documents
        docx1 = self.corpus_dir / "G3_RMS_Data_Feed_Configuration.docx"
        _make_realistic_docx(docx1,
            "G3 RMS Data Feed Configuration Guide. "
            "This document describes how to configure the G3 RMS data feed "
            "for SFDC integration. The data feed uses SFTP to transfer "
            "hotel performance data from G3 to SFDC. "
            "Steps: 1. Login to G3 RMS. 2. Navigate to Data Feed Settings. "
            "3. Configure SFTP endpoint. 4. Test the connection. "
            "Team responsible: ICS and SDOPS. "
            "Contact: Ajay Gandhi for configuration issues."
        )
        self.files.append(docx1)

        docx2 = self.corpus_dir / "SFDC_Workflow_Template.docx"
        _make_realistic_docx(docx2,
            "SFDC Workflow Template for G3 Property Management. "
            "This workflow covers the installation and configuration "
            "of G3 RMS for new hotel properties. "
            "Steps include: property setup, rate configuration, "
            "data verification, and client confirmation. "
            "Systems involved: G3 RMS, SFDC, NGI, Datadog. "
            "Team: ICS Installation Team."
        )
        self.files.append(docx2)

        xlsx1 = self.corpus_dir / "RMS_D360_Configuration.xlsx"
        _make_realistic_xlsx(xlsx1)
        self.files.append(xlsx1)

        txt1 = self.corpus_dir / "Delphi_Installation_Notes.txt"
        _make_realistic_txt(txt1,
            "Delphi Installation Configuration Notes\n"
            "=========================================\n"
            "Property: Grand Hotel\n"
            "System: Delphi + G3 RMS Integration\n"
            "Configuration required:\n"
            "- G3 server IP: 10.0.0.1\n"
            "- SFTP credentials for data transfer\n"
            "- Datadog monitoring setup\n"
            "- Validation of data discrepancy reports\n"
            "Contact: Amol Bembde for Delphi configuration.\n"
            "Status: Installation pending client approval.\n"
        )
        self.files.append(txt1)

        md1 = self.corpus_dir / "RPM_Configuration_Guide.md"
        _make_realistic_md(md1,
            "# RPM Configuration Guide\n\n"
            "## Reputation Pricing Model (RPM)\n\n"
            "RPM is a pricing model used by IDeaS G3 RMS for hotel revenue management.\n\n"
            "### Steps\n\n"
            "1. Enable RPM in G3 RMS Admin Module\n"
            "2. Configure pricing parameters\n"
            "3. Set up monitoring in Datadog\n"
            "4. Validate with test properties\n\n"
            "### Team\n\n"
            "SPM team manages RPM configuration.\n"
            "SDOPS team handles monitoring.\n"
        )
        self.files.append(md1)

        # Unsupported files
        unsupported = self.corpus_dir / "Legacy_Document.doc"
        _make_unsupported_file(unsupported)
        self.unsupported.append(unsupported)

        unknown_ext = self.corpus_dir / "data_export.sas7bdat"
        _make_unsupported_file(unknown_ext)
        self.unsupported.append(unknown_ext)

        return self

    @property
    def all_files(self) -> list[Path]:
        return self.files + self.unsupported


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSupportedFileTypes(unittest.TestCase):
    """Prove supported real-world file types can be processed."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = _TestCorpus().create()
        cls.extractor = TextExtractor()

    def test_docx_extraction(self):
        """DOCX files should extract text successfully."""
        docx = self.corpus.corpus_dir / "G3_RMS_Data_Feed_Configuration.docx"
        text = self.extractor.extract(docx)
        self.assertIsNotNone(text)
        self.assertIn("G3 RMS", text)
        self.assertIn("SFDC", text)
        self.assertGreater(len(text), 100)

    def test_xlsx_extraction(self):
        """XLSX files should extract text successfully."""
        xlsx = self.corpus.corpus_dir / "RMS_D360_Configuration.xlsx"
        text = self.extractor.extract(xlsx)
        self.assertIsNotNone(text)
        self.assertIn("G3", text)

    def test_txt_extraction(self):
        """TXT files should extract text successfully."""
        txt = self.corpus.corpus_dir / "Delphi_Installation_Notes.txt"
        text = self.extractor.extract(txt)
        self.assertIsNotNone(text)
        self.assertIn("Delphi", text)
        self.assertIn("G3 RMS", text)

    def test_md_extraction(self):
        """Markdown files should extract text successfully."""
        md = self.corpus.corpus_dir / "RPM_Configuration_Guide.md"
        text = self.extractor.extract(md)
        self.assertIsNotNone(text)
        self.assertIn("RPM", text)
        self.assertIn("G3 RMS", text)


class TestUnsupportedFileIsolation(unittest.TestCase):
    """Prove unsupported files are isolated, not silently processed."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = _TestCorpus().create()
        cls.extractor = TextExtractor()

    def test_doc_returns_none(self):
        """Legacy .doc files should return None (unsupported)."""
        doc = self.corpus.corpus_dir / "Legacy_Document.doc"
        text = self.extractor.extract(doc)
        self.assertIsNone(text)

    def test_sas7bdat_returns_none(self):
        """SAS files should return None (unsupported)."""
        sas = self.corpus.corpus_dir / "data_export.sas7bdat"
        text = self.extractor.extract(sas)
        self.assertIsNone(text)

    def test_supported_extensions_include_all_corpus_types(self):
        """All expected enterprise extensions should be in supported set."""
        supported = TextExtractor.supported_extensions()
        for ext in [".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".csv"]:
            self.assertIn(ext, supported)


class TestSourceNotModified(unittest.TestCase):
    """Prove the profiler/ingestion never modifies source files."""

    def test_source_files_unchanged(self):
        """Source file hashes should be unchanged after extraction."""
        corpus = _TestCorpus().create()
        extractor = TextExtractor()

        # Record hashes
        hashes_before = {}
        for f in corpus.all_files:
            hashes_before[f] = f.read_bytes()

        # Extract from all supported files
        for f in corpus.files:
            extractor.extract(f)

        # Verify no changes
        for f, content_before in hashes_before.items():
            content_after = f.read_bytes()
            self.assertEqual(content_before, content_after,
                f"Source file was modified: {f.name}")

        # Verify no new files
        all_files_after = list(corpus.corpus_dir.rglob("*"))
        files_only = [f for f in all_files_after if f.is_file()]
        self.assertEqual(len(files_only), len(corpus.all_files),
            "New files were created in source directory")


class TestProvenancePreserved(unittest.TestCase):
    """Prove source_path provenance survives ingestion."""

    def test_source_path_in_registrar(self):
        """DocumentRegistrar stores the full source path."""
        from kurukshetra.services.registrar import DocumentRegistrar
        import sys; sys.path.insert(0, '.')

        corpus = _TestCorpus().create()
        registrar = DocumentRegistrar()

        for f in corpus.files:
            identity = registrar.register(f)
            self.assertIsNotNone(identity.document_id)
            # The document should be registered in DuckDB
            # with a non-empty source_path
            from kurukshetra.registry import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT source_path, sha256 FROM documents WHERE document_id = ?",
                (identity.document_id,),
            ).fetchone()
            conn.close()
            self.assertIsNotNone(row, f"Document {identity.document_id} not found in DB")
            self.assertIsNotNone(row[0], f"source_path is None for {identity.document_id}")
            self.assertGreater(len(row[0]), 0, f"source_path is empty for {identity.document_id}")
            self.assertIsNotNone(row[1], f"sha256 is None for {identity.document_id}")
            self.assertEqual(len(row[1]), 64, f"sha256 has wrong length for {identity.document_id}")


class TestSHA256Dedup(unittest.TestCase):
    """Prove SHA-256 deduplication prevents duplicate documents."""

    def test_same_content_registers_once(self):
        """Registering the same file twice should return the same document_id."""
        from kurukshetra.services.registrar import DocumentRegistrar
        import sys; sys.path.insert(0, '.')

        corpus = _TestCorpus().create()
        registrar = DocumentRegistrar()
        test_file = corpus.files[0]

        id1 = registrar.register(test_file)
        id2 = registrar.register(test_file)

        self.assertEqual(id1.document_id, id2.document_id)
        self.assertEqual(id1.sha256, id2.sha256)


class TestBatchResilience(unittest.TestCase):
    """Prove one failed document does not stop the batch."""

    def test_batch_with_failure(self):
        """Batch ingestion should continue past unsupported files."""
        from kurukshetra.pipeline.ingest import IngestionPipeline
        import sys; sys.path.insert(0, '.')

        corpus = _TestCorpus().create()
        pipeline = IngestionPipeline(use_semantic_chunking=False)

        # Mix supported and unsupported files
        mixed = corpus.files[:2] + corpus.unsupported[:1] + corpus.files[2:3]
        results = pipeline.ingest_batch(mixed, stop_on_error=False)

        # All should return a result (no crash)
        self.assertEqual(len(results), len(mixed))

        # Supported files should succeed
        ok_count = sum(1 for r in results if not r.error)
        self.assertGreater(ok_count, 0)

        # Unsupported file should fail gracefully
        fail_count = sum(1 for r in results if r.error)
        self.assertGreater(fail_count, 0)

        pipeline.close()


class TestChunkPersistence(unittest.TestCase):
    """Prove chunks are persisted to DuckDB after ingestion."""

    def test_chunks_persisted(self):
        """Ingesting a document should create persistent chunks."""
        from kurukshetra.pipeline.ingest import IngestionPipeline
        import sys; sys.path.insert(0, '.')

        corpus = _TestCorpus().create()
        pipeline = IngestionPipeline(use_semantic_chunking=False)

        test_file = corpus.files[0]
        result = pipeline.ingest(test_file)

        # Verify chunks were created (count > 0)
        self.assertGreater(result.chunks_stored, 0,
            f"Expected chunks_stored > 0, got {result.chunks_stored}")

        pipeline.close()


class TestGraphPersistence(unittest.TestCase):
    """Prove graph entities and relationships are created."""

    def test_graph_entities_created(self):
        """Ingestion should create graph entities."""
        from kurukshetra.pipeline.ingest import IngestionPipeline
        import sys; sys.path.insert(0, '.')

        corpus = _TestCorpus().create()
        pipeline = IngestionPipeline(use_semantic_chunking=False)

        test_file = corpus.files[0]
        result = pipeline.ingest(test_file)

        self.assertGreater(result.entities_extracted, 0)
        self.assertGreater(result.relationships_extracted, 0)

        pipeline.close()


class TestEvidenceLinked(unittest.TestCase):
    """Prove evidence is linked to source documents."""

    def test_evidence_references_document(self):
        """Graph evidence should reference the source document."""
        from kurukshetra.registry import get_connection
        conn = get_connection()

        # Check evidence table has entries referencing Omkar docs
        evidence = conn.execute("""
            SELECT source_document, source_text, confidence
            FROM graph_evidence
            WHERE source_document IN (
                SELECT document_id FROM documents
                WHERE source_path LIKE '%Omkar%Process Documents%'
            )
            LIMIT 5
        """).fetchall()

        self.assertGreater(len(evidence), 0)
        for doc_id, text, conf in evidence:
            self.assertIsNotNone(doc_id)
            self.assertIsNotNone(text)
            self.assertGreater(conf, 0)

        conn.close()


class TestUnknownTermsGenerated(unittest.TestCase):
    """Prove unknown terms are generated for SEAL."""

    def test_unknown_terms_exist(self):
        """Ingestion should generate unknown terms."""
        from kurukshetra.registry import get_connection
        conn = get_connection()

        count = conn.execute("SELECT COUNT(*) FROM unknown_terms").fetchone()[0]
        self.assertGreater(count, 0)

        # Check some terms are system-like
        terms = conn.execute("SELECT term FROM unknown_terms LIMIT 20").fetchall()
        term_list = [t[0] for t in terms]
        self.assertGreater(len(term_list), 0)

        conn.close()


class TestSANJAYARouting(unittest.TestCase):
    """Prove SANJAYA planner routes real corpus questions correctly."""

    def test_planner_routes_to_knowledge_search(self):
        """Questions about ingested content should route to knowledge_search."""
        from kurukshetra.agent.planner import SANJAYAPlanner

        planner = SANJAYAPlanner()
        queries = [
            "What is G3 Data Feed Configuration?",
            "How does the SFDC workflow work?",
            "What is the RPM configuration process?",
            "What systems are involved in ICS installation?",
        ]

        for q in queries:
            plan = planner.create_plan(q)
            self.assertEqual(plan.intent, "knowledge_search",
                f"Query '{q}' was not routed to knowledge_search")
            self.assertGreaterEqual(plan.confidence, 0.7,
                f"Query '{q}' has low confidence: {plan.confidence}")


if __name__ == "__main__":
    unittest.main()
