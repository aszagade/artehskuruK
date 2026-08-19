from __future__ import annotations

from .models import Plan, Tool


class IntentClassifier:
    """
    SANJAYA Intent Classifier

    Priority matters:
    1. Smartsheet
    2. Datadog
    3. SQL
    4. Knowledge
    """

    def classify(self, query: str) -> Plan:
        q = query.lower()

        # ==================================================
        # SMARTSHEET (highest priority)
        # ==================================================
        if any(word in q for word in [
            "smartsheet",
            "tracker",
            "update tracker",
            "review status",
            "current state",
            "assign reviewer",
            "change state",
            "ready predv",
        ]):
            return Plan(
                intent="tracker_update",
                tool=Tool.SMARTSHEET,
                confidence=0.99,
                reason="Smartsheet tracker operation detected.",
            )

        # ==================================================
        # DATADOG
        # ==================================================
        if any(word in q for word in [
            "datadog",
            "correlation id",
            "tracking id",
            "failure stage",
            "configurepropertyinfds",
            "logs",
            "rollout failed",
            "investigate rollout",
        ]):
            return Plan(
                intent="rollout_investigation",
                tool=Tool.DATADOG,
                confidence=0.98,
                reason="Datadog log investigation detected.",
            )

        # ==================================================
        # SQL / PROPERTY LOOKUP
        # ==================================================
        if any(word in q for word in [
            "property code",
            "client code",
            "hotel",
            "order number",
            "property 3174",
            "find property",
        ]):
            return Plan(
                intent="property_lookup",
                tool=Tool.SQL,
                confidence=0.95,
                reason="Property lookup detected.",
            )

        # ==================================================
        # DEFAULT → KNOWLEDGE RAG
        # ==================================================
        return Plan(
            intent="knowledge_search",
            tool=Tool.KNOWLEDGE,
            confidence=0.90,
            reason="General SOP / documentation query.",
        )