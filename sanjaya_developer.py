#!/usr/bin/env python3
"""
SANJAYA Developer CLI
=====================

Interactive SEAL learning session.

Loads pending unknown terms, shows them one at a time with evidence,
and stores human-verified answers as glossary entries and decisions.

Usage:
    python sanjaya_developer.py
    python sanjaya_developer.py --stats
    python sanjaya_developer.py --term "CP-Admin"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from kurukshetra.seal.interview import InterviewSession
from kurukshetra.seal.unknowns import UnknownLoader
from kurukshetra.seal.decisions import DecisionStore
from kurukshetra.services.glossary import GlossaryManager


def cmd_interactive() -> None:
    """Run interactive interview session."""
    session = InterviewSession()
    session.run()


def cmd_stats() -> None:
    """Show SEAL and glossary statistics."""
    glossary = GlossaryManager()
    decisions = DecisionStore()
    loader = UnknownLoader()

    stats = glossary.get_glossary_stats()
    pending = loader.count_pending()
    total_decisions = decisions.count()

    print("=" * 50)
    print("SEAL STATISTICS")
    print("=" * 50)
    print(f"  Glossary terms:     {stats['total_terms']}")
    print(f"  Confirmed terms:    {stats['confirmed_terms']}")
    print(f"  Pending unknowns:   {pending}")
    print(f"  Decisions stored:   {total_decisions}")
    print("=" * 50)


def cmd_term(term: str) -> None:
    """Show details for a specific unknown term."""
    loader = UnknownLoader()
    term_data = loader.load_one(term)

    if term_data is None:
        print(f"Term '{term}' not found in unknown terms.")
        return

    print(f"\nTERM: {term_data.term}")
    print(f"Category: {term_data.suggested_category}")
    print(f"Occurrences: {term_data.occurrence_count}")
    print(f"Status: {term_data.status}")
    print(f"First seen: {term_data.first_seen_doc}")

    if term_data.context_snippet:
        print(f"\nContext:\n  {term_data.context_snippet[:300]}")

    if term_data.documents:
        print(f"\nDocuments:")
        for doc in term_data.documents:
            print(f"  - [{doc['id']}] {doc['title'][:60]}")

    if term_data.graph_entities:
        print(f"\nGraph entities:")
        for ent in term_data.graph_entities:
            print(f"  - [{ent['type']}] {ent['name']} ({ent['id']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="SANJAYA Developer CLI — SEAL Learning")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--term", type=str, help="Show details for a specific term")
    args = parser.parse_args()

    if args.stats:
        cmd_stats()
    elif args.term:
        cmd_term(args.term)
    else:
        cmd_interactive()


if __name__ == "__main__":
    main()
