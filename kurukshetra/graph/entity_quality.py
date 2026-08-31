"""
Entity Quality Scoring
======================

Adds quality scores to graph entities without deleting them.

Quality labels:
- HIGH: Real organizational entity (systems, teams, processes)
- MEDIUM: Potentially relevant but needs verification
- LOW: Likely noise but not certain
- NOISE: Confidently garbage (stopwords, temp files, fragments)

Design principles:
- NEVER delete entities — only score and filter
- Preserve all provenance
- Quality scoring is deterministic
- High-quality entities are prioritized in retrieval
- Noise entities are excluded from entity-augmented search
"""

from __future__ import annotations

import re
from typing import Optional

from kurukshetra.registry.database import get_connection


# ── Stopwords and Garbage Patterns ─────────────────────────────

# Common English words that should NOT be organizational entities
STOPWORDS = {
    # Articles, pronouns, prepositions
    'a', 'an', 'the', 'this', 'that', 'these', 'those',
    'i', 'me', 'my', 'mine', 'we', 'our', 'ours',
    'you', 'your', 'yours', 'he', 'him', 'his', 'she', 'her', 'hers',
    'it', 'its', 'they', 'them', 'their', 'theirs',
    # Conjunctions, prepositions
    'and', 'or', 'but', 'nor', 'for', 'yet', 'so',
    'in', 'on', 'at', 'to', 'from', 'by', 'with', 'of', 'about',
    'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'under', 'over', 'up', 'down', 'out', 'off',
    # Verbs (common)
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'shall', 'must',
    'can', 'need', 'want', 'like', 'go', 'come', 'see', 'know', 'think',
    'say', 'said', 'make', 'take', 'give', 'show', 'tell', 'ask', 'try',
    'start', 'stop', 'open', 'close', 'read', 'write', 'send',
    'use', 'get', 'put', 'post', 'run', 'set', 'add', 'remove', 'delete',
    'create', 'update', 'include', 'cover', 'perform', 'check',
    # Question words
    'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how',
    # Common nouns (not organizational)
    'step', 'steps', 'case', 'cases', 'note', 'notes', 'help',
    'time', 'way', 'day', 'year', 'week', 'month', 'hour', 'minute',
    'number', 'list', 'item', 'line', 'page', 'file', 'type', 'name',
    'value', 'data', 'info', 'text', 'part', 'section', 'group', 'level',
    'point', 'form', 'tool', 'code', 'view', 'status', 'support',
    'process', 'system', 'account', 'close', 'each', 'then',
    'not', 'no', 'yes', 'all', 'every', 'both', 'few', 'more', 'most',
    'other', 'some', 'such', 'only', 'own', 'same', 'just', 'also',
    'now', 'here', 'there', 'if', 'than', 'so', 'when',
    'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
    'must', 'should', 'would', 'could', 'will',
}

# Patterns that indicate noise
NOISE_PATTERNS = [
    # Temp file names
    re.compile(r'^tmp[a-z0-9]{4,}\.txt$', re.IGNORECASE),
    re.compile(r'^doc\.txt$', re.IGNORECASE),
    re.compile(r'^tmp_?\w+\.txt$', re.IGNORECASE),
    # Numeric-only
    re.compile(r'^\d+[\d\s,.]*$'),
    # Temporal expressions
    re.compile(r'^\d+\s*(days?|weeks?|months?|hours?|minutes?|years?)$', re.IGNORECASE),
    # Range expressions
    re.compile(r'^\d+\s+to\s+\d+$', re.IGNORECASE),
    # Single character
    re.compile(r'^.$'),
    # Very short (2 chars) that aren't acronyms
    re.compile(r'^[^A-Z]{2}$'),
    # Sentence fragments (> 50 chars, likely extracted incorrectly)
    # Handled separately
]

# Known organizational entities (whitelist)
KNOWN_ORGANIZATIONAL = {
    # Teams
    'SPM', 'ICS', 'SDOPS', 'ROA', 'IT', 'HR', 'CPM', 'PMO', 'NOC',
    # Systems
    'G3', 'G3 RMS', 'RMS', 'OHIP', 'Opera', 'FOLS', 'Demand360',
    'NGI', 'Optix', 'SFDC', 'Salesforce', 'Datadog', 'SynXis',
    # Processes
    'AMS Recoding', 'Proactive Monitoring', 'Agile Rates',
    'Property Management', 'Property Setup',
    'Data Feed Configuration', 'Duplicate Group Deletion',
    'Agent to Agent Migration', 'SSD to OCIM',
    'Stats to Inventory', 'Rate Shopping Migration',
}


def _normalize_name(name: str) -> str:
    """Normalize entity name for comparison."""
    return (name or '').lower().strip()


