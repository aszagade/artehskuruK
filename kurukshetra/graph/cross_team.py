"""
Cross-Team Relationship Builder
================================

Builds reliable cross-team relationships from actual graph evidence.

Rules:
- A relationship requires co-occurrence in the SAME document
- A relationship requires evidence from multiple chunks
- A relationship requires quality-scored entities
- Never infer relationships without evidence
- Preserve provenance for every relationship
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass
class CrossTeamRelationship:
    """A verified cross-team relationship."""
    concept_a: str
    concept_b: str
    relationship_type: str  # 'system_team', 'team_team', 'system_system', etc.
    evidence_count: int
    source_documents: list[str]
    confidence: float
    team_a: str
    team_b: str


def build_cross_team_relationships(min_evidence: int = 2) -> list[CrossTeamRelationship]:
    """
    Build cross-team relationships from co-occurrence in documents.

    Only considers entities with quality_score >= 0.4 (MEDIUM or above).
    """
    conn = get_connection()

    # Check if quality columns exist
    try:
        conn.execute("SELECT quality_label FROM graph_entities LIMIT 1")
        quality_filter = "AND ge1.quality_score >= 0.4 AND ge2.quality_score >= 0.4"
    except Exception:
        quality_filter = ""

    # Get all quality entities with their document co-occurrences
    rows = conn.execute(f'''
        SELECT DISTINCT
            ge1.name as entity_a,
            ge1.entity_type as type_a,
            ge2.name as entity_b,
            ge2.entity_type as type_b,
            COUNT(DISTINCT gevid1.source_document) as shared_docs,
            COUNT(gevid1.evidence_id) as evidence_count
        FROM graph_entities ge1
        JOIN graph_evidence gevid1 ON gevid1.entity_id = ge1.id
        JOIN graph_evidence gevid2 ON gevid2.source_document = gevid1.source_document
            AND gevid2.entity_id != gevid1.entity_id
        JOIN graph_entities ge2 ON gevid2.entity_id = ge2.id
        WHERE ge1.id < ge2.id
        {quality_filter}
        GROUP BY ge1.name, ge1.entity_type, ge2.name, ge2.entity_type
        HAVING shared_docs >= ? AND evidence_count >= ?
        ORDER BY evidence_count DESC
    ''', (min_evidence, min_evidence)).fetchall()

    relationships = []
    for row in rows:
        entity_a, type_a, entity_b, type_b, shared_docs, evidence_count = row

        # Determine relationship type
        rel_type = _classify_relationship(type_a, type_b)

        # Get source documents
        doc_rows = conn.execute('''
            SELECT DISTINCT gevid.source_document
            FROM graph_entities ge1
            JOIN graph_evidence gevid ON gevid.entity_id = ge1.id
            JOIN graph_entities ge2 ON ge2.id = gevid.entity_id
            WHERE ge1.name = ? AND ge2.name = ?
            LIMIT 5
        ''', (entity_a, entity_b)).fetchall()
        source_docs = [r[0] for r in doc_rows if r[0]]

        # Get teams for each entity
        team_a = _get_entity_team(conn, entity_a)
        team_b = _get_entity_team(conn, entity_b)

        # Confidence based on evidence strength
        confidence = min(0.5 + (evidence_count / 20.0) + (shared_docs / 10.0), 1.0)

        relationships.append(CrossTeamRelationship(
            concept_a=entity_a,
            concept_b=entity_b,
            relationship_type=rel_type,
            evidence_count=evidence_count,
            source_documents=source_docs,
            confidence=round(confidence, 3),
            team_a=team_a,
            team_b=team_b,
        ))

    conn.close()
    return relationships


def _classify_relationship(type_a: str, type_b: str) -> str:
    """Classify the type of relationship between two entities."""
    types = sorted([type_a, type_b])
    if types == ['system', 'team']:
        return 'system_team'
    elif types == ['team', 'team']:
        return 'team_team'
    elif types == ['system', 'system']:
        return 'system_system'
    elif types == ['process', 'system'] or types == ['process', 'team']:
        return 'process_related'
    elif 'property' in types or 'configuration' in types:
        return 'config_related'
    return 'other'


def _get_entity_team(conn, entity_name: str) -> str:
    """Get the primary team associated with an entity."""
    row = conn.execute('''
        SELECT team_id FROM concept_teams
        WHERE LOWER(concept_name) = LOWER(?)
        ORDER BY confidence DESC
        LIMIT 1
    ''', (entity_name,)).fetchone()
    return row[0] if row else ''


def get_knowledge_brain_snapshot() -> dict:
    """
    Generate a comprehensive brain snapshot showing what SANJAYA actually knows.

    This replaces simple row counts with meaningful knowledge representation.
    """
    conn = get_connection()

    snapshot = {}

    # Documents
    r = conn.execute('SELECT COUNT(*) FROM documents').fetchone()
    snapshot['documents'] = {'total': r[0]}

    # By team
    rows = conn.execute('''
        SELECT team_owner, COUNT(*) FROM documents
        WHERE team_owner IS NOT NULL AND team_owner != ''
        GROUP BY team_owner ORDER BY COUNT(*) DESC
    ''').fetchall()
    snapshot['documents']['by_team'] = {r[0]: r[1] for r in rows}

    # Chunks
    r = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()
    snapshot['chunks'] = r[0]

    # Teams (from documents)
    teams = set()
    for team in snapshot['documents']['by_team'].keys():
        teams.add(team.lower())
    # Also from concept_teams
    team_rows = conn.execute('SELECT DISTINCT team_id FROM concept_teams').fetchall()
    for r in team_rows:
        if r[0]:
            teams.add(r[0].lower())
    snapshot['teams'] = sorted(teams)

    # Systems (high-quality entities of type system)
    try:
        rows = conn.execute('''
            SELECT ge.name, COUNT(gevid.evidence_id) as ev,
                   COUNT(DISTINCT gevid.source_document) as docs
            FROM graph_entities ge
            LEFT JOIN graph_evidence gevid ON gevid.entity_id = ge.id
            WHERE ge.entity_type = 'system'
            AND (ge.quality_score IS NULL OR ge.quality_score >= 0.5)
            GROUP BY ge.id, ge.name
            ORDER BY ev DESC
        ''').fetchall()
        snapshot['systems'] = [
            {'name': r[0], 'evidence': r[1], 'documents': r[2]}
            for r in rows
        ]
    except Exception:
        snapshot['systems'] = []

    # Processes (high-quality)
    try:
        rows = conn.execute('''
            SELECT ge.name, COUNT(gevid.evidence_id) as ev,
                   COUNT(DISTINCT gevid.source_document) as docs
            FROM graph_entities ge
            LEFT JOIN graph_evidence gevid ON gevid.entity_id = ge.id
            WHERE ge.entity_type = 'process'
            AND (ge.quality_score IS NULL OR ge.quality_score >= 0.6)
            AND LENGTH(ge.name) <= 60
            GROUP BY ge.id, ge.name
            ORDER BY ev DESC
            LIMIT 20
        ''').fetchall()
        snapshot['processes'] = [
            {'name': r[0], 'evidence': r[1], 'documents': r[2]}
            for r in rows
        ]
    except Exception:
        snapshot['processes'] = []

    # Cross-team concepts
    try:
        rows = conn.execute('''
            SELECT concept_name, COUNT(DISTINCT team_id) as team_count,
                   GROUP_CONCAT(DISTINCT team_id) as teams
            FROM concept_teams
            GROUP BY concept_name
            HAVING team_count > 1
            ORDER BY team_count DESC
            LIMIT 20
        ''').fetchall()
        snapshot['cross_team_concepts'] = [
            {'concept': r[0], 'teams': r[2].split(','), 'team_count': r[1]}
            for r in rows
        ]
    except Exception:
        snapshot['cross_team_concepts'] = []

    # Document versions
    try:
        r = conn.execute('SELECT COUNT(*) FROM document_versions').fetchone()
        snapshot['document_versions'] = r[0]
    except Exception:
        snapshot['document_versions'] = 0

    # Feedback summary
    try:
        r = conn.execute('SELECT COUNT(*) FROM rag_feedback').fetchone()
        pos = conn.execute('SELECT COUNT(*) FROM rag_feedback WHERE is_correct = true').fetchone()
        snapshot['feedback'] = {'total': r[0], 'positive': pos[0]}
    except Exception:
        snapshot['feedback'] = {'total': 0, 'positive': 0}

    # Graph entity quality distribution
    try:
        rows = conn.execute('''
            SELECT quality_label, COUNT(*) FROM graph_entities
            GROUP BY quality_label
        ''').fetchall()
        snapshot['graph_quality'] = {r[0]: r[1] for r in rows}
    except Exception:
        snapshot['graph_quality'] = {}

    # Cross-team relationships
    relationships = build_cross_team_relationships(min_evidence=3)
    snapshot['cross_team_relationships'] = [
        {
            'a': r.concept_a, 'b': r.concept_b,
            'type': r.relationship_type,
            'evidence': r.evidence_count,
            'docs': len(r.source_documents),
            'confidence': r.confidence,
        }
        for r in relationships[:30]
    ]

    # Unknown terms
    try:
        from kurukshetra.services.glossary import GlossaryManager
        gm = GlossaryManager()
        unknowns = gm.get_unknown_terms(limit=20)
        snapshot['unknown_terms'] = len(unknowns)
    except Exception:
        snapshot['unknown_terms'] = 0

    conn.close()
    return snapshot
