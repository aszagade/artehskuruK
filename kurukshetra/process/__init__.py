"""Process Intelligence — deterministic process extraction and analysis."""
from .intelligence import (
    ProcessExtractor,
    ProcessGapDetector,
    ProcessDefinition,
    ProcessStep,
    ProcessGap,
    ensure_process_tables,
    persist_process,
    persist_gaps,
    get_process,
    list_processes,
    get_process_stats,
)