def score_entity(
    name: str,
    entity_type: str,
    evidence_count: int = 0,
    doc_count: int = 0,
) -> tuple[float, str]:
    """
    Score an entity's quality.

    Returns:
        (quality_score, quality_label)
        score: 0.0 (noise) to 1.0 (high quality)
        label: 'HIGH', 'MEDIUM', 'LOW', or 'NOISE'
    """
    if not name or not name.strip():
        return 0.0, 'NOISE'

    normalized = _normalize_name(name)
    name_stripped = name.strip()

    # Check whitelist first
    if name_stripped in KNOWN_ORGANIZATIONAL or normalized in {e.lower() for e in KNOWN_ORGANIZATIONAL}:
        return 1.0, 'HIGH'

    # Check stopwords
    if normalized in STOPWORDS:
        return 0.0, 'NOISE'

    # Check noise patterns
    for pattern in NOISE_PATTERNS:
        if pattern.match(name_stripped):
            return 0.0, 'NOISE'

    # Sentence fragments (> 50 chars)
    if len(name_stripped) > 50:
        return 0.1, 'NOISE'

    # Very short names that aren't acronyms
    if len(normalized) <= 2 and not name_stripped.isupper():
        return 0.1, 'NOISE'

    # Score based on characteristics
    score = 0.5  # Base score

    # Bonus: acronym-style (all caps, 2-10 chars)
    if name_stripped.isupper() and 2 <= len(name_stripped) <= 10:
        score += 0.2

    # Bonus: CamelCase or has spaces with capital letters (multi-word entity)
    if ' ' in name_stripped and any(c.isupper() for c in name_stripped):
        score += 0.1

    # Bonus: evidence count
    if evidence_count >= 10:
        score += 0.15
    elif evidence_count >= 5:
        score += 0.1
    elif evidence_count >= 2:
        score += 0.05

    # Bonus: multiple source documents
    if doc_count >= 5:
        score += 0.1
    elif doc_count >= 2:
        score += 0.05

    # Bonus: entity type is system or team
    if entity_type in ('system', 'team', 'configuration'):
        score += 0.1

    # Penalty: entity type is job (often noise)
    if entity_type == 'job':
        score -= 0.3

    # Penalty: entity type is document (temp files)
    if entity_type == 'document':
        score -= 0.2

    # Clamp
    score = max(0.0, min(1.0, score))

    # Determine label
    if score >= 0.7:
        label = 'HIGH'
    elif score >= 0.4:
        label = 'MEDIUM'
    elif score >= 0.2:
        label = 'LOW'
    else:
        label = 'NOISE'

    return round(score, 3), label


def apply_quality_scores(dry_run: bool = False) -> dict:
    """
    Apply quality scores to all graph entities.

    Args:
        dry_run: If True, don't modify the database

    Returns:
        Summary statistics
    """
    conn = get_connection()

    # Add columns if they don't exist
    try:
        conn.execute("ALTER TABLE graph_entities ADD COLUMN quality_score DOUBLE DEFAULT 0.5")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE graph_entities ADD COLUMN quality_label VARCHAR DEFAULT 'MEDIUM'")
    except Exception:
        pass

    # Get all entities with their evidence counts
    rows = conn.execute('''
        SELECT ge.id, ge.name, ge.entity_type,
               COUNT(gevid.evidence_id) as ev_count,
               COUNT(DISTINCT gevid.source_document) as doc_count
        FROM graph_entities ge
        LEFT JOIN graph_evidence gevid ON gevid.entity_id = ge.id
        GROUP BY ge.id, ge.name, ge.entity_type
    ''').fetchall()

    stats = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'NOISE': 0, 'total': len(rows)}

    for entity_id, name, entity_type, ev_count, doc_count in rows:
        score, label = score_entity(name, entity_type, ev_count, doc_count)
        stats[label] += 1

        if not dry_run:
            conn.execute(
                "UPDATE graph_entities SET quality_score = ?, quality_label = ? WHERE id = ?",
                (score, label, entity_id),
            )

    if not dry_run:
        conn.commit()
    conn.close()

    return stats


def get_quality_report() -> dict:
    """Get a quality report of the graph."""
    conn = get_connection()

    # Check if quality columns exist
    try:
        conn.execute("SELECT quality_label FROM graph_entities LIMIT 1")
    except Exception:
        return {"error": "Quality scores not yet applied. Run apply_quality_scores() first."}

    # Overall distribution
    rows = conn.execute('''
        SELECT quality_label, COUNT(*) as cnt
        FROM graph_entities
        GROUP BY quality_label
        ORDER BY cnt DESC
    ''').fetchall()

    distribution = {r[0]: r[1] for r in rows}

    # High-quality entities
    high_quality = conn.execute('''
        SELECT ge.name, ge.entity_type, ge.quality_score,
               COUNT(gevid.evidence_id) as ev_count,
               COUNT(DISTINCT gevid.source_document) as doc_count
        FROM graph_entities ge
        LEFT JOIN graph_evidence gevid ON gevid.entity_id = ge.id
        WHERE ge.quality_label = 'HIGH'
        GROUP BY ge.id, ge.name, ge.entity_type, ge.quality_score
        ORDER BY ev_count DESC
        LIMIT 30
    ''').fetchall()

    # Noise entities
    noise = conn.execute('''
        SELECT ge.name, ge.entity_type, ge.quality_score
        FROM graph_entities ge
        WHERE ge.quality_label = 'NOISE'
        ORDER BY ge.quality_score ASC
        LIMIT 20
    ''').fetchall()

    conn.close()

    return {
        'distribution': distribution,
        'high_quality': [
            {'name': r[0], 'type': r[1], 'score': r[2], 'evidence': r[3], 'docs': r[4]}
            for r in high_quality
        ],
        'noise_examples': [
            {'name': r[0], 'type': r[1], 'score': r[2]}
            for r in noise
        ],
    }


def get_filtered_entities(min_quality: str = 'MEDIUM') -> list[str]:
    """
    Get entity IDs that meet the minimum quality threshold.

    Used by entity-augmented retrieval to exclude noise.
    """
    quality_order = {'NOISE': 0, 'LOW': 1, 'MEDIUM': 2, 'HIGH': 3}
    min_score = quality_order.get(min_quality, 1)

    conn = get_connection()
    try:
        conn.execute("SELECT quality_label FROM graph_entities LIMIT 1")
        rows = conn.execute('''
            SELECT id, quality_label FROM graph_entities
        ''').fetchall()
    except Exception:
        # Quality scores not applied yet — return all
        rows = conn.execute('SELECT id FROM graph_entities').fetchall()
        conn.close()
        return [r[0] for r in rows]

    conn.close()

    return [
        r[0] for r in rows
        if quality_order.get(r[1], 1) >= min_score
    ]
