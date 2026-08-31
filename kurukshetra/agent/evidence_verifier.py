"""
Evidence Claim Verifier
=======================

Classifies each factual claim in an answer as:
- DIRECT: explicitly stated in retrieved document text
- INFERRED: derived from relationships/metadata/graph, not directly stated
- UNSUPPORTED: not supported by any retrieved evidence

Design principles:
- No keyword overlap as proof of direct support
- Explicit responsibility/ownership language required for DIRECT
- Metadata-only connections are INFERRED, never presented as DIRECT
- UNSUPPORTED claims are removed or trigger abstention
- Complete provenance for every classification decision
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Responsibility / explicit-support language patterns
# ---------------------------------------------------------------------------

# Patterns that indicate the evidence EXPLICITLY states a relationship.
# These require the evidence text to contain responsibility, ownership,
# definition, or process language — not merely keyword co-occurrence.

_RESPONSIBILITY_PATTERNS = [
    # Ownership / responsibility
    re.compile(r'\b(responsible|owner|owned\s+by|maintained\s+by|managed\s+by)\b', re.I),
    re.compile(r'\b(support\s+team|support\s+group|team\s+responsible|team\s+owner)\b', re.I),
    re.compile(r'\b(primary\s+contact|point\s+of\s+contact|lead|lead\s+team)\b', re.I),
    re.compile(r'\b(department|unit|division)\s+(?:responsible|handles?|manages?|owns?)\b', re.I),
]

# Definition / identity patterns — the evidence defines what something IS
_DEFINITION_PATTERNS = [
    re.compile(r'\b(is\s+a\b|is\s+the\b|refers?\s+to\b|means?\s+that\b|defined\s+as)\b', re.I),
    re.compile(r'\b(stands?\s+for|abbreviation\s+for|acronym\s+for)\b', re.I),
]

# Process / workflow patterns — the evidence describes HOW something works
_PROCESS_PATTERNS = [
    re.compile(r'\b(process\s+for|workflow\s+(?:for|that|involves?)|steps?\s+(?:include|are|involve))\b', re.I),
    re.compile(r'\b(involves?|consists?\s+of|includes?|requires?|triggers?)\b', re.I),
    re.compile(r'\b(configur(?:ation|ed|ing)|setup|installation|deploy(?:ment|ed|ing))\b', re.I),
]

# Association patterns — evidence states a relationship exists
_ASSOCIATION_PATTERNS = [
    re.compile(r'\b(belongs?\s+to|part\s+of|associated\s+with|connected\s+to|integrated\s+with)\b', re.I),
    re.compile(r'\b(uses?|utilizes?|leverages?|relies?\s+on|depends?\s+on)\b', re.I),
    re.compile(r'\b feeds?\s+(?:into|to|from)\b', re.I),
]

_ALL_EXPLICIT_PATTERNS = (
    _RESPONSIBILITY_PATTERNS
    + _DEFINITION_PATTERNS
    + _PROCESS_PATTERNS
    + _ASSOCIATION_PATTERNS
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ClaimVerification:
    """Verification result for a single claim in the answer."""
    claim_text: str
    classification: str  # "DIRECT", "INFERRED", "UNSUPPORTED"
    supporting_evidence_ids: list[str] = field(default_factory=list)  # chunk_ids
    supporting_document_ids: list[str] = field(default_factory=list)
    evidence_type: str = ""  # "textual", "metadata", "graph", "co-occurrence"
    explicit_patterns_found: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class VerificationResult:
    """Complete verification result for an answer."""
    claims: list[ClaimVerification] = field(default_factory=list)
    direct_count: int = 0
    inferred_count: int = 0
    unsupported_count: int = 0
    overall_verdict: str = "PASS"  # "PASS", "PARTIAL", "FAIL"
    adjusted_confidence: float = 0.0
    should_abstain: bool = False
    abstention_reason: str = ""


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

def _split_into_claims(answer: str) -> list[str]:
    """Split an answer into individual factual claims.

    Uses sentence splitting and bullet/list detection.
    Returns claim strings (stripped, non-empty).
    """
    if not answer or not answer.strip():
        return []

    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', answer.strip())

    # Also split on bullet points, numbered items, newlines
    expanded: list[str] = []
    for sent in sentences:
        parts = re.split(r'\n\s*(?:[-•*]\s*|\d+[.)]\s*)', sent)
        for p in parts:
            p = p.strip()
            # Remove common prefixes
            p = re.sub(r'^(?:[-•*]\s*|\d+[.)]\s*)', '', p).strip()
            if p and len(p) > 10:
                expanded.append(p)

    return expanded


def _extract_key_entities(claim: str) -> set[str]:
    """Extract potential entity names from a claim.

    Returns uppercase tokens that look like organizational entities.
    """
    # Common organizational entity patterns
    entity_re = re.compile(
        r'\b(ICS|SPM|ROA|SDOPS|IT|HR|CPM|PMO|NOC|'
        r'G3|RMS|Opera|OHIP|FOLS|SFDC|Demand360|NGI|Optix|'
        r'Salesforce|DataDog|SynXis|CAKE|'
        r'Client\s+Services|Data\s+Feed|Quality|Reporting|'
        r'Installation|Configuration|De-Installation)\b',
        re.I,
    )
    matches = entity_re.findall(claim)
    return {m.upper() for m in matches}


# ---------------------------------------------------------------------------
# EvidenceClaimVerifier
# ---------------------------------------------------------------------------

class EvidenceClaimVerifier:
    """Verifies each factual claim in an answer against retrieved evidence.

    For every claim, determines:
    - DIRECT: evidence text explicitly states the claim
    - INFERRED: supported by metadata/graph/relationships, not direct text
    - UNSUPPORTED: no meaningful support in evidence
    """

    def verify(
        self,
        answer: str,
        evidence: list,
        query: str = "",
    ) -> VerificationResult:
        """
        Verify all claims in the answer.

        Args:
            answer: The answer text to verify
            evidence: List of EvidenceItem objects (from answer_generator)
            query: The original query (for context)

        Returns:
            VerificationResult with per-claim classifications
        """
        claims = _split_into_claims(answer)
        if not claims:
            return VerificationResult(
                overall_verdict="FAIL",
                should_abstain=True,
                abstention_reason="No claims found in answer",
            )

        # Build evidence text index for fast lookup
        evidence_texts = {}
        evidence_docs = {}
        for ev in evidence:
            evidence_texts[ev.chunk_id] = ev.text
            evidence_docs[ev.chunk_id] = ev.document_id

        # Combine all evidence text for broad matching
        all_evidence_text = " ".join(ev.text for ev in evidence).lower()
        all_evidence_tokens = set(all_evidence_text.split())

        # Build metadata index: what entities/teams are in the evidence metadata
        metadata_entities = set()
        for ev in evidence:
            entity = ev.metadata.get("entity", "")
            if entity:
                metadata_entities.add(entity.upper())
            source = ev.metadata.get("source", "")
            if source == "entity_lookup":
                metadata_entities.add(ev.metadata.get("entity", "").upper())

        # Verify each claim
        verifications: list[ClaimVerification] = []
        for claim in claims:
            v = self._verify_single_claim(
                claim, evidence, evidence_texts, evidence_docs,
                all_evidence_text, all_evidence_tokens, metadata_entities,
            )
            verifications.append(v)

        # Compute summary
        direct = sum(1 for v in verifications if v.classification == "DIRECT")
        inferred = sum(1 for v in verifications if v.classification == "INFERRED")
        unsupported = sum(1 for v in verifications if v.classification == "UNSUPPORTED")

        # Overall verdict
        if unsupported > 0 and direct == 0:
            verdict = "FAIL"
            should_abstain = True
            abstention_reason = (
                f"Answer contains {unsupported} unsupported claim(s) "
                f"and no directly supported claims"
            )
        elif unsupported > 0:
            verdict = "PARTIAL"
            should_abstain = False
            abstention_reason = ""
        elif inferred > 0 and direct == 0:
            verdict = "PARTIAL"
            should_abstain = False
            abstention_reason = ""
        else:
            verdict = "PASS"
            should_abstain = False
            abstention_reason = ""

        # Adjusted confidence based on claim verification
        adjusted_confidence = self._calculate_adjusted_confidence(
            direct, inferred, unsupported, len(verifications)
        )

        return VerificationResult(
            claims=verifications,
            direct_count=direct,
            inferred_count=inferred,
            unsupported_count=unsupported,
            overall_verdict=verdict,
            adjusted_confidence=adjusted_confidence,
            should_abstain=should_abstain,
            abstention_reason=abstention_reason,
        )

    def _verify_single_claim(
        self,
        claim: str,
        evidence: list,
        evidence_texts: dict,
        evidence_docs: dict,
        all_evidence_text: str,
        all_evidence_tokens: set,
        metadata_entities: set,
    ) -> ClaimVerification:
        """Verify a single claim against all evidence."""
        claim_lower = claim.lower()
        claim_tokens = set(claim_lower.split())
        claim_entities = _extract_key_entities(claim)

        # --- Step 1: Check for explicit textual support (DIRECT) ---
        supporting_chunks = []
        explicit_patterns = []

        for ev in evidence:
            ev_text_lower = ev.text.lower()

            # Check if the claim's key content is substantially present in this chunk
            # Use content tokens (non-stopword) for matching
            stop_words = {
                "the", "a", "an", "is", "are", "was", "were", "be", "been",
                "being", "have", "has", "had", "do", "does", "did", "will",
                "would", "could", "should", "may", "might", "can", "shall",
                "to", "of", "in", "for", "on", "with", "at", "by", "from",
                "as", "into", "through", "during", "before", "after",
                "and", "or", "but", "not", "no", "nor",
                "this", "that", "these", "those", "it", "its",
                "what", "which", "who", "whom", "where", "when", "why", "how",
            }
            claim_content = claim_tokens - stop_words
            if not claim_content:
                claim_content = claim_tokens

            # Check what fraction of claim content tokens appear in this chunk
            # Strip trailing punctuation for matching ("g3." → "g3")
            def _strip_punct(s: str) -> str:
                return s.strip('.,;:!?"\'()[]{}')
            ev_tokens_clean = {_strip_punct(t) for t in ev_text_lower.split()}
            claim_content_clean = {_strip_punct(t) for t in claim_content}
            found_in_chunk = claim_content_clean & ev_tokens_clean
            coverage = len(found_in_chunk) / len(claim_content_clean) if claim_content_clean else 0
            if coverage < 0.4:
                continue  # Not enough overlap to even consider

            # Now check for EXPLICIT support patterns in the evidence
            patterns_found = []
            for pat in _ALL_EXPLICIT_PATTERNS:
                if pat.search(ev.text):
                    patterns_found.append(pat.pattern)

            # For DIRECT classification, require ALL of:
            # (a) substantial token overlap (claim content is present)
            # (b) explicit support language in the evidence
            # (c) claim's key entities appear in the evidence TEXT (not just metadata)
            # (d) no negation mismatch between claim and evidence
            if coverage >= 0.4 and patterns_found:
                # Check that claim entities appear in the evidence TEXT
                ev_text_lower = ev.text.lower()
                claim_entities_in_text = {
                    ent for ent in claim_entities
                    if ent.lower() in ev_text_lower
                }
                # If claim has entities but NOT ALL appear in evidence text,
                # this cannot be DIRECT (missing entity may only be in metadata)
                missing_entities = claim_entities - claim_entities_in_text
                if missing_entities:
                    continue  # Some entities not in text — skip to INFERRED
                # Check for negation mismatch
                if self._has_negation_mismatch(claim, ev.text):
                    continue  # Claim contradicts evidence
                # Additional check: the explicit pattern should be in the same
                # sentence or nearby context as the claim's key entities
                if self._claim_evidence_aligned(claim, ev.text):
                    supporting_chunks.append(ev.chunk_id)
                    explicit_patterns.extend(patterns_found)

        if supporting_chunks:
            return ClaimVerification(
                claim_text=claim,
                classification="DIRECT",
                supporting_evidence_ids=supporting_chunks,
                supporting_document_ids=list({
                    evidence_docs[cid] for cid in supporting_chunks
                }),
                evidence_type="textual",
                explicit_patterns_found=explicit_patterns,
                confidence=min(0.7 + len(supporting_chunks) * 0.1, 1.0),
                reasoning=f"Found {len(supporting_chunks)} chunk(s) with explicit support language",
            )

        # --- Step 2: Check for metadata/graph support (INFERRED) ---
        # The claim mentions entities that are in the evidence metadata,
        # but the evidence text doesn't explicitly state the relationship
        if claim_entities & metadata_entities:
            return ClaimVerification(
                claim_text=claim,
                classification="INFERRED",
                supporting_evidence_ids=[],
                supporting_document_ids=[],
                evidence_type="metadata",
                explicit_patterns_found=[],
                confidence=0.4,
                reasoning=(
                    f"Claim entities {claim_entities & metadata_entities} found "
                    f"in evidence metadata but not explicitly stated in text"
                ),
            )

        # --- Step 3: Check for broad co-occurrence (INFERRED) ---
        # Key tokens from the claim appear across multiple evidence items
        # but no single item has explicit support language
        claim_content_no_stop = claim_tokens - {
            "the", "a", "an", "is", "are", "was", "were", "what", "which",
            "who", "how", "do", "does", "for", "in", "of", "and", "or",
            "to", "with", "by", "that", "this", "it",
        }
        if claim_content_no_stop:
            cooccur_count = sum(
                1 for tok in claim_content_no_stop
                if tok in all_evidence_tokens
            )
            cooccur_ratio = cooccur_count / len(claim_content_no_stop)
            if cooccur_ratio >= 0.5:
                return ClaimVerification(
                    claim_text=claim,
                    classification="INFERRED",
                    supporting_evidence_ids=[],
                    supporting_document_ids=[],
                    evidence_type="co-occurrence",
                    explicit_patterns_found=[],
                    confidence=0.25,
                    reasoning=(
                        f"Claim tokens co-occur in evidence ({cooccur_ratio:.0%}) "
                        f"but no explicit support language found"
                    ),
                )

        # --- Step 4: No support (UNSUPPORTED) ---
        return ClaimVerification(
            claim_text=claim,
            classification="UNSUPPORTED",
            supporting_evidence_ids=[],
            supporting_document_ids=[],
            evidence_type="none",
            explicit_patterns_found=[],
            confidence=0.0,
            reasoning="No evidence supports this claim",
        )

    def _has_negation_mismatch(self, claim: str, evidence_text: str) -> bool:
        """Check if the evidence contradicts the claim through negation.

        For example:
          claim: 'can be modified without approval'
          evidence: 'requires approval'
        indicates a negation mismatch.
        """
        claim_lower = claim.lower()
        evidence_lower = evidence_text.lower()

        # Negation pairs: if claim says X but evidence says NOT X (or vice versa)
        negation_pairs = [
            (r'without\s+(?:any\s+)?approval', r'requires?.*\bapproval'),
            (r'without\s+(?:any\s+)?approval', r'approval\s+is\s+required'),
            (r'without\s+(?:any\s+)?approval', r'must\s+.*\bapproval'),
            (r'requires?.*\bapproval', r'without\s+(?:any\s+)?approval'),
            (r'no\s+approval', r'approval\s+(?:is\s+)?required'),
            (r'no\s+approval', r'requires?.*\bapproval'),
            (r'can\s+be\s+modified', r'should\s+not\s+be\s+modified'),
            (r'can\s+be\s+modified', r'must\s+not\s+be'),
            (r'anyone\s+can', r'only\s+authorized'),
            (r'any\s+team\s+member', r'only\s+authorized'),
            (r'not\s+required', r'is\s+required'),
            (r'is\s+not\s+required', r'is\s+required'),
            (r'do(?:es)?\s+not\s+require', r'requires?'),
            (r'no\s+restriction', r'restricted'),
            (r'not\s+restricted', r'restricted'),
        ]

        for claim_pat, evidence_pat in negation_pairs:
            if re.search(claim_pat, claim_lower) and re.search(evidence_pat, evidence_lower):
                return True

        return False

    def _claim_evidence_aligned(self, claim: str, evidence_text: str) -> bool:
        """Check that the claim's key entities appear in the same sentence
        or nearby context as explicit support language.

        This prevents false DIRECT classification when the explicit language
        is about a different topic than the claim.
        """
        claim_entities = _extract_key_entities(claim)
        if not claim_entities:
            return True  # No entities to check alignment for

        # Split evidence into sentences
        sentences = re.split(r'(?<=[.!?])\s+', evidence_text)

        for sent in sentences:
            sent_lower = sent.lower()
            # Check if any claim entity appears in this sentence
            entity_in_sentence = any(
                ent.lower() in sent_lower for ent in claim_entities
            )
            if not entity_in_sentence:
                continue

            # Check if explicit support language is in this sentence
            for pat in _ALL_EXPLICIT_PATTERNS:
                if pat.search(sent):
                    return True

        # Also check if entities and patterns are within 2 sentences of each other
        # (allowing for the claim to span a couple of sentences)
        for i, sent in enumerate(sentences):
            sent_lower = sent.lower()
            entity_in_sentence = any(
                ent.lower() in sent_lower for ent in claim_entities
            )
            if not entity_in_sentence:
                continue

            # Check nearby sentences (±2) for explicit patterns
            for j in range(max(0, i - 2), min(len(sentences), i + 3)):
                for pat in _ALL_EXPLICIT_PATTERNS:
                    if pat.search(sentences[j]):
                        return True

        return False

    def _calculate_adjusted_confidence(
        self,
        direct: int,
        inferred: int,
        unsupported: int,
        total: int,
    ) -> float:
        """Calculate adjusted confidence based on claim verification.

        Rules:
        - Each DIRECT claim adds confidence
        - Each INFERRED claim adds less confidence
        - Each UNSUPPORTED claim reduces confidence significantly
        - All UNSUPPORTED = confidence 0
        """
        if total == 0:
            return 0.0
        if unsupported > 0 and direct == 0:
            return 0.0

        # Base confidence from claim types
        direct_score = direct * 0.3
        inferred_score = inferred * 0.1
        unsupported_penalty = unsupported * 0.25

        raw = (direct_score + inferred_score - unsupported_penalty) / max(total, 1)
        # Normalize to 0-1 range
        return max(0.0, min(1.0, raw * 2))
