from __future__ import annotations

import re

from .intent import IntentClassifier
from .semantic_intent import SemanticIntentClassifier
from .models import Plan, QueryType, STRATEGY_MAP
from .org_map import OrgMap
from .memory import ConversationMemory


# Query type detection patterns
_WORKFLOW_PATTERNS = re.compile(
    r"\b(how|process|steps|workflow|procedure|workflow|migration|\n"
    r"de-install|install|reinstall|add.*property|remove.*property|\n"
    r"de-install|setup|configure|enable|disable|rollout|deploy)\b",
    re.IGNORECASE,
)
_CONFIG_PATTERNS = re.compile(
    r"\b(configuration|config|setup|settings|parameter|\n"
    r"include|exclude|room.type|str|rpm|edf|demand.?360|\n"
    r"optix|data.feed)\b",
    re.IGNORECASE,
)
_SEMANTIC_PATTERNS = re.compile(
    r"\b(what.*monitoring|how.*resolv|what.*system|\n"
    r"what.*involved|what.*exist|which.*team|\n"
    r"describe|explain|overview)\b",
    re.IGNORECASE,
)
_ACRONYM_PATTERNS = re.compile(
    r"\b(AMS|FOLS|GRO|NGI|OXI|HTNG|STR|RPM|EDF|\n"
    r"G3|G2|SFDC|SSD|OCIM|CPM|ROI|SLA)\b",
)
_INSUFFICIENT_PATTERNS = re.compile(
    r"\b(budget|salary|headcount|cost|price.of|\n"
    r"q[1-4].*campaign|marketing.budget|\n"
    r"employee.count|revenue.forecast)\b",
    re.IGNORECASE,
)
_GRAPH_PATTERNS = re.compile(
    r"\b(system.*involved|relationship|dependency|\n"
    r"connected|linked|related.to|what.*touch)\b",
    re.IGNORECASE,
)


class SANJAYAPlanner:
    """
    SANJAYA — the communication orchestrator.

    Upgraded planner that uses:
    - Semantic intent classification (not just keywords)
    - Query type detection for strategy selection
    - OrgMap for team-aware routing
    - Conversation memory for multi-turn context
    - Clarification when confidence is low
    """

    def __init__(self):
        self.classifier = IntentClassifier()
        self.semantic_classifier = SemanticIntentClassifier()
        self.org_map = OrgMap()
        self.memory = ConversationMemory()

    def classify_query_type(self, query: str) -> str:
        """
        Classify the query type for strategy selection.

        Returns a QueryType value string.
        """
        q = query.lower()

        # Check insufficient evidence first (negative signals)
        if _INSUFFICIENT_PATTERNS.search(q):
            # Only if no G3/RMS/ICS terms present
            if not re.search(r"\b(G3|RMS|ICS|IDeaS|property|hotel|client)\b", q, re.IGNORECASE):
                return QueryType.INSUFFICIENT_EVIDENCE.value

        # Check graph-related
        if _GRAPH_PATTERNS.search(q):
            return QueryType.GRAPH_RELATED.value

        # Check workflow/process
        if _WORKFLOW_PATTERNS.search(q):
            # Distinguish configuration from workflow
            if _CONFIG_PATTERNS.search(q) and not _WORKFLOW_PATTERNS.search(q):
                return QueryType.CONFIGURATION.value
            return QueryType.WORKFLOW.value

        # Check configuration
        if _CONFIG_PATTERNS.search(q):
            return QueryType.CONFIGURATION.value

        # Check semantic
        if _SEMANTIC_PATTERNS.search(q):
            return QueryType.SEMANTIC.value

        # Check acronym
        acronyms = _ACRONYM_PATTERNS.findall(query)  # Case-sensitive
        if acronyms:
            return QueryType.ACRONYM.value

        # Check for cross-document signals
        if re.search(r"\b(all|every|each|across|multiple|different)\b", q):
            return QueryType.CROSS_DOC.value

        # Check for ambiguous signals
        if re.search(r"\b(process|what is|how does)\b", q):
            return QueryType.AMBIGUOUS.value

        return QueryType.EXACT_TERM.value

    def create_plan(self, query: str) -> Plan:
        """
        Create an execution plan for the query.

        Uses semantic classification first, falls back to keyword matching.
        Enriches with OrgMap team context and strategy recommendation.
        """
        # 1. Classify query type for strategy selection
        query_type = self.classify_query_type(query)
        recommended_strategy = STRATEGY_MAP.get(query_type, "hybrid")

        # 2. Try semantic classification
        plan = self.semantic_classifier.classify(query)

        # 3. If confidence is low, try keyword-based
        if plan.confidence < 0.75:
            keyword_plan = self.classifier.classify(query)
            if keyword_plan.confidence > plan.confidence:
                plan = keyword_plan

        # 4. Enrich with query type and strategy
        plan.query_type = query_type
        plan.recommended_strategy = recommended_strategy

        # 5. Enrich with team context from OrgMap
        team_matches = self.org_map.classify_team_by_keywords(query)
        if team_matches:
            top_team = team_matches[0]
            plan.reason += f" | Team context: {top_team[0].upper()} ({top_team[1]:.2f})"

        plan.reason += f" | Query type: {query_type}, Strategy: {recommended_strategy}"

        # 6. Track in conversation memory
        self.memory.add_turn("user", query, {"intent": plan.intent})

        return plan

    def create_plan_with_context(self, query: str) -> Plan:
        """
        Create a plan with conversation context awareness.

        Resolves references like "that property" using conversation history.
        """
        # Extract conversation context
        context = self.memory.extract_context(query)

        # Use resolved query for classification
        resolved_query = context.resolved_query if context.follow_up_detected else query

        plan = self.create_plan(resolved_query)

        # If follow-up detected, boost confidence
        if context.follow_up_detected:
            plan.confidence = min(plan.confidence + 0.05, 0.99)
            plan.reason += " | Follow-up detected"

        # Store response in memory
        self.memory.add_turn("assistant", plan.reason, {"intent": plan.intent})

        return plan
