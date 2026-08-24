"""
Ingestion Status Tracker
========================

Tracks the lifecycle of documents through the ingestion pipeline.
Provides a simple in-memory status store for the demo runtime.

Status transitions:
  DETECTED -> EXTRACTING -> REGISTERED -> CLASSIFIED -> CHUNKED
  -> GRAPH_UPDATED -> RAG_READY -> COMPLETE

Or on failure:
  DETECTED -> FAILED
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IngestStatus(str, Enum):
    DETECTED = "detected"
    EXTRACTING = "extracting"
    REGISTERED = "registered"
    CLASSIFIED = "classified"
    CHUNKED = "chunked"
    GRAPH_UPDATED = "graph_updated"
    RAG_READY = "rag_ready"
    UNKNOWN_TERMS = "unknown_terms"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class DocumentActivity:
    """Status record for a single document ingestion."""
    filename: str
    status: IngestStatus = IngestStatus.DETECTED
    document_id: str = ""
    team_id: str = "unknown"
    chunks_created: int = 0
    entities_discovered: int = 0
    relationships_discovered: int = 0
    unknown_terms: int = 0
    error: Optional[str] = None
    detected_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    stages: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "status": self.status.value,
            "document_id": self.document_id,
            "team_id": self.team_id,
            "chunks_created": self.chunks_created,
            "entities_discovered": self.entities_discovered,
            "relationships_discovered": self.relationships_discovered,
            "unknown_terms": self.unknown_terms,
            "error": self.error,
            "detected_at": self.detected_at,
            "completed_at": self.completed_at,
            "stages": self.stages,
        }


class StatusTracker:
    """In-memory status tracker for ingestion activity."""

    def __init__(self) -> None:
        self._activities: dict[str, DocumentActivity] = {}
        self._history: list[DocumentActivity] = []

    def detect(self, filename: str) -> DocumentActivity:
        """Record a new document detection."""
        activity = DocumentActivity(filename=filename)
        self._activities[filename] = activity
        return activity

    def update(self, filename: str, status: IngestStatus, **kwargs) -> None:
        """Update status for a document."""
        if filename in self._activities:
            activity = self._activities[filename]
            activity.status = status
            for k, v in kwargs.items():
                if hasattr(activity, k):
                    setattr(activity, k, v)
            if status == IngestStatus.COMPLETE:
                activity.completed_at = time.time()
                self._history.append(activity)
                del self._activities[filename]
            elif status == IngestStatus.FAILED:
                activity.completed_at = time.time()
                self._history.append(activity)
                del self._activities[filename]

    def get_activity(self, filename: str) -> Optional[DocumentActivity]:
        """Get current activity for a document."""
        return self._activities.get(filename)

    def get_pending(self) -> list[DocumentActivity]:
        """Get all documents currently being processed."""
        return list(self._activities.values())

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Get recent completed/failed activities."""
        return [a.to_dict() for a in self._history[-limit:]]

    def get_stats(self) -> dict:
        """Get summary statistics."""
        return {
            "pending": len(self._activities),
            "completed": sum(1 for a in self._history if a.status == IngestStatus.COMPLETE),
            "failed": sum(1 for a in self._history if a.status == IngestStatus.FAILED),
            "total_documents": sum(
                1 for a in self._history if a.status == IngestStatus.COMPLETE
            ),
        }


# Global singleton
_tracker = StatusTracker()


def get_tracker() -> StatusTracker:
    return _tracker
