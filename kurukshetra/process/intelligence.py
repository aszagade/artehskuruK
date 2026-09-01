"""
Process Intelligence
====================

Deterministic extraction of processes and process steps from enterprise documents.

Builds on:
- Existing graph entities (process, system, team)
- Document chunks with process language
- Evidence/authority/provenance systems
- Entity quality filtering

Key principle: Co-occurrence ≠ explicit process relationship.
Every extracted step must have explicit textual evidence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from kurukshetra.registry.database import get_connection


# ─── Data Models ────────────────────────────────────────────────────────────


class EvidenceLevel(str, Enum):
    """How strongly the text supports the process claim."""
    EXPLICIT = "explicit"       # Directly stated: "Step 1: Do X"
    INFERRED = "inferred"       # Strongly implied but not verbatim
    CO_OCCURRENCE = "co_occurrence"  # Entities appear near each other
    UNKNOWN = "unknown"


class ProcessQuality(str, Enum):
    """Quality state of a discovered process."""
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    INFERRED = "inferred"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


@dataclass
class ProcessStep:
    """A single step in a process."""
    step_id: str
    process_id: str
    sequence: int
    description: str
    actor_team: Optional[str] = None
    system: Optional[str] = None
    action: Optional[str] = None
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    predecessor_step: Optional[str] = None
    successor_step: Optional[str] = None
    source_document: Optional[str] = None
    evidence_chunk: Optional[str] = None
    evidence_text: Optional[str] = None
    confidence: float = 0.5
    authority: str = "operational"
    evidence_level: str = "inferred"
    validation_status: str = "unknown"


@dataclass
class ProcessDefinition:
    """A discovered process with its steps."""
    process_id: str
    name: str
    description: str = ""
    trigger: Optional[str] = None
    outcome: Optional[str] = None
    source_documents: list[str] = field(default_factory=list)
    steps: list[ProcessStep] = field(default_factory=list)
    quality: str = "unknown"
    confidence: float = 0.5
    team: Optional[str] = None
    system: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class ProcessGap:
    """A structural gap in a process."""
    gap_id: str
    process_id: str
    gap_type: str  # no_owner, no_successor, no_receiver, conflicting, obsolete
    step_id: Optional[str] = None
    description: str = ""
    severity: str = "medium"


# ─── Process Step Extractor ─────────────────────────────────────────────────


# Patterns that indicate explicit process steps
_STEP_PATTERNS = [
    # Numbered steps
    re.compile(r'(?:^|\n)\s*(?:Step\s+(\d+))\s*[:\.–—\s]\s*(.+)', re.IGNORECASE),
    # "1." or "1)" numbered lists
    re.compile(r'(?:^|\n)\s*(\d+)[\.\)]\s+(.+)', re.IGNORECASE),
    # Roman numerals
    re.compile(r'(?:^|\n)\s*(?:I{1,3}|IV|V|VI{0,3}|IX|X)[\.\)]\s+(.+)', re.IGNORECASE),
]

# Patterns that indicate sequence/flow
_SEQUENCE_PATTERNS = [
    re.compile(r'\b(?:first|initially|start by|begin by)\b\s*[:,]?\s*(.+)', re.IGNORECASE),
    re.compile(r'\b(?:then|next|after that|subsequently|following that)\b\s*[:,]?\s*(.+)', re.IGNORECASE),
    re.compile(r'\b(?:finally|lastly|in the end|to complete)\b\s*[:,]?\s*(.+)', re.IGNORECASE),
    re.compile(r'\b(?:once .+? (?:is |are )?(?:done|completed|finished|submitted|approved))\b\s*[:,]?\s*(.+)', re.IGNORECASE),
]

# Patterns that indicate triggers
_TRIGGER_PATTERNS = [
    re.compile(r'\b(?:when|if|once|upon|as soon as)\s+(?:a\s+)?(.+?)\s+(?:is |are )?(?:received|detected|triggered|initiated|created|logged|opened)', re.IGNORECASE),
    re.compile(r'\btriggered by\s+(.+?)(?:\.|$)', re.IGNORECASE),
    re.compile(r'\bin response to\s+(.+?)(?:\.|$)', re.IGNORECASE),
]

# Patterns that indicate actors/teams
_ACTOR_PATTERNS = [
    re.compile(r'\b(?:responsible for|owned by|assigned to|handled by|managed by)\s+(.+?)(?:\.|,|$)', re.IGNORECASE),
    re.compile(r'\b(?:the|this)\s+(.+?)\s+team\s+(?:will|should|must|handles?|manages?)\b', re.IGNORECASE),
    re.compile(r'\b(?:escalat(?:e|es|ed|ion))\s+(?:to|this to)\s+(.+?)(?:\.|,|$)', re.IGNORECASE),
    re.compile(r'\b(?:send|forward|route|transfer)\s+(?:to|this to)\s+(.+?)(?:\.|,|$)', re.IGNORECASE),
]

# Patterns that indicate system actions
_SYSTEM_ACTION_PATTERNS = [
    re.compile(r'\b(?:system|application|tool)\s+(?:will|should|must|automatically)\s+(.+?)(?:\.|$)', re.IGNORECASE),
    re.compile(r'\b(?:in|on|through|via)\s+(?:the\s+)?(.+?)\s+(?:system|application|tool|dashboard|console)\b', re.IGNORECASE),
]

# Patterns that indicate handoffs
_HANDOFF_PATTERNS = [
    re.compile(r'\bhandoff\s+(?:to|from)\s+(.+?)(?:\.|,|$)', re.IGNORECASE),
    re.compile(r'\b(?:transfer|forward|send|route)\s+(?:the\s+)?(?:case|ticket|request|issue)\s+to\s+(.+?)(?:\.|,|$)', re.IGNORECASE),
    re.compile(r'\b(?:receives?|receiv(?:ed|ing))\s+(?:the\s+)?(?:case|ticket|request|issue)\s+(?:from|for)\s+(.+?)(?:\.|,|$)', re.IGNORECASE),
]

# Patterns that indicate outcomes
_OUTCOME_PATTERNS = [
    re.compile(r'\b(?:result|outcome|output|deliverable)\s*(?:is|:)\s+(.+?)(?:\.|$)', re.IGNORECASE),
    re.compile(r'\b(?:this (?:results?|leads?) in)\s+(.+?)(?:\.|$)', re.IGNORECASE),
    re.compile(r'\b(?:completion|successful|completed)\s+(?:results?|means?)\s+(?:in|that)\s+(.+?)(?:\.|$)', re.IGNORECASE),
]

# Known team names for matching
KNOWN_TEAMS = {
    "spm", "ics", "sdops", "roa", "cpm", "hr", "it",
    "SPM", "ICS", "SDOPS", "ROA", "CPM", "HR", "IT",
    "revenue management", "operations", "support", "engineering",
    "monitoring", "noc",
}

# Known system names for matching
KNOWN_SYSTEMS = {
    "g3", "g3-rms", "g3 rms", "g3rms", "ohip", "sfdc", "salesforce",
    "datadog", "synxis", "tars", "ngi", "oxi", "opera", "opera pms",
    "opera cloud", "htng", "fols", "mews", "smartsheet", "sas",
    "cp pricing", "curtis", "ngi agent", "opera agent", "opera cloud agent",
    "ohip emulator", "demand360", "optix", "sqlserver",
}


class ProcessExtractor:
    """Deterministic process step extractor.

    Extracts process steps from document chunks using explicit
    textual evidence patterns. Does NOT infer processes from co-occurrence.
    """

    def __init__(self) -> None:
        self._step_counter = 0

    def extract_processes_from_document(
        self,
        document_id: str,
        document_title: str = "",
        team_id: Optional[str] = None,
    ) -> list[ProcessDefinition]:
        """Extract all processes from a document's chunks.

        Returns a list of ProcessDefinition objects, each with steps
        backed by explicit textual evidence.
        """
        conn = get_connection()
        chunks = conn.execute(
            """
            SELECT chunk_id, text FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_id
            """,
            [document_id],
        ).fetchall()
        conn.close()

        if not chunks:
            return []

        # Combine chunks into full text with position markers
        full_text = ""
        chunk_map: dict[str, str] = {}
        for chunk_id, text in chunks:
            full_text += f"\n[CHUNK:{chunk_id}] {text}\n"
            chunk_map[chunk_id] = text

        # Detect if this document contains process content
        if not self._is_process_document(full_text, document_title):
            return []

        # Extract process name from title
        process_name = self._clean_process_name(document_title)
        process_id = f"PROC-{document_id}"

        # Extract steps
        steps = self._extract_steps(full_text, process_id, document_id, chunk_map)

        # Extract trigger
        trigger = self._extract_trigger(full_text)

        # Extract outcome
        outcome = self._extract_outcome(full_text)

        # Extract actors/teams
        actors = self._extract_actors(full_text)
        primary_team = team_id or (actors[0] if actors else None)

        # Extract systems
        systems = self._extract_systems(full_text)
        primary_system = systems[0] if systems else None

        if not steps:
            return []

        # Link steps
        self._link_steps(steps)

        process = ProcessDefinition(
            process_id=process_id,
            name=process_name,
            description=self._extract_description(full_text),
            trigger=trigger,
            outcome=outcome,
            source_documents=[document_id],
            steps=steps,
            quality=self._assess_quality(steps),
            confidence=self._compute_confidence(steps),
            team=primary_team,
            system=primary_system,
        )

        return [process]

    def _is_process_document(self, text: str, title: str) -> bool:
        """Determine if a document contains process content."""
        # Check title
        title_lower = title.lower()
        title_signals = [
            "process", "workflow", "procedure", "step", "handoff",
            "installation", "audit", "upload", "recovery", "communication",
            "handling", "guide", "charter", "integration",
        ]
        if any(s in title_lower for s in title_signals):
            return True

        # Check text for process language density
        process_words = [
            "step 1", "step 2", "step 3",
            "first,", "then,", "next,", "finally,",
            "responsible for", "owned by", "handoff",
            "triggered by", "approval", "prerequisite",
        ]
        text_lower = text.lower()
        count = sum(1 for w in process_words if w in text_lower)
        return count >= 2

    def _extract_steps(
        self,
        text: str,
        process_id: str,
        document_id: str,
        chunk_map: dict[str, str],
    ) -> list[ProcessStep]:
        """Extract process steps from text with explicit evidence."""
        steps: list[ProcessStep] = []
        seen_descriptions: set[str] = set()

        # Pattern 1: Numbered steps ("Step 1: ...", "1. ...")
        for pattern in _STEP_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) == 2:
                    seq_str, desc = groups
                    try:
                        seq = int(seq_str)
                    except ValueError:
                        seq = len(steps) + 1
                else:
                    desc = groups[0]
                    seq = len(steps) + 1

                desc = desc.strip().rstrip('.:')
                if len(desc) < 10 or desc.lower() in seen_descriptions:
                    continue
                seen_descriptions.add(desc.lower())

                # Find the chunk this came from
                chunk_id = self._find_source_chunk(match.start(), text)

                step = ProcessStep(
                    step_id=f"{process_id}-S{seq:03d}",
                    process_id=process_id,
                    sequence=seq,
                    description=desc,
                    source_document=document_id,
                    evidence_chunk=chunk_id,
                    evidence_text=desc[:200],
                    confidence=0.8,
                    evidence_level=EvidenceLevel.EXPLICIT.value,
                    validation_status="inferred",
                )

                # Extract actor from the step text
                actor = self._extract_actor_from_text(desc)
                if actor:
                    step.actor_team = actor

                # Extract system from the step text
                system = self._extract_system_from_text(desc)
                if system:
                    step.system = system

                # Extract action
                step.action = self._extract_action(desc)

                steps.append(step)

        # Pattern 2: Sequence patterns ("First, ...", "Then, ...", "Finally, ...")
        for pattern in _SEQUENCE_PATTERNS:
            for match in pattern.finditer(text):
                desc = match.group(1).strip().rstrip('.:')
                if len(desc) < 10 or desc.lower() in seen_descriptions:
                    continue
                seen_descriptions.add(desc.lower())

                seq = len(steps) + 1
                chunk_id = self._find_source_chunk(match.start(), text)

                step = ProcessStep(
                    step_id=f"{process_id}-S{seq:03d}",
                    process_id=process_id,
                    sequence=seq,
                    description=desc,
                    source_document=document_id,
                    evidence_chunk=chunk_id,
                    evidence_text=desc[:200],
                    confidence=0.7,
                    evidence_level=EvidenceLevel.EXPLICIT.value,
                    validation_status="inferred",
                )

                actor = self._extract_actor_from_text(desc)
                if actor:
                    step.actor_team = actor
                system = self._extract_system_from_text(desc)
                if system:
                    step.system = system
                step.action = self._extract_action(desc)

                steps.append(step)

        # Deduplicate by sequence number (keep first found)
        seen_seq: set[int] = set()
        unique_steps: list[ProcessStep] = []
        for s in steps:
            if s.sequence not in seen_seq:
                seen_seq.add(s.sequence)
                unique_steps.append(s)
        steps = unique_steps

        # Sort by sequence
        steps.sort(key=lambda s: s.sequence)
        return steps

    def _extract_trigger(self, text: str) -> Optional[str]:
        """Extract the process trigger."""
        for pattern in _TRIGGER_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()[:200]
        return None

    def _extract_outcome(self, text: str) -> Optional[str]:
        """Extract the process outcome."""
        for pattern in _OUTCOME_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()[:200]
        return None

    def _extract_actors(self, text: str) -> list[str]:
        """Extract team/actor mentions."""
        actors: list[str] = []
        for pattern in _ACTOR_PATTERNS:
            for match in pattern.finditer(text):
                actor = match.group(1).strip()
                # Normalize against known teams
                normalized = self._normalize_team(actor)
                if normalized and normalized not in actors:
                    actors.append(normalized)
        return actors

    def _extract_systems(self, text: str) -> list[str]:
        """Extract system mentions."""
        systems: list[str] = []
        text_lower = text.lower()
        for system in KNOWN_SYSTEMS:
            if system.lower() in text_lower and system not in systems:
                systems.append(system)
        return systems

    def _extract_actor_from_text(self, text: str) -> Optional[str]:
        """Extract a single actor from a step description."""
        for pattern in _ACTOR_PATTERNS:
            match = pattern.search(text)
            if match:
                return self._normalize_team(match.group(1).strip())
        return None

    def _extract_system_from_text(self, text: str) -> Optional[str]:
        """Extract a single system from a step description."""
        text_lower = text.lower()
        for system in KNOWN_SYSTEMS:
            if system.lower() in text_lower:
                return system
        return None

    def _extract_action(self, text: str) -> Optional[str]:
        """Extract the primary action verb phrase."""
        _ACTION_VERBS = {
            "verify", "validate", "check", "confirm", "ensure", "review",
            "approve", "reject", "send", "receive", "create", "update",
            "delete", "configure", "install", "deploy", "monitor", "run",
            "execute", "submit", "process", "handle", "manage", "escalate",
            "transfer", "assign", "notify", "log", "record", "document",
            "test", "activate", "enable", "disable", "reset", "schedule",
            "generate", "export", "import", "upload", "download", "merge",
            "compare", "analyze", "calculate", "produce", "deliver",
            "publish", "archive", "restore", "backup", "cleanup", "refresh",
            "migrate", "convert", "transform", "map", "match", "link",
            "extract", "parse", "scan", "detect", "identify", "classify",
            "queue", "route", "forward", "redirect", "retry", "rollback",
            "commit", "release", "tag", "mark", "flag", "accept", "deny",
            "permit", "block", "allow", "restrict", "authorize",
        }
        words = re.findall(r"(\w+)", text.lower())
        for w in words:
            if w in _ACTION_VERBS:
                return w
        # Fallback: first capitalized word
        for w in text.split():
            clean = w.strip(".,;:'")
            if len(clean) > 3 and clean[0].isupper():
                return clean.lower()
        return None

    def _normalize_team(self, name: str) -> Optional[str]:
        """Normalize a team name against known teams."""
        name_lower = name.lower().strip()
        for team in KNOWN_TEAMS:
            if team.lower() in name_lower or name_lower in team.lower():
                return team.lower()
        return name.lower() if len(name) < 30 else None

    def _find_source_chunk(self, pos: int, text: str) -> Optional[str]:
        """Find which chunk a character position belongs to."""
        # Search backwards for [CHUNK:...] marker
        before = text[:pos]
        marker_match = list(re.finditer(r'\[CHUNK:(.+?)\]', before))
        if marker_match:
            return marker_match[-1].group(1)
        return None

    def _clean_process_name(self, title: str) -> str:
        """Clean a document title into a process name."""
        # Remove common prefixes/suffixes
        name = re.sub(r'^(?:ACCOR|IDeaS|HTNG|HILTON)\s*[-–—]?\s*', '', title, flags=re.IGNORECASE)
        name = re.sub(r'\s*[-–—]\s*\d{8}_\d{6}\.pdf$', '', name)
        name = re.sub(r'\.pdf$', '', name, flags=re.IGNORECASE)
        name = name.strip()[:100]
        return name or title[:100]

    def _extract_description(self, text: str) -> str:
        """Extract a process description from the document."""
        # Look for purpose/scope/objective section
        desc_patterns = [
            re.compile(r'(?:purpose|scope|objective|overview|description)\s*[:\.]\s*(.+?)(?:\n\n|\Z)', re.IGNORECASE | re.DOTALL),
        ]
        for pattern in desc_patterns:
            match = pattern.search(text)
            if match:
                desc = match.group(1).strip()
                # Clean up
                desc = re.sub(r'\s+', ' ', desc)
                return desc[:500]
        return ""

    def _link_steps(self, steps: list[ProcessStep]) -> None:
        """Set predecessor/successor relationships."""
        for i, step in enumerate(steps):
            if i > 0:
                step.predecessor_step = steps[i - 1].step_id
            if i < len(steps) - 1:
                step.successor_step = steps[i + 1].step_id

    def _assess_quality(self, steps: list[ProcessStep]) -> str:
        """Assess process quality based on step evidence."""
        if not steps:
            return ProcessQuality.UNKNOWN.value

        explicit_count = sum(
            1 for s in steps if s.evidence_level == EvidenceLevel.EXPLICIT.value
        )
        ratio = explicit_count / len(steps) if steps else 0

        if ratio >= 0.8:
            return ProcessQuality.VERIFIED.value
        elif ratio >= 0.5:
            return ProcessQuality.PARTIALLY_VERIFIED.value
        elif ratio > 0:
            return ProcessQuality.INFERRED.value
        else:
            return ProcessQuality.UNKNOWN.value

    def _compute_confidence(self, steps: list[ProcessStep]) -> float:
        """Compute overall process confidence from step confidences."""
        if not steps:
            return 0.0
        return round(sum(s.confidence for s in steps) / len(steps), 3)


# ─── Gap Detection ──────────────────────────────────────────────────────────


class ProcessGapDetector:
    """Detects structural gaps in discovered processes."""

    def detect_gaps(self, process: ProcessDefinition) -> list[ProcessGap]:
        """Detect structural gaps in a process."""
        gaps: list[ProcessGap] = []
        steps = process.steps

        for i, step in enumerate(steps):
            # Gap: step with no owner
            if not step.actor_team:
                gaps.append(ProcessGap(
                    gap_id=f"GAP-{process.process_id}-NO-OWNER-{step.step_id}",
                    process_id=process.process_id,
                    gap_type="no_owner",
                    step_id=step.step_id,
                    description=f"Step '{step.description[:50]}' has no assigned team/actor",
                    severity="medium",
                ))

            # Gap: step with no successor (except the last step)
            if i < len(steps) - 1 and not step.successor_step:
                gaps.append(ProcessGap(
                    gap_id=f"GAP-{process.process_id}-NO-SUCCESSOR-{step.step_id}",
                    process_id=process.process_id,
                    gap_type="no_successor",
                    step_id=step.step_id,
                    description=f"Step '{step.description[:50]}' has no linked successor",
                    severity="low",
                ))

        # Gap: handoff with no receiving team
        for step in steps:
            if step.action in ("transfer", "forward", "send", "route", "handoff"):
                if not step.actor_team:
                    gaps.append(ProcessGap(
                        gap_id=f"GAP-{process.process_id}-NO-RECEIVER-{step.step_id}",
                        process_id=process.process_id,
                        gap_type="no_receiver",
                        step_id=step.step_id,
                        description=f"Handoff step '{step.description[:50]}' has no receiving team",
                        severity="high",
                    ))

        # Gap: process with conflicting instructions
        teams_in_steps = [s.actor_team for s in steps if s.actor_team]
        if len(set(teams_in_steps)) > 3:
            gaps.append(ProcessGap(
                gap_id=f"GAP-{process.process_id}-CONFLICTING",
                process_id=process.process_id,
                gap_type="conflicting",
                description=f"Process involves {len(set(teams_in_steps))} teams — may have conflicting instructions",
                severity="medium",
            ))

        return gaps


# ─── Database Operations ────────────────────────────────────────────────────


def ensure_process_tables() -> None:
    """Create process intelligence tables if they don't exist."""
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS processes (
            process_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT DEFAULT '',
            trigger_text TEXT,
            outcome TEXT,
            source_documents JSON DEFAULT '[]',
            quality VARCHAR DEFAULT 'unknown',
            confidence DOUBLE DEFAULT 0.5,
            team VARCHAR,
            system VARCHAR,
            step_count INTEGER DEFAULT 0,
            created_at VARCHAR DEFAULT '',
            updated_at VARCHAR DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS process_steps (
            step_id VARCHAR PRIMARY KEY,
            process_id VARCHAR NOT NULL,
            sequence INTEGER NOT NULL,
            description TEXT NOT NULL,
            actor_team VARCHAR,
            system VARCHAR,
            action VARCHAR,
            input_text TEXT,
            output_text TEXT,
            predecessor_step VARCHAR,
            successor_step VARCHAR,
            source_document VARCHAR,
            evidence_chunk VARCHAR,
            evidence_text TEXT,
            confidence DOUBLE DEFAULT 0.5,
            authority VARCHAR DEFAULT 'operational',
            evidence_level VARCHAR DEFAULT 'inferred',
            validation_status VARCHAR DEFAULT 'unknown',
            FOREIGN KEY (process_id) REFERENCES processes(process_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS process_gaps (
            gap_id VARCHAR PRIMARY KEY,
            process_id VARCHAR NOT NULL,
            gap_type VARCHAR NOT NULL,
            step_id VARCHAR,
            description TEXT DEFAULT '',
            severity VARCHAR DEFAULT 'medium',
            detected_at VARCHAR DEFAULT '',
            FOREIGN KEY (process_id) REFERENCES processes(process_id)
        )
    """)

    conn.close()


def persist_process(process: ProcessDefinition) -> None:
    """Persist a process and its steps to the database."""
    conn = get_connection()

    # Upsert process
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO processes
        (process_id, name, description, trigger_text, outcome, source_documents,
         quality, confidence, team, system, step_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(process_id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            trigger_text = excluded.trigger_text,
            outcome = excluded.outcome,
            source_documents = excluded.source_documents,
            quality = excluded.quality,
            confidence = excluded.confidence,
            team = excluded.team,
            system = excluded.system,
            step_count = excluded.step_count,
            updated_at = excluded.updated_at
    """, [
        process.process_id,
        process.name,
        process.description,
        process.trigger,
        process.outcome,
        __import__("json").dumps(process.source_documents),
        process.quality,
        process.confidence,
        process.team,
        process.system,
        len(process.steps),
        now,
        now,
    ])

    # Delete old steps for this process
    conn.execute("DELETE FROM process_steps WHERE process_id = ?", [process.process_id])

    # Insert steps
    for step in process.steps:
        conn.execute("""
            INSERT INTO process_steps
            (step_id, process_id, sequence, description, actor_team, system,
             action, input_text, output_text, predecessor_step, successor_step,
             source_document, evidence_chunk, evidence_text, confidence,
             authority, evidence_level, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            step.step_id, step.process_id, step.sequence, step.description,
            step.actor_team, step.system, step.action,
            step.input_text, step.output_text,
            step.predecessor_step, step.successor_step,
            step.source_document, step.evidence_chunk, step.evidence_text,
            step.confidence, step.authority, step.evidence_level, step.validation_status,
        ])

    conn.close()


def persist_gaps(gaps: list[ProcessGap]) -> None:
    """Persist detected gaps."""
    conn = get_connection()
    for gap in gaps:
        from datetime import datetime
        conn.execute("""
            INSERT INTO process_gaps
            (gap_id, process_id, gap_type, step_id, description, severity, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(gap_id) DO NOTHING
        """, [gap.gap_id, gap.process_id, gap.gap_type, gap.step_id, gap.description, gap.severity, datetime.utcnow().isoformat()])
    conn.close()


def get_process(process_id: str) -> Optional[dict]:
    """Get a process with its steps."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM processes WHERE process_id = ?", [process_id]
    ).fetchone()
    if not row:
        conn.close()
        return None

    cols = [d[0] for d in conn.execute("SELECT * FROM processes LIMIT 0").description]
    process = dict(zip(cols, row))

    step_rows = conn.execute(
        "SELECT * FROM process_steps WHERE process_id = ? ORDER BY sequence",
        [process_id],
    ).fetchall()
    step_cols = [d[0] for d in conn.execute("SELECT * FROM process_steps LIMIT 0").description]
    process["steps"] = [dict(zip(step_cols, r)) for r in step_rows]

    gap_rows = conn.execute(
        "SELECT * FROM process_gaps WHERE process_id = ?", [process_id]
    ).fetchall()
    gap_cols = [d[0] for d in conn.execute("SELECT * FROM process_gaps LIMIT 0").description]
    process["gaps"] = [dict(zip(gap_cols, r)) for r in gap_rows]

    conn.close()
    return process


def list_processes(
    team: Optional[str] = None,
    quality: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """List discovered processes."""
    conn = get_connection()
    conditions = ["1=1"]
    params: list = []
    if team:
        conditions.append("team = ?")
        params.append(team)
    if quality:
        conditions.append("quality = ?")
        params.append(quality)
    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT * FROM processes WHERE {where} ORDER BY confidence DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM processes LIMIT 0").description]
    result = [dict(zip(cols, r)) for r in rows]
    conn.close()
    return result


def get_process_stats() -> dict:
    """Get process intelligence statistics."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM processes").fetchone()[0]
    by_quality = dict(conn.execute(
        "SELECT quality, COUNT(*) FROM processes GROUP BY quality"
    ).fetchall())
    total_steps = conn.execute("SELECT COUNT(*) FROM process_steps").fetchone()[0]
    explicit_steps = conn.execute(
        "SELECT COUNT(*) FROM process_steps WHERE evidence_level = 'explicit'"
    ).fetchone()[0]
    total_gaps = conn.execute("SELECT COUNT(*) FROM process_gaps").fetchone()[0]
    by_gap_type = dict(conn.execute(
        "SELECT gap_type, COUNT(*) FROM process_gaps GROUP BY gap_type"
    ).fetchall())
    conn.close()
    return {
        "total_processes": total,
        "by_quality": by_quality,
        "total_steps": total_steps,
        "explicit_steps": explicit_steps,
        "total_gaps": total_gaps,
        "gaps_by_type": by_gap_type,
    }
