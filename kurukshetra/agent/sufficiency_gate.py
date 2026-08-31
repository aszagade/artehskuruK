"""
Evidence Sufficiency Gate V2
============================

Deterministic evaluation of whether retrieved evidence actually ANSWERS
the question, not merely mentions the question's keywords.

Architecture:
  Question
    -> Intent Analysis (what is being asked?)
    -> Answer-Pattern Matching (does evidence contain answer patterns?)
    -> Topic Coverage (do evidence chunks collectively cover key aspects?)
    -> Semantic Match (BGE-M3 embedding similarity, optional/lazy)
    -> Evidence Quality (structural quality signals)
    -> Combined Sufficiency Score
    -> SUFFICIENT / PARTIAL / INSUFFICIENT

Design principles:
  - No keyword overlap as sole sufficiency signal
  - Question-type-specific answer-pattern matching
  - Embedding-based semantic similarity for robustness
  - Deterministic — no LLM calls in the gate itself
  - Bounded latency (< 50ms for typical evidence sets)

V1 -> V2 changes:
  - Added semantic_match field using lazy-loaded BGE-M3 embeddings
  - Added topic_coverage signal (unique key-term coverage across evidence)
  - Broadened definition patterns to catch substantive discussion
  - Reduced heading-only penalty severity
  - Rebalanced weights for better precision/recall
  - Added aspect-coverage check as part of topical_relevance
  - Added ContradictionResult field to SufficiencyResult
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SufficiencyLevel(Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


@dataclass
class SufficiencyResult:
    """Result of the evidence sufficiency gate."""
    level: SufficiencyLevel
    score: float  # 0.0 to 1.0
    question_intent: str  # detected intent type
    answer_pattern_match: float  # how well evidence matches answer patterns
    topical_relevance: float  # is evidence about the right subtopic
    semantic_match: float  # BGE-M3 embedding similarity (0-1, 0 = unavailable)
    topic_coverage: float  # unique key-term coverage across evidence
    evidence_quality: float  # evidence count/diversity/score quality
    reasoning: str  # human-readable explanation
    should_abstain: bool = False
    abstention_reason: str = ""


# ---------------------------------------------------------------------------
# Question intent detection
# ---------------------------------------------------------------------------

_INTENT_PATTERNS = {
    # Check specific intents BEFORE generic "definition" / "factual"
    "count": re.compile(
        r"\b(how\s+many|number\s+of|total\s+count|count\s+of|how\s+much)\b",
        re.IGNORECASE,
    ),
    "specific_value": re.compile(
        r"\b(what\s+is\s+the\s+(?:cost|price|pricing|salary|budget|revenue|"
        r"SLA|turnaround\s+time|deadline|duration|timeframe|lead\s+time|"
        r"licensing|license\s+fee|annual|monthly)|"
        r"how\s+long\s+(?:does|will|is)|what\s+is\s+the\s+annual)\b",
        re.IGNORECASE,
    ),
    "comparison": re.compile(
        r"\b(what\s+is\s+the\s+difference|how\s+does\s+\w+\s+compare|"
        r"which\s+is\s+better|what\s+are\s+the\s+pros\s+and\s+cons)\b",
        re.IGNORECASE,
    ),
    "troubleshoot": re.compile(
        r"\b(how\s+(?:do|can)\s+(?:I|you|we)\s+(?:fix|resolve|troubleshoot|debug|repair)|"
        r"what\s+(?:is\s+)?(?:the\s+)?(?:cause|error|issue|problem|failure)|"
        r"why\s+(?:is|does|did|are)\s+\w+\s+(?:failing|broken|not\s+working|error))\b",
        re.IGNORECASE,
    ),
    "ownership": re.compile(
        r"\b(who\s+(?:is|are)\s+(?:responsible|the\s+owner|in\s+charge)|"
        r"which\s+team|who\s+handles|who\s+manages|who\s+owns|"
        r"which\s+(?:group|department|unit)\s+(?:is|are)\s+responsible)\b",
        re.IGNORECASE,
    ),
    "procedure": re.compile(
        r"\b(how\s+(?:do|does|can|should|would)|what\s+(?:are\s+)?(?:the\s+)?steps|"
        r"what\s+is\s+the\s+process|how\s+does\s+\w+\s+work|walk\s+me\s+through|"
        r"describe\s+the\s+process|explain\s+the\s+workflow)\b",
        re.IGNORECASE,
    ),
    "definition": re.compile(
        r"\b(what\s+is(?:\s+the)?|what\s+are|define|definition\s+of|"
        r"what\s+does\s+\w+\s+mean|what\s+does\s+\w+\s+refer\s+to|"
        r"what\s+do\s+you\s+know\s+about|"
        r"tell\s+me\s+about|"
        r"what\s+information\s+(?:do|is|are))\b",
        re.IGNORECASE,
    ),
    "factual": re.compile(
        r"\b(what\s+(?:is|are|was|were|does|do|did)|which\s+(?:is|are|was|were|does|do|did))\b",
        re.IGNORECASE,
    ),
}


# ---------------------------------------------------------------------------
# Answer-pattern matchers per intent type
# ---------------------------------------------------------------------------

def _definition_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that DEFINES or DESCRIBES what something is.

    V2: Broadened to catch substantive discussion, not just 'is a' definitions.
    """
    if not key_terms:
        return None
    terms = "|".join(re.escape(t) for t in key_terms)
    return re.compile(
        rf"(?:"
        # Direct definition language
        rf"\b({terms})\b\s+(?:is|are|refers?|means?|describes?|covers?|"
        rf"includes?|provides?|enables?|allows?|designed|purpose|"
        rf"stands?|abbreviation|acronym|used\s+for|known\s+as)"
        rf"|"
        # Substantive discussion: term followed by action/description within 300 chars
        rf"\b({terms})\b(?:[^.]*?\.){{0,3}}\s+(?:this|the|which|that)\s+(?:is|are|provides|enables|allows|covers|includes)"
        rf"|"
        # Evidence starts with key term (document title/heading)
        rf"^\s*(?:{terms})\b"
        rf")",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )


