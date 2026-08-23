from __future__ import annotations

from .intent import IntentClassifier
from .semantic_intent import SemanticIntentClassifier
from .models import Plan
from .org_map import OrgMap
from .memory import ConversationMemory


class SANJAYAPlanner:
    """
    SANJAYA — the communication orchestrator.

    Upgraded planner that uses:
    - Semantic intent classification (not just keywords)
    - OrgMap for team-aware routing
    - Conversation memory for multi-turn context
    - Clarification when confidence is low
    """

    def __init__(self):
        self.classifier = IntentClassifier()
        self.semantic_classifier = SemanticIntentClassifier()
        self.org_map = OrgMap()
        self.memory = ConversationMemory()

    def create_plan(self, query: str) -> Plan:
        """
        Create an execution plan for the query.

        Uses semantic classification first, falls back to keyword matching.
        Enriches with OrgMap team context.
        """
        # 1. Try semantic classification
        plan = self.semantic_classifier.classify(query)

        # 2. If confidence is low, try keyword-based
        if plan.confidence < 0.75:
            keyword_plan = self.classifier.classify(query)
            if keyword_plan.confidence > plan.confidence:
                plan = keyword_plan

        # 3. Enrich with team context from OrgMap
        team_matches = self.org_map.classify_team_by_keywords(query)
        if team_matches:
            top_team = team_matches[0]
            plan.reason += f" | Team context: {top_team[0].upper()} ({top_team[1]:.2f})"

        # 4. Track in conversation memory
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
