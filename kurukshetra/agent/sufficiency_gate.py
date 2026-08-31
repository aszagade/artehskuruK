"""
Evidence Sufficiency Gate
=========================

Deterministic evaluation of whether retrieved evidence actually ANSWERS
the question, not merely mentions the question's keywords.

Architecture:
  Question
    ↓
  Intent Analysis (what is being asked?)
    ↓
  Evidence Answer-Pattern Matching (does evidence contain answer patterns?)
    ↓
  Semantic Relevance (is evidence about the right subtopic?)
    ↓
  Combined Sufficiency Score
    ↓
  SUFFICIENT / PARTIAL / INSUFFICIENT

Design principles:
  - No keyword overlap as sufficiency signal
  - Question-type-specific answer-pattern matching
  - Separates "mentions topic" from "answers question"
  - Deterministic — no LLM calls
  - Bounded latency (< 10ms for typical evidence sets)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
        r"what\s+does\s+\w+\s+mean|what\s+does\s+\w+\s+refer\s+to)\b",
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

    Matches: "X is a...", "X refers to...", "X describes...",
    "X covers...", "X includes...", "X provides...",
    or evidence text that STARTS with the key term (document title/heading)."""
    if not key_terms:
        return None
    terms = "|".join(re.escape(t) for t in key_terms)
    return re.compile(
        rf"(?:"
        rf"\b({terms})\b\s+(?:is|are|refers?|means?|describes?|covers?|"
        rf"includes?|provides?|enables?|allows?|designed|purpose|"
        rf"stands?|abbreviation|acronym)"
        rf"|"  # OR: evidence starts with key term (document title/heading)
        rf"^\s*(?:{terms})\b"
        rf")",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )


def _procedure_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that describes STEPS, PROCESS, or DOCUMENTATION."""
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
        rf"must\s+(?:be|do|have|first)|should\s+(?:be|do|first))"
        rf"|"  # OR: evidence starts with key term + process words
        rf"^\s*(?:{terms})\b.*?(?:process|workflow|steps|guide|procedure|documentation)"
        rf"|"  # OR: key term near process language (within 200 chars)
        rf"(?:process(?:ing|es)?|workflow|steps|guide|procedure|documentation).*?\b({terms})\b"
        rf")",
        re.IGNORECASE | re.DOTALL,
    )


def _count_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that contains a NUMBER answering a count question."""
    # For count questions, we need evidence that has both the thing
    # being counted AND a number
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
        rf"managed\s+by|handled\s+by|managed\s+by|"
        rf"team\s+(?:that|which|responsible|handles|manages|owns)|"
        rf"support\s+team|lead\s+team|primary\s+contact).*?"
        rf"\b({terms})\b|"
        rf"\b({terms})\b.*?"
        rf"(?:responsible\s+for|owner\s+of|owned\s+by|maintained\s+by|"
        rf"managed\s+by|handled\s+by|"
        rf"team\s+(?:that|which|responsible|handles|manages|owns)|"
        rf"support\s+team|lead\s+team|primary\s+contact)",
        re.IGNORECASE | re.DOTALL,
    )


def _specific_value_patterns(key_terms: list[str]) -> re.Pattern | None:
    """Evidence that contains a SPECIFIC VALUE (cost, price, SLA, etc.).

    Requires an actual value (number, currency, or explicit amount),
    not just the topic word 'pricing'.
    """
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
    "refer", "refers", "involved", "involve",
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
# EvidenceSufficiencyGate
# ---------------------------------------------------------------------------

