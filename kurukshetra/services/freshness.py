"""
Document Freshness & Staleness Tracking
========================================

Tracks:
- Document age from content/filename timestamps
- Last verification date
- Staleness scoring based on age + reference frequency
- Version tracking from document content
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional


class FreshnessLevel(Enum):
    """Freshness classification."""
    CURRENT = "current"         # Recently created/updated
    RECENT = "recent"           # Within acceptable age
    AGING = "aging"             # Getting old, may need review
    STALE = "stale"             # Likely outdated
    UNKNOWN = "unknown"         # Cannot determine age


@dataclass(slots=True)
class FreshnessResult:
    """Result of freshness analysis for a document."""
    document_id: str
    freshness_level: FreshnessLevel
    staleness_score: float  # 0.0 = fresh, 1.0 = very stale
    detected_version: Optional[str]
    detected_date: Optional[datetime]
    days_since_modified: Optional[int]
    reference_count: int  # How often this doc is referenced
    verification_count: int  # How often this doc's answers were verified correct
    confidence: float


@dataclass
class FreshnessTracker:
    """
    Tracks freshness metadata for all documents in the knowledge base.
    Persists state in-memory; designed to be backed by DuckDB.
    """
    # document_id -> last_verified_at
    verification_dates: dict[str, datetime] = field(default_factory=dict)
    # document_id -> number of times referenced in queries
    reference_counts: dict[str, int] = field(default_factory=dict)
    # document_id -> number of times answers were verified correct
    verification_counts: dict[str, int] = field(default_factory=dict)

    def record_reference(self, document_id: str) -> None:
        """Record that a document was referenced in a query."""
        self.reference_counts[document_id] = (
            self.reference_counts.get(document_id, 0) + 1
        )

    def record_verification(self, document_id: str, correct: bool) -> None:
        """Record a verification result for a document's answer."""
        self.verification_dates[document_id] = datetime.utcnow()
        if correct:
            self.verification_counts[document_id] = (
                self.verification_counts.get(document_id, 0) + 1
            )

    def get_reference_count(self, document_id: str) -> int:
        return self.reference_counts.get(document_id, 0)

    def get_verification_count(self, document_id: str) -> int:
        return self.verification_counts.get(document_id, 0)


# -----------------------------------------------------------------------
# Date / version extraction patterns
# -----------------------------------------------------------------------

# Filename patterns: "Title - 20250822_102942.pdf"
FILENAME_DATE_PATTERN = re.compile(
    r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"
)

# Content version patterns: "v1.2.3", "Version 2.0", "Rev 3"
VERSION_PATTERNS = [
    re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", re.IGNORECASE),
    re.compile(r"version\s+(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"rev(?:ision)?\s+(\d+(?:\.\d+)?)", re.IGNORECASE),
]

# Content date patterns: "January 15, 2025" or "2025-01-15" or "01/15/2025"
CONTENT_DATE_PATTERNS = [
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),  # ISO
    re.compile(r"(\d{2})/(\d{2})/(\d{4})"),  # US format
    re.compile(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    ),
]

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def extract_date_from_filename(filename: str) -> Optional[datetime]:
    """Extract datetime from filename patterns like 'Title - 20250822_102942.pdf'."""
    match = FILENAME_DATE_PATTERN.search(filename)
    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
                int(match.group(5)),
                int(match.group(6)),
            )
        except ValueError:
            return None
    return None


def extract_version_from_text(text: str) -> Optional[str]:
    """Extract version number from document text."""
    for pattern in VERSION_PATTERNS:
        match = pattern.search(text[:5000])  # Search first 5000 chars
        if match:
            return match.group(1)
    return None


def extract_date_from_text(text: str) -> Optional[datetime]:
    """Extract date from document content text."""
    # Try ISO format first
    match = CONTENT_DATE_PATTERNS[0].search(text[:5000])
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # Try US format
    match = CONTENT_DATE_PATTERNS[1].search(text[:5000])
    if match:
        try:
            return datetime(int(match.group(3)), int(match.group(1)), int(match.group(2)))
        except ValueError:
            pass

    # Try written month format
    match = CONTENT_DATE_PATTERNS[2].search(text[:5000])
    if match:
        month = MONTH_MAP.get(match.group(1).lower())
        if month:
            try:
                return datetime(int(match.group(3)), month, int(match.group(2)))
            except ValueError:
                pass

    return None


def calculate_staleness(
    days_since_modified: Optional[int],
    reference_count: int,
    verification_count: int,
) -> tuple[FreshnessLevel, float]:
    """
    Calculate staleness score and freshness level.

    Scoring:
    - Base staleness increases with age
    - Frequent references reduce staleness (actively used = probably current)
    - Successful verifications reduce staleness (confirmed accurate)
    """
    if days_since_modified is None:
        return FreshnessLevel.UNKNOWN, 0.5

    # Base staleness from age (0-1 scale)
    # 0 days = 0.0, 365 days = ~0.7, 730+ days = ~1.0
    age_staleness = min(days_since_modified / 730.0, 1.0)

    # Reference bonus: docs used more often are less likely stale
    reference_bonus = min(reference_count * 0.02, 0.3)

    # Verification bonus: confirmed accurate docs are less stale
    verification_bonus = min(verification_count * 0.05, 0.3)

    # Final staleness score
    staleness = max(0.0, min(1.0,
        age_staleness - reference_bonus - verification_bonus
    ))

    # Classify
    if staleness < 0.2:
        level = FreshnessLevel.CURRENT
    elif staleness < 0.4:
        level = FreshnessLevel.RECENT
    elif staleness < 0.7:
        level = FreshnessLevel.AGING
    else:
        level = FreshnessLevel.STALE

    return level, round(staleness, 3)


def analyze_freshness(
    document_id: str,
    text: str,
    filename: str,
    tracker: FreshnessTracker,
) -> FreshnessResult:
    """
    Perform comprehensive freshness analysis for a document.

    Args:
        document_id: Unique document identifier
        text: Full document text
        filename: Original filename
        tracker: FreshnessTracker for reference/verification history

    Returns:
        FreshnessResult with staleness assessment
    """
    now = datetime.utcnow()

    # Try to extract date from filename first (most reliable)
    detected_date = extract_date_from_filename(filename)

    # Fall back to content date
    if detected_date is None:
        detected_date = extract_date_from_text(text)

    # Extract version
    detected_version = extract_version_from_text(text)

    # Calculate days since modified
    days_since = None
    if detected_date:
        days_since = (now - detected_date).days

    # Get reference and verification counts
    ref_count = tracker.get_reference_count(document_id)
    verif_count = tracker.get_verification_count(document_id)

    # Calculate staleness
    level, staleness = calculate_staleness(days_since, ref_count, verif_count)

    # Confidence in the freshness assessment
    confidence = 0.5  # base
    if detected_date:
        confidence += 0.3
    if detected_version:
        confidence += 0.1
    if ref_count > 0:
        confidence += 0.1

    return FreshnessResult(
        document_id=document_id,
        freshness_level=level,
        staleness_score=staleness,
        detected_version=detected_version,
        detected_date=detected_date,
        days_since_modified=days_since,
        reference_count=ref_count,
        verification_count=verif_count,
        confidence=min(confidence, 1.0),
    )