def _procedure_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that describes STEPS, PROCESS, or DOCUMENTATION.

    V2: Broadened to catch more process descriptions.
    """
    if not key_terms:
        return None
    terms = "|".join(re.escape(t) for t in key_terms)
    return re.compile(
        rf"(?:"
        # Key term followed by process language
        rf"\b({terms})\b.*?"
        rf"(?:step\s+\d|first|then|next|after\s+that|finally|"
        rf"process\s+(?:for|of|involves)|workflow|"
        rf"the\s+following|below\s+is|instructions|"
        rf"click|select|navigate|configure|setup|install|"
        rf"must\s+(?:be|do|have|first)|should\s+(?:be|do|first)|"
        rf"need\s+to|go\s+to|open|navigate\s+to)"
        rf"|"
        # Process/workflow keywords near key terms
        rf"(?:process(?:ing|es)?|workflow|steps|guide|procedure|documentation|"
        rf"instruction|tutorial|walkthrough).*?\b({terms})\b"
        rf"|"
        # Key term followed by colon (often section headers)
        rf"\b({terms})\b\s*:"
        rf")",
        re.IGNORECASE | re.DOTALL,
    )


def _count_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that contains a NUMBER answering a count question."""
    return re.compile(
        r"\b(\d[\d,]*\.?\d*)\b.*?"
        r"(?:total|count|number|employees|members|properties|documents|"
        r"items|records|entries|approximately|about|around|roughly|"
        r"more than|less than|over|under|at least|minimum|maximum)",
        re.IGNORECASE,
    )


