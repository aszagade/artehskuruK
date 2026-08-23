"""
SEAL Interview
==============

Interactive human-in-the-loop learning session.

Shows pending unknown terms one at a time with evidence.
User may answer, skip, or mark ambiguous.
All answers are stored as human-verified decisions.
"""

from __future__ import annotations

import sys
from typing import Optional

from kurukshetra.services.glossary import GlossaryManager
from kurukshetra.seal.decisions import DecisionStore
from kurukshetra.seal.unknowns import UnknownLoader, UnknownTermWithEvidence


class InterviewSession:
    """Interactive SEAL learning session."""

    def __init__(self) -> None:
        self.loader = UnknownLoader()
        self.decisions = DecisionStore()
        self.glossary = GlossaryManager()
        self._skipped: list[str] = []
        self._answered: list[str] = []
        self._ambiguous: list[str] = []

    def run(self) -> dict:
        """Run the full interview session. Returns session stats."""
        terms = self.loader.load_pending()

        if not terms:
            print("\nNo pending unknown terms. The glossary is up to date.")
            return {"total": 0, "answered": 0, "skipped": 0, "ambiguous": 0}

        print(f"\nSEAL Interview Session")
        print(f"{'=' * 50}")
        print(f"Pending terms: {len(terms)}")
        print(f"Commands: [enter] = define, [s] = skip, [a] = ambiguous, [q] = quit")
        print(f"{'=' * 50}\n")

        for i, term in enumerate(terms):
            print(f"\n--- Term {i + 1}/{len(terms)} ---")
            action = self._show_term(term)

            if action == "quit":
                break
            elif action == "skip":
                self._skipped.append(term.term)
                self.glossary.reject_term(term.term)
            elif action == "ambiguous":
                self._ambiguous.append(term.term)
                # Don't reject — keep as pending for future review
            elif action == "answer":
                self._answered.append(term.term)

        return self._summary()

    def _show_term(self, term: UnknownTermWithEvidence) -> str:
        """Show a single term with evidence. Returns action taken."""
        print(f"\n  TERM: {term.term}")
        print(f"  Category: {term.suggested_category}")
        print(f"  Occurrences: {term.occurrence_count}")
        print(f"  First seen in: {term.first_seen_doc}")

        if term.context_snippet:
            print(f"\n  Context:")
            print(f"    {term.context_snippet[:200]}")

        if term.documents:
            print(f"\n  Found in documents:")
            for doc in term.documents[:3]:
                print(f"    - {doc['title'][:60]}")

        if term.graph_entities:
            print(f"\n  Graph entities:")
            for ent in term.graph_entities[:3]:
                print(f"    - [{ent['type']}] {ent['name']}")

        if term.glossary_similar:
            print(f"\n  Similar glossary terms:")
            for g in term.glossary_similar:
                print(f"    - {g['term']}: {g['definition'][:60]}")

        # Get user input
        print()
        while True:
            try:
                action = input("  [enter definition / s=skip / a=ambiguous / q=quit]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nSession interrupted.")
                return "quit"

            if action.lower() == "q":
                return "quit"
            elif action.lower() == "s":
                return "skip"
            elif action.lower() == "a":
                return "ambiguous"
            elif action == "":
                # Empty = skip
                return "skip"
            else:
                # User typed a definition
                self._store_answer(term, action)
                return "answer"

    def _store_answer(self, term: UnknownTermWithEvidence, definition: str) -> None:
        """Store a human-verified answer."""
        # Add to glossary
        self.glossary.confirm_term(
            term=term.term,
            definition=definition,
            category=term.suggested_category,
        )

        # Record decision
        self.decisions.record(
            term=term.term,
            definition=definition,
            category="glossary",
            source_term=term.term,
            source_documents=[d["id"] for d in term.documents],
            decided_by="developer",
        )

        print(f"  -> Saved: {term.term} = {definition}")

    def _summary(self) -> dict:
        """Print and return session summary."""
        total = len(self._answered) + len(self._skipped) + len(self._ambiguous)
        print(f"\n{'=' * 50}")
        print(f"SESSION COMPLETE")
        print(f"{'=' * 50}")
        print(f"  Answered:  {len(self._answered)}")
        print(f"  Skipped:   {len(self._skipped)}")
        print(f"  Ambiguous: {len(self._ambiguous)}")
        print(f"  Total:     {total}")
        print(f"  Decisions: {self.decisions.count()}")
        print(f"{'=' * 50}")

        if self._answered:
            print(f"\nNew glossary entries:")
            for term in self._answered:
                print(f"  + {term}")

        if self._skipped:
            print(f"\nSkipped (will appear next time):")
            for term in self._skipped:
                print(f"  - {term}")

        return {
            "total": total,
            "answered": len(self._answered),
            "skipped": len(self._skipped),
            "ambiguous": len(self._ambiguous),
        }
