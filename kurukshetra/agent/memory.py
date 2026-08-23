"""
SANJAYA Conversation Memory
===========================

Enables multi-turn conversations with context tracking:
- Reference resolution ("that property" → previous property code)
- Follow-up query understanding
- Session-based memory with configurable TTL
- Topic tracking across turns
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class ConversationTurn:
    """A single turn in the conversation."""
    turn_id: int
    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ConversationContext:
    """Extracted context from conversation history."""
    last_topic: str
    last_property_code: Optional[str]
    last_action: Optional[str]
    mentioned_entities: list[str]
    follow_up_detected: bool
    original_query: str
    resolved_query: str


# Patterns for detecting follow-ups and references
FOLLOW_UP_PATTERNS = [
    re.compile(r"^(?:and|also|what about|how about|tell me about)\s+", re.IGNORECASE),
    re.compile(r"^(?:the\s+)?(?:same|that|this|those)\s+", re.IGNORECASE),
    re.compile(r"^(?:more|details|again|elaborate)\s*$", re.IGNORECASE),
]

PROPERTY_CODE_PATTERN = re.compile(r"\b(?:property|code|hotel)\s*(?:code)?\s*[:=]?\s*(\w{3,10})\b", re.IGNORECASE)

ENTITY_PATTERNS = [
    re.compile(r"\b(G3|RMS|Opera|NGI|OXI|OHIP|FOLS|TARS|Hilton|Accor|Hyatt|Marriott|MGM)\b", re.IGNORECASE),
]


class ConversationMemory:
    """
    Manages multi-turn conversation state for SANJAYA.

    Tracks conversation history and provides context for
    understanding follow-up queries.
    """

    def __init__(self, max_turns: int = 20, ttl_seconds: int = 3600) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self.session_start = time.time()
        self.turn_counter = 0

    @property
    def is_expired(self) -> bool:
        """Check if the session has expired."""
        return (time.time() - self.session_start) > self.ttl_seconds

    def add_turn(
        self,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> ConversationTurn:
        """Add a new turn to the conversation."""
        self.turn_counter += 1
        turn = ConversationTurn(
            turn_id=self.turn_counter,
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self.turns.append(turn)
        return turn

    def get_recent_turns(self, n: int = 5) -> list[ConversationTurn]:
        """Get the most recent N turns."""
        return list(self.turns)[-n:]

    def extract_context(self, query: str) -> ConversationContext:
        """
        Extract conversation context from history to help understand
        the current query.
        """
        last_topic = ""
        last_property_code = None
        last_action = None
        mentioned_entities: list[str] = []
        follow_up_detected = False

        # Check if this is a follow-up query
        for pattern in FOLLOW_UP_PATTERNS:
            if pattern.match(query):
                follow_up_detected = True
                break

        # Analyze recent turns for context
        recent = self.get_recent_turns(5)

        for turn in reversed(recent):
            if turn.role == "user":
                # Extract property code from last user message
                if last_property_code is None:
                    prop_match = PROPERTY_CODE_PATTERN.search(turn.content)
                    if prop_match:
                        last_property_code = prop_match.group(1)

                # Extract entities
                for pattern in ENTITY_PATTERNS:
                    for match in pattern.finditer(turn.content):
                        entity = match.group(1)
                        if entity not in mentioned_entities:
                            mentioned_entities.append(entity)

            elif turn.role == "assistant":
                # Extract last topic from assistant response
                if not last_topic and turn.content:
                    # Use first sentence as topic
                    first_sentence = turn.content.split(".")[0][:100]
                    last_topic = first_sentence

                # Extract last action from metadata
                if not last_action and "intent" in turn.metadata:
                    last_action = turn.metadata["intent"]

        # Resolve references in query
        resolved = self._resolve_references(query, recent)

        return ConversationContext(
            last_topic=last_topic,
            last_property_code=last_property_code,
            last_action=last_action,
            mentioned_entities=mentioned_entities,
            follow_up_detected=follow_up_detected,
            original_query=query,
            resolved_query=resolved,
        )

    def _resolve_references(
        self, query: str, recent_turns: list[ConversationTurn]
    ) -> str:
        """
        Resolve references like "that property", "same thing", etc.
        using conversation history.
        """
        resolved = query

        # "that property" or "same property" → use last property code
        if re.search(r"\b(?:that|this|same)\s+property\b", query, re.IGNORECASE):
            for turn in reversed(recent_turns):
                prop_match = PROPERTY_CODE_PATTERN.search(turn.content)
                if prop_match:
                    resolved = re.sub(
                        r"\b(?:that|this|same)\s+property\b",
                        f"property {prop_match.group(1)}",
                        resolved,
                        flags=re.IGNORECASE,
                    )
                    break

        # "the same thing" or "again" → append context from last query
        if re.search(r"\b(?:same thing|again|more details)\b", query, re.IGNORECASE):
            for turn in reversed(recent_turns):
                if turn.role == "user":
                    # Prepend context from last user query
                    last_query_words = turn.content.split()
                    if len(last_query_words) > 3:
                        context = " ".join(last_query_words[:5])
                        resolved = f"{context} {resolved}"
                    break

        return resolved

    def get_conversation_summary(self) -> str:
        """Generate a summary of the conversation."""
        if not self.turns:
            return "No conversation history."

        turns = list(self.turns)
        topics = []
        entities = set()

        for turn in turns:
            for pattern in ENTITY_PATTERNS:
                for match in pattern.finditer(turn.content):
                    entities.add(match.group(1))

        return (
            f"Conversation: {len(turns)} turns. "
            f"Entities mentioned: {', '.join(sorted(entities)) if entities else 'none'}. "
            f"Duration: {int(time.time() - self.session_start)}s."
        )

    def reset(self) -> None:
        """Reset the conversation memory."""
        self.turns.clear()
        self.session_start = time.time()
        self.turn_counter = 0
