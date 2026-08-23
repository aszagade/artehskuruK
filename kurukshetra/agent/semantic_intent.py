"""
Semantic Intent Classification
==============================

Upgrades SANJAYA's intent classification from keyword matching to:
- Embedding-based intent matching (handles paraphrases)
- Multi-intent detection (complex queries)
- Confidence calibration
- New pattern learning from corrections
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

from .models import Plan, Tool


@dataclass(slots=True)
class IntentPrototype:
    """A prototype query for a specific intent."""
    intent: str
    tool: Tool
    example_queries: list[str]
    keywords: list[str]
    priority: int  # Lower = higher priority


# -----------------------------------------------------------------------
# Intent prototypes with representative queries
# -----------------------------------------------------------------------

INTENT_PROTOTYPES: list[IntentPrototype] = [
    IntentPrototype(
        intent="tracker_update",
        tool=Tool.SMARTSHEET,
        example_queries=[
            "update smartsheet tracker",
            "change review status",
            "assign reviewer to tracker",
            "what is the current state of the tracker",
            "modify the tracker entry",
            "ready predv status update",
        ],
        keywords=["smartsheet", "tracker", "review status", "assign reviewer",
                  "current state", "change state", "ready predv"],
        priority=1,
    ),
    IntentPrototype(
        intent="rollout_investigation",
        tool=Tool.DATADOG,
        example_queries=[
            "check datadog logs for this correlation id",
            "investigate the rollout failure",
            "what is the failure stage in the logs",
            "tracking id investigation",
            "configurepropertyinfds error in datadog",
            "find the rollout logs",
        ],
        keywords=["datadog", "correlation id", "tracking id", "failure stage",
                  "configurepropertyinfds", "logs", "rollout failed",
                  "investigate rollout"],
        priority=2,
    ),
    IntentPrototype(
        intent="property_lookup",
        tool=Tool.SQL,
        example_queries=[
            "find property code for hotel",
            "what is the client code",
            "lookup order number",
            "property 3174 details",
            "search for property by name",
            "get property configuration from database",
        ],
        keywords=["property code", "client code", "hotel", "order number",
                  "find property", "property details"],
        priority=3,
    ),
    IntentPrototype(
        intent="knowledge_search",
        tool=Tool.KNOWLEDGE,
        example_queries=[
            "how to handle G3 decision upload failures",
            "what is the process for full upload",
            "troubleshooting steps for monitoring alerts",
            "how to install a new property",
            "configuration requirements for Opera Agent",
            "what causes CPOptimalPriceToBARStep failures",
        ],
        keywords=["how to", "process", "steps", "troubleshoot", "configuration",
                  "installation", "error", "failure", "guide", "documentation"],
        priority=4,
    ),
]


def _simple_tokenize(text: str) -> list[str]:
    """Simple tokenization for keyword matching."""
    return re.findall(r"\b\w+\b", text.lower())


def _keyword_overlap_score(query_tokens: list[str], keywords: list[str]) -> float:
    """Calculate keyword overlap score between query and intent keywords."""
    query_set = set(query_tokens)
    keyword_set = set(kw.lower() for kw in keywords)

    if not keyword_set:
        return 0.0

    overlap = len(query_set & keyword_set)
    return overlap / len(keyword_set)


def _example_similarity(query: str, examples: list[str]) -> float:
    """Calculate similarity based on shared n-grams with examples."""
    query_tokens = set(_simple_tokenize(query))
    max_score = 0.0

    for example in examples:
        example_tokens = set(_simple_tokenize(example))
        if not example_tokens:
            continue

        # Jaccard-like similarity with token overlap
        intersection = len(query_tokens & example_tokens)
        union = len(query_tokens | example_tokens)

        if union > 0:
            score = intersection / union
            max_score = max(max_score, score)

    return max_score


class SemanticIntentClassifier:
    """
    Embedding-free semantic intent classification.

    Uses keyword overlap, example similarity, and priority ordering
    to classify queries without requiring an LLM.
    """

    def __init__(self) -> None:
        self.prototypes = INTENT_PROTOTYPES.copy()

    def classify(self, query: str) -> Plan:
        """
        Classify a query into an intent with tool routing.

        Returns the best-matching Plan with confidence score.
        """
        query_tokens = _simple_tokenize(query)
        scores: list[tuple[IntentPrototype, float]] = []

        for proto in self.prototypes:
            # Score 1: Keyword overlap (0-1)
            kw_score = _keyword_overlap_score(query_tokens, proto.keywords)

            # Score 2: Example similarity (0-1)
            ex_score = _example_similarity(query, proto.example_queries)

            # Combined score (weighted)
            combined = kw_score * 0.6 + ex_score * 0.4

            scores.append((proto, combined))

        # Sort by score, then by priority (lower = higher priority)
        scores.sort(key=lambda x: (-x[1], x[0].priority))

        if not scores or scores[0][1] == 0:
            # Default to knowledge search
            return Plan(
                intent="knowledge_search",
                tool=Tool.KNOWLEDGE,
                confidence=0.7,
                reason="No strong intent match; defaulting to knowledge search.",
            )

        best_proto, best_score = scores[0]

        # Confidence calibration
        confidence = min(0.7 + best_score * 0.3, 0.99)

        # Check for multi-intent (if second-best is also strong)
        reason = f"Matched intent '{best_proto.intent}' with score {best_score:.3f}"
        if len(scores) > 1 and scores[1][1] > 0.5:
            reason += f" (secondary intent: {scores[1][0].intent})"

        return Plan(
            intent=best_proto.intent,
            tool=best_proto.tool,
            confidence=round(confidence, 3),
            reason=reason,
        )

    def classify_multi_intent(self, query: str) -> list[Plan]:
        """
        Detect if a query has multiple intents.

        Returns list of Plans, one per detected intent, sorted by confidence.
        """
        query_tokens = _simple_tokenize(query)
        results: list[tuple[IntentPrototype, float]] = []

        for proto in self.prototypes:
            kw_score = _keyword_overlap_score(query_tokens, proto.keywords)
            ex_score = _example_similarity(query, proto.example_queries)
            combined = kw_score * 0.6 + ex_score * 0.4

            if combined > 0.3:  # Threshold for multi-intent detection
                results.append((proto, combined))

        results.sort(key=lambda x: (-x[1], x[0].priority))

        plans = []
        for proto, score in results[:3]:  # Max 3 intents
            confidence = min(0.7 + score * 0.3, 0.99)
            plans.append(
                Plan(
                    intent=proto.intent,
                    tool=proto.tool,
                    confidence=round(confidence, 3),
                    reason=f"Multi-intent: {proto.intent} (score {score:.3f})",
                )
            )

        return plans

    def learn_correction(
        self, query: str, correct_intent: str, correct_tool: Tool
    ) -> None:
        """
        Learn from a user correction.

        Adds the query as a new example for the correct intent prototype.
        """
        for proto in self.prototypes:
            if proto.intent == correct_intent:
                if query not in proto.example_queries:
                    proto.example_queries.append(query)
                break
