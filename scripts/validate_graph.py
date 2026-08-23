#!/usr/bin/env python3
"""
Graph Validation CLI
====================

Validates the Knowledge Graph state in DuckDB.

Usage:
    python scripts/validate_graph.py
    python scripts/validate_graph.py --db kurukshetra_registry.duckdb
    python scripts/validate_graph.py --summary
    python scripts/validate_graph.py --extract-sample "G3 RMS uses Opera Agent."
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def validate_database(db_path: str) -> None:
    """Run full graph validation against DuckDB."""
    from kurukshetra.graph.validator import GraphValidator

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        print("Run ingestion first to populate the graph.")
        sys.exit(1)

    print(f"Validating graph: {db_path}")
    print()

    validator = GraphValidator(db_path=db_path)

    # 1. Full graph validation
    print("--- Persisted Graph Validation ---")
    report = validator.validate_persisted_graph()
    print(report.summary())
    print()

    # 2. Per-document validation
    print("--- Per-Document Validation ---")
    doc_report = validator.validate_all_documents()
    print(f"Documents validated: {doc_report.documents_validated}")
    print(f"Orphan entities:     {doc_report.orphan_entities}")
    print(f"Duplicate IDs:       {doc_report.duplicate_ids}")
    print(f"Coverage:            {doc_report.coverage_pct:.1f}%")
    print()

    if doc_report.warnings:
        print(f"Document warnings: {len(doc_report.warnings)}")
        for w in doc_report.warnings[:20]:
            print(f"  ! {w}")
        if len(doc_report.warnings) > 20:
            print(f"  ... and {len(doc_report.warnings) - 20} more")
        print()

    # 3. Graph summary
    print("--- Graph Summary ---")
    summary = validator.get_graph_summary()

    print("Entities by type:")
    for etype, count in sorted(summary["entities_by_type"].items()):
        bar = "#" * min(count, 40)
        print(f"  {etype:20s} {count:5d}  {bar}")

    print()
    print("Relationships by type:")
    for rtype, count in sorted(summary["relationships_by_type"].items()):
        bar = "#" * min(count, 40)
        print(f"  {rtype:20s} {count:5d}  {bar}")

    print()
    print("Confidence distribution:")
    for tier, count in sorted(summary["confidence_distribution"].items()):
        print(f"  {tier:10s} {count:5d}")

    validator.close()


def validate_extraction_sample(text: str) -> None:
    """Validate extraction on a sample text."""
    from kurukshetra.graph.extractor import SmartEntityExtractor
    from kurukshetra.graph.validator import GraphValidator

    print("--- Extraction Validation (sample text) ---")
    print(f"Text length: {len(text)} chars")
    print()

    extractor = SmartEntityExtractor()
    result = extractor.extract_from_document(
        text=text,
        document_id="SAMPLE-001",
        document_title="Sample Document",
        team_id="spm",
    )

    validator = GraphValidator()
    doc_val = validator.validate_extraction(result)

    print(f"Document entity:      {'?' if doc_val.has_document_entity else '?'}")
    print(f"Team relationship:    {'?' if doc_val.has_team_relationship else '?'}")
    print(f"Systems detected:     {doc_val.systems_detected}")
    print(f"Processes detected:   {doc_val.processes_detected}")
    print(f"Jobs detected:        {doc_val.jobs_detected}")
    print(f"Incidents detected:   {doc_val.incidents_detected}")
    print(f"Configs detected:     {doc_val.configs_detected}")
    print(f"Evidence attached:    {'?' if doc_val.evidence_attached else '?'}")
    print(f"Total entities:       {doc_val.entity_count}")
    print(f"Total relationships:  {doc_val.relationship_count}")
    print(f"Extraction confidence: {result.extraction_confidence:.3f}")
    print()

    if doc_val.errors:
        print(f"Errors: {len(doc_val.errors)}")
        for e in doc_val.errors:
            print(f"  ? {e}")
    else:
        print("Errors: 0 ?")


def print_summary_only(db_path: str) -> None:
    """Print summary statistics only."""
    from kurukshetra.graph.registry import GraphRegistry

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    registry = GraphRegistry(db_path=db_path)
    stats = registry.get_stats()

    print(f"Documents:  {stats.get('total_entities', 0)}")
    print(f"Entities:   {stats.get('total_entities', 0)}")
    print(f"Relationships: {stats.get('total_relationships', 0)}")
    print(f"Teams:      {len(stats.get('teams_represented', []))}")
    print(f"Avg confidence: {stats.get('avg_confidence', 0):.4f}")

    registry.close()


def main():
    parser = argparse.ArgumentParser(
        description="KURUKSHETRA Graph Validation CLI",
    )
    parser.add_argument(
        "--db",
        default="kurukshetra_registry.duckdb",
        help="Path to DuckDB database (default: kurukshetra_registry.duckdb)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary statistics only",
    )
    parser.add_argument(
        "--extract-sample",
        type=str,
        default=None,
        help="Validate extraction on sample text",
    )

    args = parser.parse_args()

    if args.extract_sample:
        validate_extraction_sample(args.extract_sample)
    elif args.summary:
        print_summary_only(args.db)
    else:
        validate_database(args.db)


if __name__ == "__main__":
    main()
