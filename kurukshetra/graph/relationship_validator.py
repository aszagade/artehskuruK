"""
Relationship Validator
======================

Validates entity relationships against actual document text.

Problem: graph_evidence stores entity-document associations, but two entities
appearing in the same document doesn't mean they're related.

Solution: Verify that both entities appear in the SAME text chunk (or nearby chunks),
not just the same document.

This dramatically improves relationship precision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass
class ValidatedRelationship:
    """A relationship validated against actual document text."""
    entity_a: str
    entity_b: str
    entity_type_a: str
    entity_type_b: str
    validation_status: str  # 'VALID', 'WEAK', 'INVALID'
    supporting_documents: list[str]
    evidence_snippets: list[str]
    confidence: float
    evidence_count: int
    shared_doc_count: int


def validate_relationship(
    entity_a: str,
    entity_b: str,
    min_chunk_cooccurrence: int = 1,
) -> ValidatedRelationship:
    """
    Validate a single relationship by checking text-level co-occurrence.

    Returns ValidatedRelationship with validation_status:
    - VALID: both entities appear in the same chunk(s)
    - WEAK: entities appear in the same document but not same chunk
    - INVALID: no verifiable co-occurrence
    """
    conn = get_connection()

    # Get entity IDs
    ea_row = conn.execute(
        "SELECT id, entity_type FROM graph_entities WHERE name = ?",
        (entity_a,)
    ).fetchone()
    eb_row = conn.execute(
        "SELECT id, entity_type FROM graph_entities WHERE name = ?",
        (entity_b,)
    ).fetchone()

    if not ea_row or not eb_row:
        conn.close()
        return ValidatedRelationship(
            entity_a=entity_a, entity_b=entity_b,
            entity_type_a='unknown', entity_type_b='unknown',
            validation_status='INVALID',
            supporting_documents=[], evidence_snippets=[],
            confidence=0.0, evidence_count=0, shared_doc_count=0,
        )

    ea_id, ea_type = ea_row
    eb_id, eb_type = eb_row

    # Find shared documents
    shared_docs = conn.execute('''
        SELECT DISTINCT gevid1.source_document
        FROM graph_evidence gevid1
        JOIN graph_evidence gevid2 ON gevid2.source_document = gevid1.source_document
            AND gevid2.entity_id = ?
        WHERE gevid1.entity_id = ?
        AND gevid1.source_document LIKE 'DOC-%'
    ''', (eb_id, ea_id)).fetchall()

    doc_ids = [r[0] for r in shared_docs if r[0]]

    # Check text-level co-occurrence
    supporting_docs = []
    evidence_snippets = []

    for doc_id in doc_ids[:10]:
        chunks = conn.execute(
            "SELECT text FROM chunks WHERE document_id = ? LIMIT 20",
            (doc_id,)
        ).fetchall()

        for chunk_row in chunks:
            text = (chunk_row[0] or '').lower()
            ea_lower = entity_a.lower()
            eb_lower = entity_b.lower()

            if ea_lower in text and eb_lower in text:
                # Both entities in same chunk — strong evidence
                supporting_docs.append(doc_id)
                # Extract snippet around first entity mention
                idx = text.find(ea_lower)
                start = max(0, idx - 50)
                end = min(len(text), idx + 100)
                snippet = text[start:end].strip()
                evidence_snippets.append(snippet)
                break

    conn.close()

    # Determine validation status
    if len(supporting_docs) >= min_chunk_cooccurrence:
        status = 'VALID'
        confidence = min(0.5 + len(supporting_docs) * 0.1, 1.0)
    elif len(doc_ids) > 0:
        status = 'WEAK'
        confidence = 0.3
    else:
        status = 'INVALID'
        confidence = 0.0

    return ValidatedRelationship(
        entity_a=entity_a,
        entity_b=entity_b,
        entity_type_a=ea_type,
        entity_type_b=eb_type,
        validation_status=status,
        supporting_documents=supporting_docs[:5],
        evidence_snippets=evidence_snippets[:3],
        confidence=round(confidence, 3),
        evidence_count=len(doc_ids),
        shared_doc_count=len(doc_ids),
    )


def validate_all_relationships(
    min_evidence: int = 5,
    min_shared_docs: int = 2,
) -> dict:
    """
    Validate all cross-team relationships and return a precision report.
    """
    conn = get_connection()

    # Get all candidate relationships
    rows = conn.execute('''
        SELECT DISTINCT
            ge1.name, ge1.entity_type, ge2.name, ge2.entity_type,
            COUNT(DISTINCT gevid1.source_document) as shared_docs,
            COUNT(gevid1.evidence_id) as evidence_count
        FROM graph_entities ge1
        JOIN graph_evidence gevid1 ON gevid1.entity_id = ge1.id
        JOIN graph_evidence gevid2 ON gevid2.source_document = gevid1.source_document
            AND gevid2.entity_id != gevid1.entity_id
        JOIN graph_entities ge2 ON gevid2.entity_id = ge2.id
        WHERE ge1.id < ge2.id
        AND ge1.quality_score >= 0.5 AND ge2.quality_score >= 0.5
        GROUP BY ge1.name, ge1.entity_type, ge2.name, ge2.entity_type
        HAVING shared_docs >= ? AND evidence_count >= ?
        ORDER BY evidence_count DESC
        LIMIT 50
    ''', (min_shared_docs, min_evidence)).fetchall()

    conn.close()

    results = []
    valid_count = 0
    weak_count = 0
    invalid_count = 0

    for ea, ta, eb, tb, docs, ev in rows:
        vr = validate_relationship(ea, eb)
        results.append(vr)

        if vr.validation_status == 'VALID':
            valid_count += 1
        elif vr.validation_status == 'WEAK':
            weak_count += 1
        else:
            invalid_count += 1

    total = len(results)
    precision = valid_count / max(total, 1)
    precision_weak = (valid_count + weak_count) / max(total, 1)

    return {
        'total': total,
        'valid': valid_count,
        'weak': weak_count,
        'invalid': invalid_count,
        'precision_strict': round(precision, 3),
        'precision_with_weak': round(precision_weak, 3),
        'relationships': results,
    }


def get_validated_relationships() -> list[ValidatedRelationship]:
    """Get only VALID relationships (text-level co-occurrence verified)."""
    report = validate_all_relationships()
    return [r for r in report['relationships'] if r.validation_status == 'VALID']