class EvidenceSufficiencyGate:
    """Evaluates whether retrieved evidence actually answers the question.

    Unlike the previous EvidenceSufficiencyChecker which measured keyword
    overlap, this gate:

    1. Detects question intent (definition, procedure, count, etc.)
    2. Checks if evidence contains answer-PATTERNS for that intent
    3. Separates "mentions topic" from "answers question"
    4. Returns SUFFICIENT / PARTIAL / INSUFFICIENT
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

        # Step 5: Evidence quality signals
        evidence_quality = self._check_evidence_quality(evidence)

        # Step 6: Compute combined score
        # Weight: answer patterns (50%) + topical relevance (30%) + quality (20%)
        combined = (
            answer_pattern_match * 0.50
            + topical_relevance * 0.30
            + evidence_quality * 0.20
        )

        # Step 7: Classify
        if combined >= 0.6:
            level = SufficiencyLevel.SUFFICIENT
            should_abstain = False
        elif combined >= 0.35:
            level = SufficiencyLevel.PARTIAL
            should_abstain = False
        else:
            level = SufficiencyLevel.INSUFFICIENT
            should_abstain = True

        # Special case: if answer pattern match is very low, always abstain
        # regardless of other signals (this catches the keyword-only match case)
        if answer_pattern_match < 0.15 and intent != "factual":
            level = SufficiencyLevel.INSUFFICIENT
            should_abstain = True
            combined = min(combined, 0.1)

        # Build reasoning
        reasoning = self._build_reasoning(
            intent, key_terms, answer_pattern_match,
            topical_relevance, evidence_quality, combined, level,
        )

        return SufficiencyResult(
            level=level,
            score=round(combined, 3),
            question_intent=intent,
            answer_pattern_match=round(answer_pattern_match, 3),
            topical_relevance=round(topical_relevance, 3),
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
            # or direct topic discussion
            builder = _ANSWER_PATTERN_BUILDERS.get("definition")
        else:
            builder = _ANSWER_PATTERN_BUILDERS.get(intent)

        if builder is None:
            return 0.5  # Unknown intent — neutral score

        pattern = builder(key_terms)
        if pattern is None:
            # Can't build pattern (e.g., count with no key terms)
            return 0.5

        # Check how many evidence items contain the answer pattern
        matches = 0
        for ev in evidence:
            if pattern.search(ev.text):
                matches += 1

        if not evidence:
            return 0.0

        # Score based on fraction of evidence items matching
        match_ratio = matches / len(evidence)

        # Also check: does the matched evidence actually contain the key terms?
        # (prevents matching generic patterns without topic relevance)
        key_term_str = "|".join(re.escape(t) for t in key_terms) if key_terms else r"\w+"
        topic_pattern = re.compile(
            rf"\b({key_term_str})\b", re.IGNORECASE
        )

        topical_matches = 0
        for ev in evidence:
            if pattern.search(ev.text) and topic_pattern.search(ev.text):
                topical_matches += 1

        # Combined: answer pattern + topic co-occurrence
        if matches == 0:
            return 0.0

        # If patterns match but not with key terms, lower score
        if topical_matches == 0 and key_terms:
            return min(match_ratio * 0.3, 0.3)

        # Check for heading-only matches: evidence starts with key term but
        # doesn't actually define/describe it within 100 chars
        heading_only_matches = 0
        definition_language = re.compile(
            r"(?:is\s+a\b|is\s+the\b|refers?\s+to|means?\s+that|describes?|covers?|"
            r"includes?|provides?|enables?|allows?|designed|purpose|"
            r"stands?|abbreviation|acronym|\bprocess\b|\bworkflow\b|\bsteps\b|\bguide\b|\bprocedure\b)",
            re.IGNORECASE,
        )
        for ev in evidence:
            ev_lower = ev.text.lower().strip()
            for term in key_terms:
                term_lower = term.lower()
                if ev_lower.startswith(term_lower):
                    # Evidence starts with key term — check for definition in first 150 chars
                    head = ev.text[:150]
                    if not definition_language.search(head):
                        heading_only_matches += 1
                        break

        # If most matches are heading-only (no definition language), penalize
        if heading_only_matches > 0 and heading_only_matches == matches:
            return min(match_ratio * 0.3, 0.3)
        elif heading_only_matches > 0:
            # Mix of heading-only and real matches — partial penalty
            real_ratio = (matches - heading_only_matches) / max(matches, 1)
            return min(
                real_ratio * 0.7 + (heading_only_matches / max(matches, 1)) * 0.2 + (topical_matches / max(len(evidence), 1)) * 0.1,
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

        Not just keyword overlap — checks whether the evidence discusses
        the specific aspect the question is asking about.
        """
        if not key_terms or not evidence:
            return 0.0

        # Build a topic-specific check based on question phrasing
        query_lower = query.lower()

        # For definition questions: evidence should define the key terms
        if re.search(r"\bwhat\s+is\b", query_lower, re.IGNORECASE):
            # Check if evidence DEFINES (not just mentions) the key term
            definition_signals = 0
            for ev in evidence:
                ev_lower = ev.text.lower()
                for term in key_terms:
                    term_lower = term.lower()
                    if term_lower in ev_lower:
                        # Check for definition context
                        if re.search(
                            rf"{re.escape(term_lower)}\s+(?:is|are|refers?|means?|stands?|provides?|enables?|allows?|designed|used\s+for)",
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
                    r"must|should|follow|procedure)",
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

        # For count questions: evidence should contain numbers
        if re.search(r"\bhow\s+many\b", query_lower, re.IGNORECASE):
            count_signals = 0
            for ev in evidence:
                if re.search(r"\b\d[\d,]*\b", ev.text):
                    count_signals += 1
            return min(count_signals / max(len(evidence), 1), 1.0)

        # For specific value questions: evidence should contain the value
        if re.search(r"\b(cost|price|pricing|SLA|budget|revenue)\b", query_lower, re.IGNORECASE):
            value_signals = 0
            for ev in evidence:
                ev_lower = ev.text.lower()
                if re.search(
                    r"(?:cost|price|pricing|budget|salary|revenue|"
                    r"SLA|\$\d|USD|EUR|INR|\d+[\d,]*\s*(?:hours|days|weeks|months))",
                    ev_lower,
                ):
                    value_signals += 1
            return min(value_signals / max(len(evidence), 1), 1.0)

        # Aspect-specific check: when the question asks about a specific attribute
        # (language, cost, SLA, etc.), evidence must contain that attribute
        _ASPECT_KEYWORDS = {
            "programming": ["programming language", "source code", "implemented in", "written in", "built with", "java", "python", "c++", "javascript", "typescript"],
            "language": ["programming language", "source code", "implemented in", "written in", "built with"],
            "cost": ["cost", "price", "budget", "expense", r"\$", "USD"],
            "price": ["cost", "price", "budget", r"\$", "USD"],
            "sla": ["sla", "turnaround", "response time", "resolution time"],
            "revenue": ["revenue", "income", "earnings", r"\$", "million", "billion"],
            "headcount": ["employees", "headcount", "staff", "workforce"]
        }
        query_lower_for_aspect = query.lower()
        for aspect_key, aspect_words in _ASPECT_KEYWORDS.items():
            if aspect_key in query_lower_for_aspect:
                # Check if evidence contains the aspect keywords
                aspect_hits = 0
                for ev in evidence:
                    ev_lower = ev.text.lower()
                    if any(aw in ev_lower for aw in aspect_words):
                        aspect_hits += 1
                if aspect_hits == 0:
                    # Evidence mentions topic but not the specific aspect
                    return 0.0
                return min(aspect_hits / max(len(evidence), 1), 1.0)

        # Generic: check how many evidence items contain key terms
        term_hits = 0
        for ev in evidence:
            ev_lower = ev.text.lower()
            hits = sum(1 for t in key_terms if t.lower() in ev_lower)
            if hits >= len(key_terms) * 0.5:
                term_hits += 1

        return min(term_hits / max(len(evidence), 1), 1.0)

    def _check_evidence_quality(self, evidence: list) -> float:
        """Check basic evidence quality signals.

        Not keyword overlap — just structural quality:
        - Enough evidence items
        - Multiple source documents
        - Reasonable text length (not empty/garbage)
        """
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
        parts.append(f"evidence_quality={evidence_quality:.2f}")
        parts.append(f"combined={combined:.2f}")

        if level == SufficiencyLevel.INSUFFICIENT:
            if answer_pattern_match < 0.15:
                parts.append("→ Evidence mentions topic but does not answer the question")
            elif topical_relevance < 0.2:
                parts.append("→ Evidence is not about the specific subtopic asked")
            else:
                parts.append("→ Insufficient answer-pattern match for this question type")
        elif level == SufficiencyLevel.PARTIAL:
            parts.append("→ Some evidence addresses the question, but coverage is incomplete")
        else:
            parts.append("→ Evidence contains answer patterns for this question type")

        return "; ".join(parts)
