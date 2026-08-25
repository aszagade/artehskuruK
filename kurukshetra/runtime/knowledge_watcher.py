"""
Knowledge Watcher — Continuous Runtime Refresh
================================================

Integrates KnowledgeFabric with the existing InboxWatcher to provide:

1. Automatic detection of new/changed/removed files
2. Incremental ingestion through KnowledgeFabric
3. BM25/vector cache refresh after ingestion
4. Multi-team concept tracking
5. Version history tracking
6. Provenance preservation

Design principles:
- Reuses existing InboxWatcher for file movement
- Reuses existing IngestionPipeline for document processing
- Uses KnowledgeFabric for change detection and state management
- Invalidates BM25/Vector caches after changes
- Tracks multi-team concepts automatically
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kurukshetra.knowledge.fabric import (
    ChangeDetection,
    ChangeType,
    FabricIngestResult,
    FabricScanResult,
    KnowledgeFabric,
)
from kurukshetra.retrieval.database_bm25 import DatabaseBM25Retriever
from kurukshetra.runtime.status import StatusTracker, IngestStatus, get_tracker


@dataclass
class WatcherResult:
    """Result of a watcher cycle."""
    scan_result: FabricScanResult
    ingest_results: list[FabricIngestResult]
    cache_refreshed: bool
    total_time_ms: float
    new_documents: int = 0
    changed_documents: int = 0
    removed_documents: int = 0
    errors: list[str] = field(default_factory=list)


class KnowledgeWatcher:
    """
    Continuous runtime watcher that detects and ingests document changes.

    Integrates KnowledgeFabric for change detection with the existing
    InboxWatcher for file management.
    """

    def __init__(
        self,
        source_dirs: list[str] | None = None,
        inbox_dir: str = "knowledge/inbox",
        processed_dir: str = "knowledge/processed",
        failed_dir: str = "knowledge/failed",
    ) -> None:
        self.source_dirs = source_dirs or ["knowledge/inbox"]
        self.fabric = KnowledgeFabric()
        self.tracker = get_tracker()
        self._pipeline = None
        self._bm25_invalidated = False

        # Import InboxWatcher for file movement
        from kurukshetra.runtime.watcher import InboxWatcher
        self.inbox_watcher = InboxWatcher(
            inbox_dir=inbox_dir,
            processed_dir=processed_dir,
            failed_dir=failed_dir,
        )

    @property
    def pipeline(self):
        if self._pipeline is None:
            from kurukshetra.pipeline.ingest import IngestionPipeline
            self._pipeline = IngestionPipeline(use_semantic_chunking=False)
        return self._pipeline

    def scan_and_ingest(self) -> WatcherResult:
        """
        Full cycle: scan all sources, detect changes, ingest, refresh caches.

        Returns WatcherResult with detailed outcome.
        """
        start = time.time()
        all_changes = []
        all_ingest_results = []
        errors = []

        # Scan each source directory
        for source_dir in self.source_dirs:
            try:
                scan = self.fabric.scan_source(source_dir)
                all_changes.extend(scan.changes)
            except Exception as e:
                errors.append(f"Scan error ({source_dir}): {e}")

        # Ingest each change
        for change in all_changes:
            try:
                if change.change_type == ChangeType.NEW_FILE:
                    result = self._ingest_new(change)
                elif change.change_type == ChangeType.CONTENT_CHANGED:
                    result = self._ingest_changed(change)
                elif change.change_type == ChangeType.REMOVED:
                    result = self._handle_removed(change)
                else:
                    continue

                all_ingest_results.append(result)

                if result.error:
                    errors.append(f"Ingest error ({change.source_path}): {result.error}")

            except Exception as e:
                errors.append(f"Change error ({change.source_path}): {e}")

        # Refresh caches if anything changed
        cache_refreshed = False
        if any(r.change_type != ChangeType.NONE for r in all_ingest_results):
            self._refresh_caches()
            cache_refreshed = True

        total_time = (time.time() - start) * 1000

        return WatcherResult(
            scan_result=FabricScanResult(
                source_path=", ".join(self.source_dirs),
                scan_time=total_time / 1000,
                files_found=sum(
                    self.fabric.scan_source(d).files_found
                    for d in self.source_dirs
                    if Path(d).exists()
                ),
                new_files=sum(1 for r in all_ingest_results if r.change_type == ChangeType.NEW_FILE),
                changed_files=sum(1 for r in all_ingest_results if r.change_type == ChangeType.CONTENT_CHANGED),
                unchanged_files=0,
                removed_files=sum(1 for r in all_ingest_results if r.change_type == ChangeType.REMOVED),
                errors=errors,
                changes=all_changes,
            ),
            ingest_results=all_ingest_results,
            cache_refreshed=cache_refreshed,
            total_time_ms=round(total_time, 1),
            new_documents=sum(1 for r in all_ingest_results if r.change_type == ChangeType.NEW_FILE),
            changed_documents=sum(1 for r in all_ingest_results if r.change_type == ChangeType.CONTENT_CHANGED),
            removed_documents=sum(1 for r in all_ingest_results if r.change_type == ChangeType.REMOVED),
            errors=errors,
        )

    def _ingest_new(self, change: ChangeDetection) -> FabricIngestResult:
        """Ingest a new file through the canonical pipeline."""
        filename = Path(change.source_path).name
        self.tracker.detect(filename)
        self.tracker.update(filename, IngestStatus.EXTRACTING)

        result = self.fabric.ingest_change(change, pipeline=self.pipeline)

        if result.error:
            self.tracker.update(filename, IngestStatus.FAILED, error=result.error)
        else:
            self.tracker.update(filename, IngestStatus.REGISTERED, document_id=result.document_id)
            self.tracker.update(filename, IngestStatus.CLASSIFIED, team_id=result.teams_detected[0] if result.teams_detected else "unknown")
            self.tracker.update(filename, IngestStatus.CHUNKED, chunks_created=result.chunks_stored)
            self.tracker.update(filename, IngestStatus.GRAPH_UPDATED,
                              entities_discovered=result.entities_extracted,
                              relationships_discovered=result.relationships_extracted)
            self.tracker.update(filename, IngestStatus.RAG_READY)
            if result.unknown_terms > 0:
                self.tracker.update(filename, IngestStatus.UNKNOWN_TERMS, unknown_terms=result.unknown_terms)
            self.tracker.update(filename, IngestStatus.COMPLETE)

        return result

    def _ingest_changed(self, change: ChangeDetection) -> FabricIngestResult:
        """Re-ingest a changed file."""
        filename = Path(change.source_path).name
        self.tracker.detect(filename)
        self.tracker.update(filename, IngestStatus.EXTRACTING)

        result = self.fabric.ingest_change(change, pipeline=self.pipeline)

        if result.error:
            self.tracker.update(filename, IngestStatus.FAILED, error=result.error)
        else:
            self.tracker.update(filename, IngestStatus.COMPLETE)

        return result

    def _handle_removed(self, change: ChangeDetection) -> FabricIngestResult:
        """Handle a removed file."""
        result = self.fabric.ingest_change(change)
        return result

    def _refresh_caches(self) -> None:
        """Refresh BM25 and Vector retrieval caches."""
        try:
            # BM25 auto-refreshes on chunk count change
            # But we can force invalidation for immediate effect
            bm25 = DatabaseBM25Retriever()
            bm25.invalidate()
            self._bm25_invalidated = True
        except Exception:
            pass

    def scan_only(self) -> FabricScanResult:
        """Scan without ingesting (for dry-run)."""
        all_changes = []
        for source_dir in self.source_dirs:
            try:
                scan = self.fabric.scan_source(source_dir)
                all_changes.extend(scan.changes)
            except Exception:
                pass

        return FabricScanResult(
            source_path=", ".join(self.source_dirs),
            scan_time=0,
            files_found=0,
            new_files=sum(1 for c in all_changes if c.change_type == ChangeType.NEW_FILE),
            changed_files=sum(1 for c in all_changes if c.change_type == ChangeType.CONTENT_CHANGED),
            unchanged_files=0,
            removed_files=sum(1 for c in all_changes if c.change_type == ChangeType.REMOVED),
            changes=all_changes,
        )

    def get_knowledge_state(self) -> dict:
        """Get current knowledge state."""
        state = self.fabric.get_knowledge_state()
        return {
            "total_documents": state.total_documents,
            "total_chunks": state.total_chunks,
            "total_entities": state.total_entities,
            "total_relationships": state.total_relationships,
            "total_glossary_terms": state.total_glossary_terms,
            "total_unknown_terms": state.total_unknown_terms,
            "total_concepts": state.total_concepts,
            "total_conflicts": state.total_conflicts,
            "teams_represented": state.teams_represented,
            "documents_by_state": state.documents_by_state,
        }

    def close(self) -> None:
        """Clean up resources."""
        if self._pipeline:
            self._pipeline.close()
            self._pipeline = None
        self.fabric.close()
        self.inbox_watcher.close()
