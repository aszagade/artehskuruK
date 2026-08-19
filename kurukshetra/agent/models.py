from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tool(Enum):
    KNOWLEDGE = "knowledge"
    SQL = "sql"
    DATADOG = "datadog"
    SMARTSHEET = "smartsheet"
    GENERAL = "general"


@dataclass(slots=True)
class Plan:
    intent: str
    tool: Tool
    confidence: float
    reason: str