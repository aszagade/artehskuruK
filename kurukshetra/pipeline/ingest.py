from __future__ import annotations

from pathlib import Path
from typing import Optional

from kurukshetra.preprocessing import KnowledgeCleaner
from kurukshetra.chunking.splitter import DeterministicSplitter
from kurukshetra.chunking.semantic import SemanticSplitter
from kurukshetra.extractors import PDFExtractor
from kurukshetra.services import DocumentRegistrar
from kurukshetra.services.metadata import MetadataEnricher
from kurukshetra.services.content_enricher import ContentEnricher
from kurukshetra.services.freshness import analyze_freshness, FreshnessTracker
from kurukshetra.services.glossary import GlossaryManager
from kurukshetra.services.team_classifier import TeamClassifier
from kurukshetra.graph.registry import GraphRegistry


class IngestionPipeline:
    """
    Full knowledge ingestion pipeline.

    Extract → Clean → Register → Classify Team → Classify Content →
    Chunk → Store → Detect Terms → Analyze Freshness → Build Graph
    """

    def __init__(self, use_semantic_chunking: bool = True) -> None:
        self.registrar = DocumentRegistrar()
        self.metadata = MetadataEnricher()
        self.extractor = PDFExtractor()
        self.cleaner = KnowledgeCleaner()
        self.content_enricher = ContentEnricher()
        self.team_classifier = TeamClassifier()
        self.glossary = GlossaryManager()
        self.freshness_tracker = FreshnessTracker()
        self.graph_registry = GraphRegistry()

        if use_semantic_chunking:
            self.splitter = SemanticSplitter(max_chunk_size=1000, overlap=150)
        else:
            self.splitter = DeterministicSplitter(chunk_size=1000, overlap=150)

    def ingest(self, file_path: Path):
        """
        Full ingestion pipeline for a single document.

        Returns dict with:
            - document: DocumentIdentity
            - metadata: FileMetadata
            - content_metadata: ContentMetadata (team, product, type)
            - team_classification: ClassificationResult
            - chunks: list of Chunks
            - unknown_terms: list of UnknownTerm
            - freshness: FreshnessResult
            - graph_extraction: ExtractionResult (entities + relationships)
        """
        # 1. Extract text
        raw_text = self.extractor.extract(file_path)
        text = self.cleaner.clean(raw_text)

        # 2. Register document
        document = self.registrar.register(file_path)
        metadata = self.metadata.extract(file_path)

        # 3. Classify team ownership
        team_result = self.team_classifier.classify_document(
            text=text,
            filename=file_path.name,
            document_id=document.document_id,
        )

        # 4. Classify content (product, type, etc.)
        content_meta = self.content_enricher.enrich(text, file_path.name)

        # 5. Chunk the document
        chunks = self.splitter.split(document.document_id, text)

        # 6. Detect unknown terms
        unknown_terms = self.glossary.detect_unknown_terms(
            text, document.document_id
        )

        # 7. Analyze freshness
        freshness = analyze_freshness(
            document_id=document.document_id,
            text=text,
            filename=file_path.name,
            tracker=self.freshness_tracker,
        )

        # 8. Build Knowledge Graph — extract entities & relationships
        graph_result = self.graph_registry.ingest_document(
            text=text,
            document_id=document.document_id,
            document_title=document.title or file_path.stem,
            team_id=team_result.primary_team_id if team_result else None,
            product_scope=content_meta.product_scope if content_meta else [],
        )

        return {
            "document": document,
            "metadata": metadata,
            "content_metadata": content_meta,
            "team_classification": team_result,
            "chunks": chunks,
            "unknown_terms": unknown_terms,
            "freshness": freshness,
            "graph_extraction": graph_result,
        }

    def ingest_batch(
        self, file_paths: list[Path], stop_on_error: bool = False
    ) -> list[dict]:
        """
        Ingest multiple documents.

        Args:
            file_paths: list of file paths to ingest
            stop_on_error: if True, stop on first error

        Returns:
            List of ingestion results (or None for failures)
        """
        results = []

        for path in file_paths:
            try:
                result = self.ingest(path)
                results.append(result)
            except Exception as e:
                if stop_on_error:
                    raise
                results.append({"error": str(e), "file": str(path)})

        return results

    def get_graph_stats(self) -> dict:
        """Get Knowledge Graph statistics."""
        return self.graph_registry.get_stats()

    def close(self) -> None:
        """Clean up resources."""
        self.graph_registry.close()
