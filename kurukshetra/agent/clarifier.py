"""
Clarification & Follow-Up Generation
=====================================

When confidence is low, SANJAYA asks clarifying questions instead of guessing.
After answering, suggests relevant follow-ups.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class ClarificationRequest:
    """A clarifying question generated when confidence is low."""
    question: str
    options: list[str]  # Suggested answer options
    reason: str  # Why clarification is needed


@dataclass(slots=True)
class FollowUpSuggestion:
    """A follow-up question suggested after an answer."""
    question: str
    relevance: str  # Why this follow-up is relevant
    priority: int  # 1 = most relevant


# -----------------------------------------------------------------------
# Templates for generating clarifications
# -----------------------------------------------------------------------

AMBIGUOUS_PROPERTY_TEMPLATE = (
    "I found information about multiple properties. "
    "Could you specify which property you're referring to?"
)

MULTIPLE_TOPICS_TEMPLATE = (
    "Your question touches on several topics. "
    "Which aspect would you like me to focus on?"
)

VAGUE_QUERY_TEMPLATE = (
    "I want to make sure I give you the most relevant answer. "
    "Could you provide a bit more detail about what you're looking for?"
)

# Follow-up templates based on intent
FOLLOW_UPS_BY_INTENT = {
    "installation": [
        ("What specific integration type are you using?", "HTNG, Opera Agent, OXI, OHIP", 1),
        ("Do you need help with pre-installation checks?", "Verification steps before installation", 2),
        ("Would you like the post-installation verification steps?", "Ensure installation was successful", 3),
    ],
    "troubleshooting": [
        ("What error message are you seeing?", "Specific error details help narrow down the cause", 1),
        ("When did this issue start occurring?", "Timeline helps identify triggering events", 2),
        ("Have you checked the monitoring dashboard?", "Quick health check before deep investigation", 3),
    ],
    "configuration": [
        ("Which property is this configuration for?", "Property-specific configuration details", 1),
        ("Is this a new setup or modification of existing config?", "Different processes for new vs. modified", 2),
        ("Do you need the configuration verification steps?", "Ensure config was applied correctly", 3),
    ],
    "migration": [
        ("What is the source system?", "OXI, HTNG, Opera Agent, etc.", 1),
        ("What is the target system?", "Migration destination", 2),
        ("Do you have a migration timeline?", "Planning considerations", 3),
    ],
    "monitoring": [
        ("Which monitoring dashboard are you using?", "Different dashboards have different capabilities", 1),
        ("Is this a scheduled or ad-hoc investigation?", "Affects the approach and tools", 2),
        ("Do you have the correlation ID?", "Speeds up investigation significantly", 3),
    ],
}


class Clarifier:
    """
    Generates clarifying questions and follow-up suggestions
    for SANJAYA conversations.
    """

    def generate_clarification(
        self,
        query: str,
        confidence: float,
        ambiguous_terms: Optional[list[str]] = None,
    ) -> Optional[ClarificationRequest]:
        """
        Generate a clarifying question if needed.

        Returns None if confidence is high enough.
        """
        if confidence >= 0.85:
            return None

        ambiguous_terms = ambiguous_terms or []

        # Determine clarification type
        if "property" in query.lower() or any(
            term in query.lower() for term in ambiguous_terms
        ):
            return ClarificationRequest(
                question=AMBIGUOUS_PROPERTY_TEMPLATE,
                options=[
                    "Provide the property code (e.g., 'property 3174')",
                    "Provide the hotel name",
                    "Provide the client name",
                ],
                reason="Property reference is ambiguous",
            )

        if confidence < 0.6:
            return ClarificationRequest(
                question=VAGUE_QUERY_TEMPLATE,
                options=[
                    "Be more specific about the product/system",
                    "Mention the specific error or issue",
                    "Specify the team or context",
                ],
                reason=f"Low confidence ({confidence:.2f}) on query interpretation",
            )

        # Check for multiple possible intents
        q = query.lower()
        intent_signals = {
            "installation": ["install", "setup", "add property"],
            "troubleshooting": ["error", "failure", "issue", "problem"],
            "configuration": ["config", "setting", "parameter"],
            "migration": ["migration", "migrate", "switch"],
        }

        detected_intents = [
            intent
            for intent, keywords in intent_signals.items()
            if any(kw in q for kw in keywords)
        ]

        if len(detected_intents) > 1:
            return ClarificationRequest(
                question=MULTIPLE_TOPICS_TEMPLATE,
                options=[f"Focus on {intent}" for intent in detected_intents],
                reason=f"Multiple intents detected: {', '.join(detected_intents)}",
            )

        return None

    def generate_follow_ups(
        self,
        intent: str,
        query: str,
        answer_given: bool = True,
    ) -> list[FollowUpSuggestion]:
        """
        Generate follow-up suggestions based on the answered query.

        Args:
            intent: The detected intent (installation, troubleshooting, etc.)
            query: The original query
            answer_given: Whether an answer was provided

        Returns:
            List of FollowUpSuggestion, sorted by priority
        """
        if not answer_given:
            return []

        # Get template follow-ups for this intent
        template_follow_ups = FOLLOW_UPS_BY_INTENT.get(intent, [])

        suggestions = []
        for question, relevance, priority in template_follow_ups:
            suggestions.append(
                FollowUpSuggestion(
                    question=question,
                    relevance=relevance,
                    priority=priority,
                )
            )

        # Add general follow-ups
        suggestions.extend([
            FollowUpSuggestion(
                question="Would you like me to find related documentation?",
                relevance="Related documents may provide additional context",
                priority=4,
            ),
            FollowUpSuggestion(
                question="Do you need help with anything else on this topic?",
                relevance="Ensure comprehensive coverage of the topic",
                priority=5,
            ),
        ])

        # Sort by priority
        suggestions.sort(key=lambda x: x.priority)

        return suggestions[:4]  # Max 4 suggestions

    def format_clarification(self, clarification: ClarificationRequest) -> str:
        """Format a clarification request for display."""
        lines = [
            "I need a bit more information:",
            "",
            f"  {clarification.question}",
            "",
            "Options:",
        ]
        for i, option in enumerate(clarification.options, 1):
            lines.append(f"  {i}. {option}")

        return "\n".join(lines)

    def format_follow_ups(self, follow_ups: list[FollowUpSuggestion]) -> str:
        """Format follow-up suggestions for display."""
        if not follow_ups:
            return ""

        lines = ["You might also want to know:"]
        for fu in follow_ups:
            lines.append(f"  • {fu.question}")

        return "\n".join(lines)
