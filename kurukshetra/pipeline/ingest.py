from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kurukshetra.preprocessing import KnowledgeCleaner
from kurukshetra.chunking.splitter import DeterministicSplitter
from kurukshetra.chunking.semantic import SemanticSplitter
from kurukshetra.extractors.text_extractor import TextExtractor
from kurukshetra.services import DocumentRegistrar
from kurukshetra.services.metadata import MetadataEnricher
from kurukshetra.services.content_enricher import ContentEnricher
from kurukshetra.services.freshness import analyze_freshness, FreshnessTracker
from kurukshetra.services.glossary import GlossaryManager
from kurukshetra.services.team_classifier import TeamClassifier
from kurukshetra.graph.registry import GraphRegistry
from kurukshetra.registry.chunks import ChunkRepository


@dataclass
class IngestionResult:
    """Structured result from the ingestion pipeline."""
    document_id: str
    title: str
    stages: dict[str, str] = field(default_factory=dict)  # stage -> "ok"|"skipped"|"error:..."
    chunks_stored: int = 0
    embeddings_built: int = 0
    entities_extracted: int = 0
    relationships_extracted: int = 0
    unknown_terms: int = 0
    team_id: str = "unknown"
    error: Optional[str] = None


class IngestionPipeline:
    """
    Canonical knowledge ingestion pipeline.

    Extract -> Clean -> Register -> Classify Team -> Classify Content ->
    Chunk -> Persist Chunks -> (Embed) -> Detect Terms -> Build Graph

    Works for any document type the TextExtractor supports.
    """

    def __init__(
        self,
        use_semantic_chunking: bool = True,
        build_embeddings: bool = False,
    ) -> None:
        self.registrar = DocumentRegistrar()
        self.metadata = MetadataEnricher()
        self.extractor = TextExtractor()
        self.cleaner = KnowledgeCleaner()
        self.content_enricher = ContentEnricher()
        self.team_classifier = TeamClassifier()
        self.glossary = GlossaryManager()
        self.freshness_tracker = FreshnessTracker()
        import kurukshetra.registry.database as _db
        self.graph_registry = GraphRegistry(db_path=str(_db.DATABASE_PATH))
        self.chunk_repo = ChunkRepository()
        self.build_embeddings = build_embeddings

        if use_semantic_chunking:
            self.splitter = SemanticSplitter(max_chunk_size=1000, overlap=150)
        else:
            self.splitter = DeterministicSplitter(chunk_size=1000, overlap=150)

    def ingest(self, file_path: Path) -> IngestionResult:
        """
        Full ingestion pipeline for a single document.

        Returns IngestionResult showing which stages succeeded.
        """
        result = IngestionResult(document_id="", title=file_path.stem)
        stages = result.stages

        # 1. Extract text
        try:
            raw_text = self.extractor.extract(file_path)
            if raw_text is None:
                stages["extract"] = f"unsupported:{file_path.suffix}"
                result.error = f"Unsupported file type: {file_path.suffix}"
                return result
            text = self.cleaner.clean(raw_text)
            stages["extract"] = "ok"
        except Exception as e:
            stages["extract"] = f"error:{e}"
            result.error = str(e)
            return result

        # 2. Register document
        try:
            document = self.registrar.register(file_path)
            metadata = self.metadata.extract(file_path)
            result.document_id = document.document_id
            result.title = getattr(document, 'title', None) or document.file_name or file_path.stem
            stages["register"] = "ok"
        except Exception as e:
            stages["register"] = f"error:{e}"
            result.error = str(e)
            return result

        # 3. Classify team ownership
        try:
            team_result = self.team_classifier.classify_document(
                text=text,
                filename=file_path.name,
                document_id=document.document_id,
            )
            result.team_id = team_result.primary_team_id if team_result else "unknown"
            stages["classify_team"] = "ok"
        except Exception as e:
            stages["classify_team"] = f"error:{e}"
            team_result = None

        # 4. Classify content (product, type, etc.)
        try:
            content_meta = self.content_enricher.enrich(text, file_path.name)
            stages["classify_content"] = "ok"
        except Exception as e:
            stages["classify_content"] = f"error:{e}"
            content_meta = None

        # 5. Chunk the document
        try:
            chunks = self.splitter.split(document.document_id, text)
            stages["chunk"] = f"ok:{len(chunks)}"
        except Exception as e:
            stages["chunk"] = f"error:{e}"
            chunks = []

        # 6. Persist chunks to DuckDB
        if chunks:
            try:
                self.chunk_repo.insert(chunks)
                result.chunks_stored = len(chunks)
                stages["persist_chunks"] = "ok"
            except Exception as e:
                stages["persist_chunks"] = f"error:{e}"

        # 7. Generate embeddings (optional, expensive)
        if self.build_embeddings and chunks:
            try:
                from kurukshetra.pipeline.vector_indexer import VectorIndexer
                indexer = VectorIndexer()
                # Only embed new chunks
                result.embeddings_built = indexer.build()
                stages["embeddings"] = "ok"
            except Exception as e:
                stages["embeddings"] = f"error:{e}"

        # 8. Detect unknown terms
        try:
            unknown_terms = self.glossary.detect_unknown_terms(
                text, document.document_id
            )
            result.unknown_terms = len(unknown_terms)
            stages["detect_terms"] = f"ok:{len(unknown_terms)}"
        except Exception as e:
            stages["detect_terms"] = f"error:{e}"

        # 9. Analyze freshness
        try:
            freshness = analyze_freshness(
                document_id=document.document_id,
                text=text,
                filename=file_path.name,
                tracker=self.freshness_tracker,
            )
            stages["freshness"] = "ok"
        except Exception as e:
            stages["freshness"] = f"error:{e}"

        # 10. Build Knowledge Graph
        try:
            graph_result = self.graph_registry.ingest_document(
                text=text,
                document_id=document.document_id,
                document_title=result.title,
                team_id=result.team_id if result.team_id != "unknown" else None,
                product_scope=[content_meta.product.value] if content_meta and content_meta.product else [],
            )
            result.entities_extracted = len(graph_result.entities)
            result.relationships_extracted = len(graph_result.relationships)
            stages["graph"] = f"ok:{len(graph_result.entities)}e,{len(graph_result.relationships)}r"
        except Exception as e:
            stages["graph"] = f"error:{e}"

        return result

    def ingest_batch(
        self, file_paths: list[Path], stop_on_error: bool = False
    ) -> list[IngestionResult]:
        """Ingest multiple documents."""
        results = []
        for path in file_paths:
            try:
                results.append(self.ingest(path))
            except Exception as e:
                if stop_on_error:
                    raise
                results.append(IngestionResult(
                    document_id="", title=path.stem, error=str(e)
                ))
        return results

    def get_graph_stats(self) -> dict:
        return self.graph_registry.get_stats()

    def close(self) -> None:
        self.graph_registry.close()
