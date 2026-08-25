from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tool(Enum):
    KNOWLEDGE = "knowledge"
    SQL = "sql"
    DATADOG = "datadog"
    SMARTSHEET = "smartsheet"
    GENERAL = "general"


class QueryType(Enum):
    EXACT_TERM = "exact_term"
    SEMANTIC = "semantic"
    WORKFLOW = "workflow"
    CONFIGURATION = "configuration"
    ACRONYM = "acronym"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CROSS_DOC = "cross_doc"
    GRAPH_RELATED = "graph_related"


# Strategy selection rules: query_type -> recommended strategy
STRATEGY_MAP: dict[str, str] = {
    QueryType.EXACT_TERM.value: "bm25",
    QueryType.ACRONYM.value: "hybrid",
    QueryType.WORKFLOW.value: "hybrid",
    QueryType.CONFIGURATION.value: "hybrid",
    QueryType.SEMANTIC.value: "vector",
    QueryType.AMBIGUOUS.value: "hybrid",
    QueryType.CROSS_DOC.value: "hybrid",
    QueryType.GRAPH_RELATED.value: "graph_aug",
    QueryType.INSUFFICIENT_EVIDENCE.value: "none",
}


@dataclass(slots=True)
class Plan:
    intent: str
    tool: Tool
    confidence: float
    reason: str
    query_type: str = QueryType.EXACT_TERM.value
    recommended_strategy: str = "hybrid"