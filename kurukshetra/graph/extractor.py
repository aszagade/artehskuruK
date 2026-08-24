"""
Smart Entity Extractor
======================

Extracts entities from document text and builds relationships with evidence.

Responsibilities:
  1. Extract SYSTEM, PROCESS, INCIDENT, CONFIGURATION, JOB entities from text
  2. Resolve TEAM entities from OrgMap (every document has a team owner)
  3. Infer CLIENT/PROPERTY entities from document content
  4. Deduplicate entities across documents
  5. Attach Evidence to every extracted relationship
  6. Never hardcode document-specific logic

This is the primary input to the Knowledge Graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .entity_types import (
    Evidence,
    ExtendedEntity,
    ExtendedEntityType,
    ExtendedRelationship,
    ExtendedRelationType,
)


# =====================================================================
# Extraction patterns — organized by entity type
# =====================================================================

# --- SYSTEM ---
SYSTEM_PATTERNS = [
    re.compile(r"\b(G3\s*RMS|G3-RMS|Opera\s*Cloud|NGI|OXI|OHIP|FOLS|TARS|CP\s*Pricing)\b", re.IGNORECASE),
    re.compile(r"\b(Datadog|Smartsheet|SFDC|Salesforce|JIRA|SynXis|Curtis)\b", re.IGNORECASE),
    re.compile(r"\b(RabbitMQ|Kafka|SAS|SQL\s*Server|Docker|Kubernetes)\b", re.IGNORECASE),
    re.compile(r"\b(Opera\s*Agent|Opera\s*REST|Opera\s*Cloud\s*Agent)\b", re.IGNORECASE),
    re.compile(r"\b(HTNG|OHIP\s*Emulator|NGI\s*Agent)\b", re.IGNORECASE),
    re.compile(r"\b(Mews|OPERA\s*PMS)\b", re.IGNORECASE),
]

# --- INCIDENT / ERROR ---
INCIDENT_PATTERNS = [
    re.compile(r"\b(\w+Step)\s+(?:failure|failed|error)", re.IGNORECASE),
    re.compile(r"(?:error|exception|failure|crash)[\s:]+([A-Z][\w\s]{5,60})", re.IGNORECASE),
    re.compile(r"\b(step\s*\d+\s*(?:failure|error|failed))\b", re.IGNORECASE),
    re.compile(r"\b(job\s+(?:failure|failed|error))\b", re.IGNORECASE),
    re.compile(r"\b(timeout|connection\s+(?:refused|lost|timeout))\b", re.IGNORECASE),
]

# --- PROCESS / WORKFLOW ---
PROCESS_PATTERNS = [
    re.compile(r"(?:process|procedure|workflow|steps?)\s+(?:to\s+)?(\w[\w\s]{5,50})", re.IGNORECASE),
    re.compile(r"(?:installation|migration|configuration|monitoring)\s+(?:of\s+)?(\w[\w\s]{5,50})", re.IGNORECASE),
    re.compile(r"\b(onboarding\s+(?:process|procedure|workflow))\b", re.IGNORECASE),
    re.compile(r"\b(deployment\s+(?:process|procedure|steps?))\b", re.IGNORECASE),
    re.compile(r"\b(rollback\s+(?:procedure|process|steps?))\b", re.IGNORECASE),
    re.compile(r"\b(data\s+feed\s+(?:process|flow|procedure))\b", re.IGNORECASE),
    re.compile(r"\b(decision\s+upload\s+(?:process|procedure|workflow))\b", re.IGNORECASE),
]

# --- CONFIGURATION ---
CONFIGURATION_PATTERNS = [
    re.compile(r"(?:parameter|setting|config(?:uration)?)\s*[:=]\s*(\w+)", re.IGNORECASE),
    re.compile(r"(?:enable|disable|activate|deactivate)\s+(\w+)", re.IGNORECASE),
    re.compile(r"\b(CP\s*Config|property\s+config(?:uration)?)\b", re.IGNORECASE),
    re.compile(r"\b(restriction\s+level\s*[:=]?\s*\w+)\b", re.IGNORECASE),
    re.compile(r"\b(bar\s+upload\s+(?:setting|config))\b", re.IGNORECASE),
]

# --- JOB ---
JOB_PATTERNS = [
    re.compile(r"\b(\w+)\s+(?:job|batch|task|run)\b", re.IGNORECASE),
    re.compile(r"\b(full\s+upload)\b", re.IGNORECASE),
    re.compile(r"\b(first\s+decision)\b", re.IGNORECASE),
    re.compile(r"\b(catchup)\b", re.IGNORECASE),
    re.compile(r"\b(pull\s+extract)\b", re.IGNORECASE),
    re.compile(r"\b(demand\s+360)\b", re.IGNORECASE),
    re.compile(r"\b(benefit\s+measurement)\b", re.IGNORECASE),
]

# --- CLIENT / PROPERTY ---
CLIENT_PROPERTY_PATTERNS = [
    re.compile(r"\b(property\s+(?:configuration|setup|installation|management))\b", re.IGNORECASE),
    re.compile(r"\b(new\s+property)\b", re.IGNORECASE),
    re.compile(r"\b(add\s+property)\b", re.IGNORECASE),
    re.compile(r"\b(property\s+id\s*[:=]?\s*(\w+))\b", re.IGNORECASE),
    re.compile(r"\b(hotel\s+([\w\s]+?)(?:\s+\.|\s+is|\s+has|\s+\.))", re.IGNORECASE),
    re.compile(r"\b(client\s+([\w\s]+?)(?:\s+\.|\s+is|\s+has|\s+\.))", re.IGNORECASE),
]


# =====================================================================
# Extraction result
# =====================================================================

@dataclass(slots=True)
class ExtractionResult:
    """Result of entity and relationship extraction from a document."""
    document_id: str
    entities: list[ExtendedEntity]
    relationships: list[ExtendedRelationship]
    extraction_confidence: float
    entities_by_type: dict[str, int] = field(default_factory=dict)


# =====================================================================
# SmartEntityExtractor
# =====================================================================

class SmartEntityExtractor:
    """
    Extracts entities and relationships from document text.

    Uses:
    - Pattern matching for SYSTEM, INCIDENT, PROCESS, CONFIGURATION, JOB
    - OrgMap for TEAM resolution
    - Content heuristics for CLIENT/PROPERTY
    - Deduplication across documents
    - Evidence attached to every relationship

    This class never hardcodes document-specific logic.
    """

    def __init__(self) -> None:
        # Entity deduplication cache: entity_id -> ExtendedEntity
        self._entity_cache: dict[str, ExtendedEntity] = {}

    def extract_from_document(
        self,
        text: str,
        document_id: str,
        document_title: str = "",
        team_id: Optional[str] = None,
        product_scope: Optional[list[str]] = None,
    ) -> ExtractionResult:
        """
        Extract all entities and relationships from a document.

        Args:
            text: full document text
            document_id: unique document identifier
            document_title: human-readable title
            team_id: owning team from OrgMap (if known)
            product_scope: products this document relates to

        Returns:
            ExtractionResult with deduplicated entities and evidence-backed relationships
        """
        entities: list[ExtendedEntity] = []
        relationships: list[ExtendedRelationship] = []

        # 1. Create the DOCUMENT entity
        doc_entity = self._make_entity(
            entity_id=f"DOC-{document_id}",
            name=document_title or document_id,
            entity_type=ExtendedEntityType.DOCUMENT,
            description=f"Document: {document_title}",
            team_id=team_id,
            product_scope=product_scope or [],
            evidence_source=document_id,
            evidence_text=f"Document '{document_title}' registered in system",
        )
        entities.append(doc_entity)

        # 2. Create TEAM entity if team_id is provided
        if team_id:
            team_entity = self._make_entity(
                entity_id=f"TEAM-{team_id.upper()}",
                name=team_id.upper(),
                entity_type=ExtendedEntityType.TEAM,
                description=f"Team: {team_id.upper()}",
                team_id=team_id,
                evidence_source=document_id,
                evidence_text=f"Document classified to team {team_id.upper()}",
            )
            entities.append(team_entity)

            # OWNED_BY relationship: document → team
            relationships.append(self._make_relationship(
                source_id=doc_entity.id,
                target_id=team_entity.id,
                relation_type=ExtendedRelationType.OWNED_BY,
                description=f"Document is owned by {team_id.upper()} team",
                evidence_source=document_id,
                evidence_text=f"Team classification assigned {team_id.upper()}",
                confidence=0.9,
            ))

        # 3. Extract SYSTEM entities
        system_entities = self._extract_by_patterns(
            patterns=SYSTEM_PATTERNS,
            entity_type=ExtendedEntityType.SYSTEM,
            id_prefix="SYS",
            text=text,
            evidence_source=document_id,
        )
        entities.extend(system_entities)

        # Link document → systems (USES)
        for sys_entity in system_entities:
            relationships.append(self._make_relationship(
                source_id=doc_entity.id,
                target_id=sys_entity.id,
                relation_type=ExtendedRelationType.USES,
                description=f"Document references system {sys_entity.name}",
                evidence_source=document_id,
                evidence_text=f"System '{sys_entity.name}' found in document text",
                confidence=0.8,
            ))

        # 4. Extract INCIDENT entities
        incident_entities, incident_rels = self._extract_incidents(
            text=text, document_id=document_id
        )
        entities.extend(incident_entities)
        relationships.extend(incident_rels)

        # Link document → incidents (RESOLVES)
        for inc_entity in incident_entities:
            relationships.append(self._make_relationship(
                source_id=doc_entity.id,
                target_id=inc_entity.id,
                relation_type=ExtendedRelationType.RESOLVES,
                description=f"Document helps resolve {inc_entity.name}",
                evidence_source=document_id,
                evidence_text=f"Incident '{inc_entity.name}' mentioned with resolution context",
                confidence=0.7,
            ))

        # 5. Extract PROCESS entities
        process_entities = self._extract_by_patterns(
            patterns=PROCESS_PATTERNS,
            entity_type=ExtendedEntityType.PROCESS,
            id_prefix="PROC",
            text=text,
            evidence_source=document_id,
        )
        entities.extend(process_entities)

        # Link document → processes (REFERENCES)
        for proc_entity in process_entities:
            relationships.append(self._make_relationship(
                source_id=doc_entity.id,
                target_id=proc_entity.id,
                relation_type=ExtendedRelationType.REFERENCES,
                description=f"Document describes process: {proc_entity.name}",
                evidence_source=document_id,
                evidence_text=f"Process '{proc_entity.name}' found in document",
                confidence=0.75,
            ))

        # 6. Extract CONFIGURATION entities
        config_entities = self._extract_by_patterns(
            patterns=CONFIGURATION_PATTERNS,
            entity_type=ExtendedEntityType.CONFIGURATION,
            id_prefix="CFG",
            text=text,
            evidence_source=document_id,
        )
        entities.extend(config_entities)

        # Link document → configs (CONFIGURES)
        for cfg_entity in config_entities:
            relationships.append(self._make_relationship(
                source_id=doc_entity.id,
                target_id=cfg_entity.id,
                relation_type=ExtendedRelationType.CONFIGURES,
                description=f"Document describes configuration: {cfg_entity.name}",
                evidence_source=document_id,
                evidence_text=f"Configuration '{cfg_entity.name}' found in document",
                confidence=0.7,
            ))

        # 7. Extract JOB entities
        job_entities = self._extract_by_patterns(
            patterns=JOB_PATTERNS,
            entity_type=ExtendedEntityType.JOB,
            id_prefix="JOB",
            text=text,
            evidence_source=document_id,
        )
        entities.extend(job_entities)

        # Link document → jobs (REFERENCES)
        for job_entity in job_entities:
            relationships.append(self._make_relationship(
                source_id=doc_entity.id,
                target_id=job_entity.id,
                relation_type=ExtendedRelationType.REFERENCES,
                description=f"Document references job: {job_entity.name}",
                evidence_source=document_id,
                evidence_text=f"Job '{job_entity.name}' found in document",
                confidence=0.65,
            ))

        # 8. Extract CLIENT/PROPERTY entities
        client_entities = self._extract_client_property(
            text=text, document_id=document_id
        )
        entities.extend(client_entities)

        # Link document → clients/properties (REFERENCES)
        for cp_entity in client_entities:
            relationships.append(self._make_relationship(
                source_id=doc_entity.id,
                target_id=cp_entity.id,
                relation_type=ExtendedRelationType.REFERENCES,
                description=f"Document references {cp_entity.name}",
                evidence_source=document_id,
                evidence_text=f"Client/Property '{cp_entity.name}' found in document",
                confidence=0.6,
            ))

        # 9. Infer cross-entity relationships
        inferred_rels = self._infer_relationships(entities)
        relationships.extend(inferred_rels)

        # 10. Calculate extraction confidence
        confidence = self._calculate_extraction_confidence(entities, relationships)

        # Build type counts
        type_counts: dict[str, int] = {}
        for e in entities:
            type_counts[e.entity_type.value] = type_counts.get(e.entity_type.value, 0) + 1

        return ExtractionResult(
            document_id=document_id,
            entities=entities,
            relationships=relationships,
            extraction_confidence=round(confidence, 3),
            entities_by_type=type_counts,
        )

    # -----------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------

    def _make_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: ExtendedEntityType,
        description: str = "",
        team_id: Optional[str] = None,
        product_scope: Optional[list[str]] = None,
        evidence_source: str = "",
        evidence_text: str = "",
        confidence: float = 0.8,
    ) -> ExtendedEntity:
        """Create or retrieve from cache an ExtendedEntity."""
        # Check cache for deduplication
        if entity_id in self._entity_cache:
            # Add new evidence to existing entity
            evidence = Evidence(
                source_document=evidence_source,
                source_text=evidence_text,
                confidence=confidence,
            )
            self._entity_cache[entity_id].add_evidence(evidence)
            return self._entity_cache[entity_id]

        evidence = Evidence(
            source_document=evidence_source,
            source_text=evidence_text,
            confidence=confidence,
        )
        entity = ExtendedEntity(
            id=entity_id,
            name=name,
            entity_type=entity_type,
            description=description,
            team_id=team_id,
            product_scope=product_scope or [],
            evidence=[evidence],
            average_confidence=confidence,
        )
        self._entity_cache[entity_id] = entity
        return entity

    def _make_relationship(
        self,
        source_id: str,
        target_id: str,
        relation_type: ExtendedRelationType,
        description: str = "",
        evidence_source: str = "",
        evidence_text: str = "",
        confidence: float = 0.7,
    ) -> ExtendedRelationship:
        """Create an ExtendedRelationship with evidence."""
        evidence = Evidence(
            source_document=evidence_source,
            source_text=evidence_text,
            confidence=confidence,
        )
        return ExtendedRelationship(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            description=description,
            evidence=[evidence],
            confidence=confidence,
        )

    @staticmethod
    def _is_valid_entity_name(name: str) -> bool:
        """Return True if the name is a valid entity (not an artifact)."""
        if len(name) < 3:
            return False
        # Reject NaN/None artifacts from spreadsheets
        lower = name.lower()
        if lower in ("nan", "none", "null", "n/a", "na", "--", "-"):
            return False
        if "nan" in lower and len(name) < 30:
            # Allow names that contain nan as part of a real word (e.g. "Nano")
            # but reject "NaN NaN NaN" patterns
            words = lower.split()
            nan_count = sum(1 for w in words if w.strip("\n\r") in ("nan", ""))
            if nan_count > 0 and nan_count / max(len(words), 1) > 0.3:
                return False
        # Reject names with newlines (spreadsheet row artifacts)
        if "\n" in name or "\r" in name:
            return False
        # Reject names that are just numbers/special chars
        stripped = re.sub(r"[^a-zA-Z0-9]", "", name)
        if len(stripped) < 2:
            return False
        return True

    def _extract_by_patterns(
        self,
        patterns: list[re.Pattern],
        entity_type: ExtendedEntityType,
        id_prefix: str,
        text: str,
        evidence_source: str,
    ) -> list[ExtendedEntity]:
        """Extract entities using a list of regex patterns."""
        found: dict[str, ExtendedEntity] = {}

        for pattern in patterns:
            for match in pattern.finditer(text):
                # Get the primary capture group or the full match
                if match.lastindex and match.lastindex >= 1:
                    name = match.group(1).strip()
                else:
                    name = match.group(0).strip()

                # Skip invalid names
                if not self._is_valid_entity_name(name):
                    continue

                entity_id = f"{id_prefix}-{name.upper().replace(' ', '-')[:50]}"

                if entity_id not in found:
                    entity = self._make_entity(
                        entity_id=entity_id,
                        name=name,
                        entity_type=entity_type,
                        description=f"{entity_type.value}: {name}",
                        evidence_source=evidence_source,
                        evidence_text=f"Pattern match: '{match.group(0)[:100]}'",
                        confidence=0.75,
                    )
                    found[entity_id] = entity

        return list(found.values())

    def _extract_incidents(
        self, text: str, document_id: str
    ) -> tuple[list[ExtendedEntity], list[ExtendedRelationship]]:
        """Extract incident entities with RESOLVES relationships."""
        entities: list[ExtendedEntity] = []
        relationships: list[ExtendedRelationship] = []

        found: dict[str, ExtendedEntity] = {}

        for pattern in INCIDENT_PATTERNS:
            for match in pattern.finditer(text):
                if match.lastindex and match.lastindex >= 1:
                    name = match.group(1).strip()
                else:
                    name = match.group(0).strip()

                if not self._is_valid_entity_name(name) or len(name) < 4:
                    continue

                entity_id = f"INC-{name.upper().replace(' ', '-')[:50]}"

                if entity_id not in found:
                    entity = self._make_entity(
                        entity_id=entity_id,
                        name=name,
                        entity_type=ExtendedEntityType.INCIDENT,
                        description=f"Incident/Error: {name}",
                        evidence_source=document_id,
                        evidence_text=f"Incident pattern match: '{match.group(0)[:100]}'",
                        confidence=0.7,
                    )
                    found[entity_id] = entity

        entities = list(found.values())

        # Create RESOLVES relationships (document resolves incident)
        for inc in entities:
            relationships.append(self._make_relationship(
                source_id=f"DOC-{document_id}",
                target_id=inc.id,
                relation_type=ExtendedRelationType.RESOLVES,
                description=f"Document provides resolution for {inc.name}",
                evidence_source=document_id,
                evidence_text=f"Incident '{inc.name}' mentioned with resolution context",
                confidence=0.7,
            ))

        return entities, relationships

    def _extract_client_property(
        self, text: str, document_id: str
    ) -> list[ExtendedEntity]:
        """Extract CLIENT and PROPERTY entities."""
        found: dict[str, ExtendedEntity] = {}

        for pattern in CLIENT_PROPERTY_PATTERNS:
            for match in pattern.finditer(text):
                if match.lastindex and match.lastindex >= 1:
                    name = match.group(1).strip()
                else:
                    name = match.group(0).strip()

                if not self._is_valid_entity_name(name):
                    continue

                # Determine if it's a CLIENT or PROPERTY
                is_property = any(
                    kw in name.lower()
                    for kw in ["property", "hotel", "property id"]
                )
                entity_type = ExtendedEntityType.PROPERTY if is_property else ExtendedEntityType.CLIENT
                prefix = "PROP" if is_property else "CLIENT"

                entity_id = f"{prefix}-{name.upper().replace(' ', '-')[:50]}"

                if entity_id not in found:
                    entity = self._make_entity(
                        entity_id=entity_id,
                        name=name,
                        entity_type=entity_type,
                        description=f"{'Property' if is_property else 'Client'}: {name}",
                        evidence_source=document_id,
                        evidence_text=f"Client/Property pattern match: '{match.group(0)[:100]}'",
                        confidence=0.6,
                    )
                    found[entity_id] = entity

        return list(found.values())

    def _infer_relationships(
        self, entities: list[ExtendedEntity]
    ) -> list[ExtendedRelationship]:
        """
        Infer relationships between entities based on type compatibility.

        Rules:
        - PROCESS → SYSTEM: USES (if they appear in same document)
        - JOB → PROCESS: GENERATED_FROM
        - JOB → SYSTEM: USES
        - INCIDENT → SYSTEM: TRIGGERS (system causes incident)
        - CONFIGURATION → SYSTEM: CONFIGURES
        - PROPERTY → CLIENT: BELONGS_TO
        """
        rels: list[ExtendedRelationship] = []

        entities_by_type: dict[ExtendedEntityType, list[ExtendedEntity]] = {}
        for e in entities:
            entities_by_type.setdefault(e.entity_type, []).append(e)

        processes = entities_by_type.get(ExtendedEntityType.PROCESS, [])
        systems = entities_by_type.get(ExtendedEntityType.SYSTEM, [])
        jobs = entities_by_type.get(ExtendedEntityType.JOB, [])
        incidents = entities_by_type.get(ExtendedEntityType.INCIDENT, [])
        configs = entities_by_type.get(ExtendedEntityType.CONFIGURATION, [])
        properties = entities_by_type.get(ExtendedEntityType.PROPERTY, [])

        # PROCESS → SYSTEM: USES
        for proc in processes:
            for sys in systems:
                rels.append(self._make_relationship(
                    source_id=proc.id,
                    target_id=sys.id,
                    relation_type=ExtendedRelationType.USES,
                    description=f"Process '{proc.name}' uses system '{sys.name}'",
                    evidence_source=proc.evidence[0].source_document if proc.evidence else "",
                    evidence_text=f"Inferred: process and system co-occur",
                    confidence=0.4,
                ))

        # JOB → PROCESS: GENERATED_FROM
        for job in jobs:
            for proc in processes:
                rels.append(self._make_relationship(
                    source_id=job.id,
                    target_id=proc.id,
                    relation_type=ExtendedRelationType.GENERATED_FROM,
                    description=f"Job '{job.name}' generated from process '{proc.name}'",
                    evidence_source=job.evidence[0].source_document if job.evidence else "",
                    evidence_text=f"Inferred: job and process co-occur",
                    confidence=0.35,
                ))

        # JOB → SYSTEM: USES
        for job in jobs:
            for sys in systems:
                rels.append(self._make_relationship(
                    source_id=job.id,
                    target_id=sys.id,
                    relation_type=ExtendedRelationType.USES,
                    description=f"Job '{job.name}' uses system '{sys.name}'",
                    evidence_source=job.evidence[0].source_document if job.evidence else "",
                    evidence_text=f"Inferred: job and system co-occur",
                    confidence=0.4,
                ))

        # INCIDENT → SYSTEM: TRIGGERS
        for inc in incidents:
            for sys in systems:
                rels.append(self._make_relationship(
                    source_id=sys.id,
                    target_id=inc.id,
                    relation_type=ExtendedRelationType.TRIGGERS,
                    description=f"System '{sys.name}' triggers incident '{inc.name}'",
                    evidence_source=inc.evidence[0].source_document if inc.evidence else "",
                    evidence_text=f"Inferred: incident and system co-occur",
                    confidence=0.35,
                ))

        # CONFIGURATION → SYSTEM: CONFIGURES
        for cfg in configs:
            for sys in systems:
                rels.append(self._make_relationship(
                    source_id=cfg.id,
                    target_id=sys.id,
                    relation_type=ExtendedRelationType.CONFIGURES,
                    description=f"Configuration '{cfg.name}' configures system '{sys.name}'",
                    evidence_source=cfg.evidence[0].source_document if cfg.evidence else "",
                    evidence_text=f"Inferred: config and system co-occur",
                    confidence=0.4,
                ))

        return rels

    def _calculate_extraction_confidence(
        self,
        entities: list[ExtendedEntity],
        relationships: list[ExtendedRelationship],
    ) -> float:
        """
        Calculate overall extraction confidence.

        Factors:
        - Number of entities found (more = more thorough)
        - Average entity confidence
        - Average relationship confidence
        - Evidence diversity (multiple sources = higher confidence)
        """
        if not entities:
            return 0.1

        # Entity count signal
        entity_signal = min(len(entities) / 10.0, 0.3)

        # Average entity confidence
        avg_entity_conf = (
            sum(e.average_confidence for e in entities) / len(entities)
            if entities else 0.0
        )

        # Average relationship confidence
        avg_rel_conf = (
            sum(r.confidence for r in relationships) / len(relationships)
            if relationships else 0.0
        )

        # Evidence diversity
        unique_sources = set()
        for e in entities:
            for ev in e.evidence:
                unique_sources.add(ev.source_document)
        diversity_signal = min(len(unique_sources) / 3.0, 0.2)

        # Combined score
        confidence = (
            0.3 * avg_entity_conf
            + 0.3 * avg_rel_conf
            + 0.2 * entity_signal
            + 0.2 * diversity_signal
        )

        return min(max(confidence, 0.0), 1.0)

    def get_cached_entities(self) -> dict[str, ExtendedEntity]:
        """Return all cached entities (for cross-document deduplication)."""
        return self._entity_cache.copy()

    def clear_cache(self) -> None:
        """Clear the entity deduplication cache."""
        self._entity_cache.clear()
