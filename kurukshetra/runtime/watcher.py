"""
Knowledge Inbox Watcher
=======================

Watches knowledge/inbox/ for new documents.
Ingests them through the canonical pipeline.
Moves processed files to knowledge/processed/.
Moves failed files to knowledge/failed/.

Reuses existing TextExtractor and IngestionPipeline.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from kurukshetra.extractors.text_extractor import TextExtractor
from kurukshetra.pipeline.ingest import IngestionPipeline, IngestionResult
from kurukshetra.runtime.status import StatusTracker, IngestStatus, get_tracker


class InboxWatcher:
    """Watches the knowledge inbox and ingests new documents."""

    def __init__(
        self,
        inbox_dir: str = "knowledge/inbox",
        processed_dir: str = "knowledge/processed",
        failed_dir: str = "knowledge/failed",
    ) -> None:
        self.inbox = Path(inbox_dir)
        self.processed = Path(processed_dir)
        self.failed = Path(failed_dir)
        self.supported = TextExtractor.supported_extensions()
        self.tracker = get_tracker()
        self._pipeline: IngestionPipeline | None = None

    @property
    def pipeline(self) -> IngestionPipeline:
        if self._pipeline is None:
            self._pipeline = IngestionPipeline(use_semantic_chunking=False)
        return self._pipeline

    def scan(self) -> list[Path]:
        """Scan inbox for supported files not currently being processed."""
        if not self.inbox.exists():
            return []
        pending = {a.filename for a in self.tracker.get_pending()}
        return sorted(
            f for f in self.inbox.iterdir()
            if f.is_file()
            and f.suffix.lower() in self.supported
            and f.name not in pending
        )

    def ingest_one(self, file_path: Path) -> IngestionResult:
        """Ingest a single file through the KnowledgeFabric.

        Routes through KnowledgeFabric for version tracking,
        concept-team association, and provenance preservation.
        Falls back to direct pipeline if Fabric is unavailable.
        """
        filename = file_path.name
        self.tracker.detect(filename)
        self.tracker.update(filename, IngestStatus.EXTRACTING)

        # Try routing through KnowledgeFabric first
        try:
            from kurukshetra.knowledge.fabric import KnowledgeFabric
            fabric = KnowledgeFabric()
            try:
                fabric_result = fabric.ingest_file(file_path)
            finally:
                fabric.close()

            # Map Fabric result to IngestionResult for compatibility
            team_id = fabric_result.teams_detected[0] if fabric_result.teams_detected else "unknown"
            result = IngestionResult(
                document_id=fabric_result.document_id,
                title=fabric_result.title or filename,
                error=fabric_result.error,
            )
            result.chunks_stored = fabric_result.chunks_stored
            result.entities_extracted = fabric_result.entities_extracted
            result.relationships_extracted = fabric_result.relationships_extracted
            result.unknown_terms = fabric_result.unknown_terms
            result.team_id = team_id
            result.stages = fabric_result.stages
        except Exception:
            # Fallback: direct pipeline ingestion
            try:
                result = self.pipeline.ingest(file_path)
            except Exception as e:
                self.tracker.update(
                    filename, IngestStatus.FAILED, error=str(e)
                )
                self._move(file_path, self.failed)
                return IngestionResult(
                    document_id="", title=filename, error=str(e)
                )

        # Update tracker with results
        if result.error:
            self.tracker.update(
                filename, IngestStatus.FAILED, error=result.error
            )
            self._move(file_path, self.failed)
        else:
            self.tracker.update(
                filename, IngestStatus.REGISTERED,
                document_id=result.document_id,
            )
            self.tracker.update(
                filename, IngestStatus.CLASSIFIED,
                team_id=result.team_id,
            )
            self.tracker.update(
                filename, IngestStatus.CHUNKED,
                chunks_created=result.chunks_stored,
            )
            self.tracker.update(
                filename, IngestStatus.GRAPH_UPDATED,
                entities_discovered=result.entities_extracted,
                relationships_discovered=result.relationships_extracted,
            )
            self.tracker.update(
                filename, IngestStatus.RAG_READY,
            )
            if result.unknown_terms > 0:
                self.tracker.update(
                    filename, IngestStatus.UNKNOWN_TERMS,
                    unknown_terms=result.unknown_terms,
                )
            self.tracker.update(
                filename, IngestStatus.COMPLETE,
            )
            self._move(file_path, self.processed)

        return result

    def ingest_all(self) -> list[IngestionResult]:
        """Ingest all pending files in the inbox."""
        files = self.scan()
        results = []
        for f in files:
            results.append(self.ingest_one(f))
        return results

    def _move(self, src: Path, dest_dir: Path) -> None:
        """Move a file to the destination directory."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            dest = dest_dir / f"{src.stem}_{int(time.time())}{src.suffix}"
        shutil.move(str(src), str(dest))

    def close(self) -> None:
        if self._pipeline:
            self._pipeline.close()
            self._pipeline = None