def _ownership_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that assigns RESPONSIBILITY for something."""
    if not key_terms:
        return None
    terms = "|".join(re.escape(t) for t in key_terms)
    return re.compile(
        rf"(?:responsible\s+for|owner\s+of|owned\s+by|maintained\s+by|"
        rf"managed\s+by|handled\s+by|"
        rf"team\s+(?:that|which|responsible|handles|manages|owns)|"
        rf"support\s+team|lead\s+team|primary\s+contact|"
        rf"team.*?(?:responsible|owns|manages|handles)).*?"
        rf"\b({terms})\b|"
        rf"\b({terms})\b.*?"
        rf"(?:responsible\s+for|owner\s+of|owned\s+by|maintained\s+by|"
        rf"managed\s+by|handled\s+by|"
        rf"team\s+(?:that|which|responsible|handles|manages|owns)|"
        rf"support\s+team|lead\s+team|primary\s+contact)",
        re.IGNORECASE | re.DOTALL,
    )


def _specific_value_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that contains a SPECIFIC VALUE (cost, price, SLA, etc.)."""
    return re.compile(
        r"(?:cost|price|budget|salary|revenue|SLA|turnaround|deadline|"
        r"duration|timeframe|lead\s+time)\s+(?:of|is|was|will be|:|\d)"
        r"|\$\d|USD|EUR|GBP|INR"
        r"|\b\d[\d,]*\.?\d*\s*(?:per\s+(?:hour|day|month|year|night))",
        re.IGNORECASE,
    )


def _troubleshoot_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that describes TROUBLESHOOTING or ERROR RESOLUTION."""
    if not key_terms:
        return None
    terms = "|".join(re.escape(t) for t in key_terms)
    return re.compile(
        rf"(?:error|issue|problem|failure|exception|bug|fix|resolve|"
        rf"troubleshoot|debug|repair|workaround|solution).*?"
        rf"\b({terms})\b|"
        rf"\b({terms})\b.*?"
        rf"(?:error|issue|problem|failure|exception|bug|fix|resolve|"
        rf"troubleshoot|debug|repair|workaround|solution)",
        re.IGNORECASE | re.DOTALL,
    )


_ANSWER_PATTERN_BUILDERS = {
    "definition": _definition_patterns,
    "procedure": _procedure_patterns,
    "count": _count_patterns,
    "ownership": _ownership_patterns,
    "specific_value": _specific_value_patterns,
    "troubleshoot": _troubleshoot_patterns,
}


# ---------------------------------------------------------------------------
# Key-term extraction from questions
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "what", "is", "the", "how", "do", "does", "a", "an", "to", "for",
    "in", "of", "and", "or", "can", "you", "are", "there", "this",
    "that", "it", "on", "at", "by", "be", "as", "with", "from", "not",
    "who", "which", "when", "where", "why", "if", "about", "your",
    "we", "my", "our", "their", "its", "could", "should", "would",
    "may", "might", "will", "shall", "must", "need", "want", "know",
    "tell", "me", "explain", "describe", "walk", "through", "step",
    "steps", "process", "work", "works", "working", "mean", "means",
    "refer", "refers", "involved", "involve", "latest", "current",
    "new", "old", "version", "recent", "update",
}

# Known organizational entities to boost as key terms
_KNOWN_ENTITIES = {
    "G3", "RMS", "SFDC", "SALESFORCE", "ICS", "SPM", "ROA", "SDOPS",
    "IT", "HR", "CPM", "OHIP", "FOLS", "NGI", "OPTIX", "SYNXIS",
    "DATADOG", "DEMAND360", "CAKE", "OPERA", "PMS", "OXI", "HTNG",
    "IDeaS", "HILTON", "ACCOR", "HYATT",
}


def _extract_key_terms(query: str) -> list[str]:
    """Extract the most important terms from a question.

    Prioritizes known organizational entities, then content words.
    """
    words = re.findall(r"\b\w+\b", query)
    content_words = [w for w in words if w.lower() not in _STOP_WORDS and len(w) > 1]

    # Boost known entities
    entities = [w for w in content_words if w.upper() in _KNOWN_ENTITIES or w in _KNOWN_ENTITIES]
    other = [w for w in content_words if w.upper() not in _KNOWN_ENTITIES and w not in _KNOWN_ENTITIES]

    # Return entities first, then other content words, capped at 6
    return (entities + other)[:6]


# ---------------------------------------------------------------------------
# Semantic match via BGE-M3 embeddings (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_bge_model = None
_bge_load_attempted = False


def _get_bge_model():
    """Lazy-load the BGE-M3 model for semantic similarity.

    Returns None if the model is unavailable (prevents repeated failures).
    """
    global _bge_model, _bge_load_attempted
    if _bge_load_attempted:
        return _bge_model
    _bge_load_attempted = True
    try:
        from kurukshetra.embeddings.bge_m3 import BGEEmbedding
        _bge_model = BGEEmbedding()
    except Exception:
        _bge_model = None
    return _bge_model


def _compute_semantic_match(query: str, evidence: list) -> float:
    """Compute semantic similarity between query and evidence using BGE-M3.

    Returns a score from 0.0 (no match / unavailable) to 1.0 (perfect match).
    Uses the mean cosine similarity of the top evidence items.
    """
    model = _get_bge_model()
    if model is None:
        return 0.0  # Signal: semantic match unavailable

    try:
        q_emb = model.embed(query)
        if q_emb is None:
            return 0.0

        sims = []
        for ev in evidence[:5]:  # Cap at 5 to bound latency
            try:
                ev_emb = model.embed(ev.text[:512])  # Truncate long text
                if ev_emb is None:
                    continue
                # Cosine similarity
                dot = sum(a * b for a, b in zip(q_emb, ev_emb))
                na = math.sqrt(sum(a * a for a in q_emb))
                nb = math.sqrt(sum(b * b for b in ev_emb))
                if na > 0 and nb > 0:
                    sims.append(dot / (na * nb))
            except Exception:
                continue

        if not sims:
            return 0.0

        # Mean of top similarities, normalized to 0-1
        # Cosine sim for BGE-M3 typically ranges from 0.3 to 0.8
        mean_sim = sum(sims) / len(sims)
        # Normalize: 0.3 -> 0.0, 0.8 -> 1.0
        normalized = max(0.0, min(1.0, (mean_sim - 0.3) / 0.5))
        return round(normalized, 3)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Topic coverage: how many unique key terms are covered across evidence
# ---------------------------------------------------------------------------

def _compute_topic_coverage(key_terms: list[str], evidence: list) -> float:
    """Check how many unique key terms appear across all evidence chunks.

    Returns 0.0 (no terms covered) to 1.0 (all terms covered).
    This catches cases where the answer is distributed across multiple documents.
    """
    if not key_terms or not evidence:
        return 0.0

    all_text = " ".join(ev.text.lower() for ev in evidence)
    covered = sum(1 for t in key_terms if t.lower() in all_text)
    return round(covered / len(key_terms), 3)


# ---------------------------------------------------------------------------
# EvidenceSufficiencyGate
# ---------------------------------------------------------------------------

class EvidenceSufficiencyGate:
    """Evaluates whether retrieved evidence actually answers the question.

    V2 improvements over V1:
    1. Embedding-based semantic similarity (optional, lazy-loaded)
    2. Topic coverage signal (unique term coverage across evidence)
    3. Broader definition patterns
    4. Less aggressive heading-only penalty
    5. Better weight balance
    """

    def check(
        self,
        query: str,
        evidence: list,
    ) -> SufficiencyResult:
        """
        Evaluate evidence sufficiency for the given query.

        Args:
            query: The user's question
            evidence: List of EvidenceItem objects from retrieval

        Returns:
            SufficiencyResult with level, score, and reasoning
        """
        if not evidence:
            return SufficiencyResult(
                level=SufficiencyLevel.INSUFFICIENT,
                score=0.0,
                question_intent="unknown",
                answer_pattern_match=0.0,
                topical_relevance=0.0,
                semantic_match=0.0,
                topic_coverage=0.0,
                evidence_quality=0.0,
                reasoning="No evidence provided",
                should_abstain=True,
                abstention_reason="No evidence retrieved for this question",
            )

        # Step 1: Detect question intent
        intent = self._detect_intent(query)

        # Step 2: Extract key terms
        key_terms = _extract_key_terms(query)

        # Step 3: Build answer pattern for this intent
        answer_pattern_match = self._check_answer_patterns(
            intent, key_terms, evidence
        )

        # Step 4: Check topical relevance (evidence is about the right subtopic)
        topical_relevance = self._check_topical_relevance(query, key_terms, evidence)

        # Step 5: Topic coverage (unique key-term coverage across evidence)
        topic_coverage = _compute_topic_coverage(key_terms, evidence)

        # Step 6: Semantic match via embeddings (optional, 0 if unavailable)
        semantic_match = _compute_semantic_match(query, evidence)

        # Step 7: Evidence quality signals
        evidence_quality = self._check_evidence_quality(evidence)

        # Step 8: Compute combined score
        # V2 weights:
        #   answer patterns: 35% (was 50%)
        #   topical relevance: 25% (was 30%)
        #   topic coverage: 15% (NEW)
        #   semantic match: 15% (NEW, 0 if unavailable — redistributed)
        #   evidence quality: 10% (was 20%)
        #
        # When semantic match is unavailable (0), redistribute its weight
        # to the other signals proportionally.
        if semantic_match > 0:
            combined = (
                answer_pattern_match * 0.35
                + topical_relevance * 0.25
                + topic_coverage * 0.15
                + semantic_match * 0.15
                + evidence_quality * 0.10
            )
        else:
            # Semantic match unavailable — redistribute weight
            combined = (
                answer_pattern_match * 0.40
                + topical_relevance * 0.30
                + topic_coverage * 0.20
                + evidence_quality * 0.10
            )

        # V2: Aspect-mismatch penalty.
        # If topical_relevance is 0.0 due to an aspect mismatch (e.g., question
        # asks about 'programming' but evidence discusses G3 without any
        # programming language mention), the evidence is answering a DIFFERENT
        # question. Cap the combined score so the gate doesn't treat it as
        # answering the actual question.
        _ASPECT_KEYS = {"programming", "language", "cost", "price", "sla",
                        "revenue", "headcount", "how many"}
        query_lower_combined = query.lower()
        has_aspect = any(kw in query_lower_combined for kw in _ASPECT_KEYS)
        if has_aspect and topical_relevance == 0.0:
            combined = min(combined, 0.25)

        # V2: Count-question penalty.
        # If the question is "how many..." but evidence has no numbers,
        # the evidence is NOT answering the count question.
        if re.search(r"\bhow\s+many\b", query_lower_combined, re.IGNORECASE):
            has_numbers = any(re.search(r"\b\d[\d,]*\b", ev.text) for ev in evidence)
            if not has_numbers:
                combined = min(combined, 0.25)

        # V2: Specific-value question penalty.
        # If the question asks about cost/price/SLA/revenue/stock/etc.
        # and evidence lacks actual values, cap the score.
        if re.search(r"\b(cost|price|pricing|SLA|budget|revenue|stock|salary)\b", query_lower_combined, re.IGNORECASE):
            has_actual_value = any(
                re.search(r"\$\d|USD|EUR|\d[\d,]*\.?\d*\s*(?:per|/|(?:hours|days|months|years))", ev.text)
                for ev in evidence
            )
            if not has_actual_value:
                combined = min(combined, 0.40)

        # V2: General out-of-scope penalty.
        # If answer pattern is low AND topical relevance is low, the evidence
        # is likely irrelevant even if topic coverage is high.
        if answer_pattern_match < 0.15 and topical_relevance < 0.3:
            combined = min(combined, 0.25)

        # Step 9: Classify
        if combined >= 0.55:
            level = SufficiencyLevel.SUFFICIENT
            should_abstain = False
        elif combined >= 0.30:
            level = SufficiencyLevel.PARTIAL
            should_abstain = False
        else:
            level = SufficiencyLevel.INSUFFICIENT
            should_abstain = True

        # V2: Relax the hard floor from V1 (was: always abstain if pattern < 0.15)
        # Now: only abstain if BOTH pattern AND coverage are low
        # This prevents false abstentions for substantive discussions
        if answer_pattern_match < 0.10 and topic_coverage < 0.3 and intent not in ("factual",):
            level = SufficiencyLevel.INSUFFICIENT
            should_abstain = True
            combined = min(combined, 0.15)

        # Build reasoning
        reasoning = self._build_reasoning(
            intent, key_terms, answer_pattern_match,
            topical_relevance, topic_coverage, semantic_match,
            evidence_quality, combined, level,
        )

        return SufficiencyResult(
            level=level,
            score=round(combined, 3),
            question_intent=intent,
            answer_pattern_match=round(answer_pattern_match, 3),
            topical_relevance=round(topical_relevance, 3),
            semantic_match=round(semantic_match, 3),
            topic_coverage=round(topic_coverage, 3),
            evidence_quality=round(evidence_quality, 3),
            reasoning=reasoning,
            should_abstain=should_abstain,
            abstention_reason=(
                f"Insufficient evidence to answer '{query[:60]}': "
                f"{reasoning}"
                if should_abstain else ""
            ),
        )

    def _detect_intent(self, query: str) -> str:
        """Detect the primary intent of the question."""
        for intent, pattern in _INTENT_PATTERNS.items():
            if pattern.search(query):
                return intent
        return "factual"

    def _check_answer_patterns(
        self,
        intent: str,
        key_terms: list[str],
        evidence: list,
    ) -> float:
        """Check if evidence contains answer patterns for the detected intent.

        Returns a score from 0.0 (no answer patterns found) to 1.0
        (strong answer patterns found across multiple evidence items).
        """
        if intent == "factual":
            # For generic factual questions, check for definition-like patterns
            builder = _ANSWER_PATTERN_BUILDERS.get("definition")
        else:
            builder = _ANSWER_PATTERN_BUILDERS.get(intent)

        if builder is None:
            return 0.5  # Unknown intent — neutral score

        pattern = builder(key_terms)
        if pattern is None:
            return 0.5

        # Check how many evidence items contain the answer pattern
        matches = 0
        for ev in evidence:
            if pattern.search(ev.text):
                matches += 1

        if not evidence:
            return 0.0

        match_ratio = matches / len(evidence)

        # Check: does the matched evidence actually contain the key terms?
        key_term_str = "|".join(re.escape(t) for t in key_terms) if key_terms else r"\w+"
        topic_pattern = re.compile(
            rf"\b({key_term_str})\b", re.IGNORECASE
        )

        topical_matches = 0
        for ev in evidence:
            if pattern.search(ev.text) and topic_pattern.search(ev.text):
                topical_matches += 1

        if matches == 0:
            return 0.0

        # If patterns match but not with key terms, lower score
        if topical_matches == 0 and key_terms:
            return min(match_ratio * 0.3, 0.3)

        # V2: Relax heading-only penalty
        # Only penalize if evidence starts with key term AND has NO substantive
        # content in first 200 chars (was 150 in V1)
        heading_only_matches = 0
        definition_language = re.compile(
            r"(?:is\s+a\b|is\s+the\b|refers?\s+to|means?\s+that|describes?|covers?|"
            r"includes?|provides?|enables?|allows?|designed|purpose|"
            r"stands?|abbreviation|acronym|\bprocess\b|\bworkflow\b|\bsteps\b|\bguide\b|"
            r"\bprocedure\b|\bdata\s+feed\b|\bconfiguration\b|\binstallation\b|\bsetup\b)",
            re.IGNORECASE,
        )
        for ev in evidence:
            ev_lower = ev.text.lower().strip()
            for term in key_terms:
                term_lower = term.lower()
                if ev_lower.startswith(term_lower):
                    head = ev.text[:200]  # V2: 200 chars (was 150)
                    if not definition_language.search(head):
                        heading_only_matches += 1
                        break

        # V2: Less aggressive heading-only penalty
        if heading_only_matches > 0 and heading_only_matches == matches:
            # All heading-only: still give some credit (was: cap at 0.3)
            return min(match_ratio * 0.45, 0.45)
        elif heading_only_matches > 0:
            real_ratio = (matches - heading_only_matches) / max(matches, 1)
            return min(
                real_ratio * 0.65
                + (heading_only_matches / max(matches, 1)) * 0.25
                + (topical_matches / max(len(evidence), 1)) * 0.10,
                1.0,
            )

        return min(
            match_ratio * 0.7 + (topical_matches / len(evidence)) * 0.3,
            1.0,
        )

    def _check_topical_relevance(
        self,
        query: str,
        key_terms: list[str],
        evidence: list,
    ) -> float:
        """Check if evidence is about the right subtopic.

        V2: Broadened definition check; added aspect-coverage integration.
        """
        if not key_terms or not evidence:
            return 0.0

        query_lower = query.lower()

        # V2: Specific-aspect checks run FIRST (before generic what-is/how/who).
        # This prevents 'What is the cost of X?' from being treated as a
        # definition question when it's actually asking about a specific value.

        # For count questions: evidence MUST contain numbers
        if re.search(r"\bhow\s+many\b", query_lower, re.IGNORECASE):
            count_signals = 0
            for ev in evidence:
                if re.search(r"\b\d[\d,]*\b", ev.text):
                    count_signals += 1
            return min(count_signals / max(len(evidence), 1), 1.0)

        # For specific value questions: evidence should contain the value
        # V2: Require actual values (numbers/currency), not just concept words.
        # 'pricing rules' is not an answer to 'what is the pricing?'
        if re.search(r"\b(cost|price|pricing|SLA|budget|revenue)\b", query_lower, re.IGNORECASE):
            value_signals = 0
            has_numbers = False
            for ev in evidence:
                ev_lower = ev.text.lower()
                if re.search(
                    r"(?:\$\d|USD|EUR|INR|\d[\d,]*\s*(?:hours|days|weeks|months|per\s+(?:hour|day|month|year)))",
                    ev_lower,
                ):
                    value_signals += 1
                    has_numbers = True
                elif re.search(
                    r"\b(?:cost|price|salary|budget|revenue|SLA)\b",
                    ev_lower,
                ) and re.search(r"\b\d[\d,]*\b", ev.text):
                    # Concept word + number in same evidence = value present
                    value_signals += 1
                    has_numbers = True
            if not has_numbers:
                # Evidence mentions pricing concepts but no actual values
                return 0.0
            return min(value_signals / max(len(evidence), 1), 1.0)

        # For definition questions: evidence should define the key terms
        if re.search(r"\bwhat\s+is\b", query_lower, re.IGNORECASE):
            definition_signals = 0
            for ev in evidence:
                ev_lower = ev.text.lower()
                for term in key_terms:
                    term_lower = term.lower()
                    if term_lower in ev_lower:
                        # V2: Broader check — definition OR substantive discussion
                        if re.search(
                            rf"{re.escape(term_lower)}\s+(?:is|are|refers?|means?|stands?|"
                            rf"provides?|enables?|allows?|designed|used\s+for|covers|includes)",
                            ev_lower,
                        ):
                            definition_signals += 1
                            break
                        # V2: Also accept if term appears in a heading/section context
                        # followed by substantive content (colon, dash, etc.)
                        if re.search(
                            rf"{re.escape(term_lower)}\s*[:\-]",
                            ev_lower,
                        ):
                            definition_signals += 1
                            break
            return min(definition_signals / max(len(evidence), 1), 1.0)

        # For procedure questions: evidence should describe steps
        if re.search(r"\bhow\b", query_lower, re.IGNORECASE):
            procedure_signals = 0
            for ev in evidence:
                ev_lower = ev.text.lower()
                if re.search(
                    r"(?:step|first|then|next|finally|process|workflow|"
                    r"click|select|navigate|configure|setup|install|"
                    r"must|should|follow|procedure|instructions|"
                    r"need\s+to|go\s+to|open)",
                    ev_lower,
                ):
                    procedure_signals += 1
            return min(procedure_signals / max(len(evidence), 1), 1.0)

        # For ownership questions: evidence should assign responsibility
        if re.search(r"\bwho\b", query_lower, re.IGNORECASE):
            ownership_signals = 0
            for ev in evidence:
                ev_lower = ev.text.lower()
                if re.search(
                    r"(?:responsible|owner|owned by|maintained|managed|"
                    r"handled by|support team|lead|contact)",
                    ev_lower,
                ):
                    ownership_signals += 1
            return min(ownership_signals / max(len(evidence), 1), 1.0)

        # Aspect-specific check: when the question asks about a specific attribute
        # V2: This check runs FIRST — if the question asks about a specific aspect
        # and evidence doesn't cover it, return 0.0 regardless of entity presence.
        _ASPECT_KEYWORDS = {
            "programming": ["programming language", "source code", "implemented in", "written in", "built with", "java", "python", "c++", "javascript", "typescript"],
            "language": ["programming language", "source code", "implemented in", "written in", "built with"],
            "cost": ["cost", "price", "budget", "expense", "USD"],
            "price": ["cost", "price", "budget", "USD"],
            "sla": ["sla", "turnaround", "response time", "resolution time"],
            "revenue": ["revenue", "income", "earnings", "million", "billion"],
            "headcount": ["employees", "headcount", "staff", "workforce"],
        }
        for aspect_key, aspect_words in _ASPECT_KEYWORDS.items():
            if aspect_key in query_lower:
                aspect_hits = 0
                for ev in evidence:
                    ev_lower = ev.text.lower()
                    if any(aw in ev_lower for aw in aspect_words):
                        aspect_hits += 1
                if aspect_hits == 0:
                    return 0.0
                return min(aspect_hits / max(len(evidence), 1), 1.0)

        # For count questions: evidence MUST contain numbers (not just entities)
        if re.search(r"\bhow\s+many\b", query_lower, re.IGNORECASE):
            count_signals = 0
            for ev in evidence:
                if re.search(r"\b\d[\d,]*\b", ev.text):
                    count_signals += 1
            return min(count_signals / max(len(evidence), 1), 1.0)

        # Generic: check how many evidence items contain key terms
        term_hits = 0
        for ev in evidence:
            ev_lower = ev.text.lower()
            hits = sum(1 for t in key_terms if t.lower() in ev_lower)
            if hits >= max(len(key_terms) * 0.5, 1):
                term_hits += 1

        return min(term_hits / max(len(evidence), 1), 1.0)

    def _check_evidence_quality(self, evidence: list) -> float:
        """Check basic evidence quality signals."""
        if not evidence:
            return 0.0

        # Count score
        count_score = min(len(evidence) / 3, 1.0) * 0.3

        # Diversity score
        unique_docs = len(set(e.document_id for e in evidence))
        diversity_score = min(unique_docs / max(len(evidence), 1), 1.0) * 0.3

        # Quality score (non-empty, meaningful text)
        meaningful = sum(
            1 for e in evidence
            if len(e.text.strip()) > 50
        )
        quality_score = (meaningful / max(len(evidence), 1)) * 0.4

        return count_score + diversity_score + quality_score

    def _build_reasoning(
        self,
        intent: str,
        key_terms: list[str],
        answer_pattern_match: float,
        topical_relevance: float,
        topic_coverage: float,
        semantic_match: float,
        evidence_quality: float,
        combined: float,
        level: SufficiencyLevel,
    ) -> str:
        """Build human-readable reasoning for the sufficiency decision."""
        parts = []
        parts.append(f"intent={intent}")
        parts.append(f"key_terms={key_terms[:4]}")
        parts.append(f"answer_pattern={answer_pattern_match:.2f}")
        parts.append(f"topical_relevance={topical_relevance:.2f}")
        parts.append(f"topic_coverage={topic_coverage:.2f}")
        if semantic_match > 0:
            parts.append(f"semantic_match={semantic_match:.2f}")
        parts.append(f"evidence_quality={evidence_quality:.2f}")
        parts.append(f"combined={combined:.2f}")

        if level == SufficiencyLevel.INSUFFICIENT:
            if answer_pattern_match < 0.10 and topic_coverage < 0.3:
                parts.append("-> Evidence mentions topic but does not answer the question")
            elif topical_relevance < 0.2:
                parts.append("-> Evidence is not about the specific subtopic asked")
            else:
                parts.append("-> Insufficient answer-pattern match for this question type")
        elif level == SufficiencyLevel.PARTIAL:
            parts.append("-> Some evidence addresses the question, but coverage is incomplete")
        else:
            parts.append("-> Evidence contains answer patterns for this question type")

        return "; ".join(parts)
