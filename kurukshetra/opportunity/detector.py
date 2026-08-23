"""
Opportunity Detector
====================

Deterministic pattern analysis across enterprise events.

Produces opportunities backed by evidence. Never executes actions.

Detection rules:
  - Automation: repeated identical events from the same system/team
  - Monitoring: systems with high error rates but no monitoring setup
  - Documentation: configurations or processes mentioned without docs
  - Process Improvement: cross-team friction signals
  - Knowledge Gap: queries or topics with no existing documentation
  - Duplicate Work: similar events across different teams
  - Risk Detection: critical errors on production systems
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from typing import Optional

from .models import (
    Event, Opportunity, OpportunityCategory, OpportunityStatus,
    SourceSystem, DetectionResult,
)
from .repository import OpportunityRepository


# Minimum event count to trigger an automation opportunity
AUTOMATION_THRESHOLD = 3
# Minimum frequency for duplicate work detection
DUPLICATE_THRESHOLD = 2
# Confidence floor — below this, don't create an opportunity
MIN_CONFIDENCE = 0.3


class OpportunityDetector:
    """
    Analyzes enterprise events and discovers opportunities.

    All algorithms are deterministic. No LLM calls. No auto-execution.
    """

    def __init__(self, repository: Optional[OpportunityRepository] = None) -> None:
        self.repo = repository or OpportunityRepository()

    def run(self) -> DetectionResult:
        """Run all detection rules against stored events. Returns results."""
        start = time.time()
        events = self.repo.get_events()
        opportunities: list[Opportunity] = []

        opportunities.extend(self._detect_automation(events))
        opportunities.extend(self._detect_monitoring(events))
        opportunities.extend(self._detect_documentation(events))
        opportunities.extend(self._detect_process_improvement(events))
        opportunities.extend(self._detect_knowledge_gap(events))
        opportunities.extend(self._detect_duplicate_work(events))
        opportunities.extend(self._detect_risk(events))

        # Persist
        for opp in opportunities:
            self.repo.upsert_opportunity(opp)

        # Count by category
        categories: dict[str, int] = defaultdict(int)
        for opp in opportunities:
            categories[opp.category.value] += 1

        return DetectionResult(
            opportunities_found=len(opportunities),
            events_analyzed=len(events),
            categories=dict(categories),
            elapsed_seconds=round(time.time() - start, 2),
        )

    # ------------------------------------------------------------------
    # Detection rules
    # ------------------------------------------------------------------

    def _detect_automation(self, events: list[Event]) -> list[Opportunity]:
        """
        Detect repeated identical events that could be automated.

        Signal: same (source, event_type, subject, team) appears 3+ times.
        """
        groups: dict[str, list[Event]] = defaultdict(list)
        for e in events:
            key = f"{e.source.value}|{e.event_type}|{e.subject}|{e.team}"
            groups[key].append(e)

        opps = []
        for key, group in groups.items():
            if len(group) < AUTOMATION_THRESHOLD:
                continue

            confidence = min(0.5 + len(group) * 0.05, 0.95)
            timestamps = [e.timestamp for e in group]
            evidence = (
                f"Event '{group[0].subject}' from {group[0].source.value} "
                f"occurred {len(group)} times for team {group[0].team}. "
                f"First: {min(timestamps)}, Last: {max(timestamps)}. "
                f"Repeated identical events are candidates for automation."
            )

            opps.append(Opportunity(
                opportunity_id=self._make_id("AUTO", key),
                title=f"Automate: {group[0].subject[:60]}",
                category=OpportunityCategory.AUTOMATION,
                source_system=group[0].source,
                affected_team=group[0].team,
                frequency=len(group),
                evidence=evidence,
                confidence=confidence,
                first_seen=min(timestamps),
                last_seen=max(timestamps),
                event_ids=[e.event_id for e in group],
            ))

        return opps

    def _detect_monitoring(self, events: list[Event]) -> list[Opportunity]:
        """
        Detect systems with error events but no monitoring setup.

        Signal: error/alert events exist for a team/system but no
        corresponding monitoring event type.
        """
        error_events = [e for e in events if e.event_type in ("error", "alert", "failure")]
        if not error_events:
            return []

        # Group errors by team
        by_team: dict[str, list[Event]] = defaultdict(list)
        for e in error_events:
            by_team[e.team].append(e)

        # Check if monitoring events exist for same teams
        monitoring_teams = {
            e.team for e in events if e.event_type == "monitoring"
        }

        opps = []
        for team, errs in by_team.items():
            if team in monitoring_teams:
                continue  # Already monitored

            if len(errs) < 2:
                continue

            confidence = min(0.4 + len(errs) * 0.08, 0.9)
            evidence = (
                f"Team {team} has {len(errs)} error/alert events "
                f"but no monitoring events configured. "
                f"Error subjects: {list(set(e.subject for e in errs))[:3]}. "
                f"Adding monitoring would enable proactive incident response."
            )

            opps.append(Opportunity(
                opportunity_id=self._make_id("MON", f"monitor-{team}"),
                title=f"Add monitoring for {team}",
                category=OpportunityCategory.MONITORING,
                source_system=errs[0].source,
                affected_team=team,
                frequency=len(errs),
                evidence=evidence,
                confidence=confidence,
                first_seen=min(e.timestamp for e in errs),
                last_seen=max(e.timestamp for e in errs),
                event_ids=[e.event_id for e in errs],
            ))

        return opps

    def _detect_documentation(self, events: list[Event]) -> list[Opportunity]:
        """
        Detect configurations or processes mentioned without documentation.

        Signal: config/process events exist but no confluence/doc events
        for the same subject.
        """
        config_events = [
            e for e in events
            if e.event_type in ("config_change", "process_update", "deployment")
        ]
        if not config_events:
            return []

        doc_subjects = {
            e.subject.lower() for e in events
            if e.event_type in ("document_update", "wiki_edit")
        }

        opps = []
        for e in config_events:
            if e.subject.lower() in doc_subjects:
                continue

            confidence = 0.5
            evidence = (
                f"'{e.subject}' has a {e.event_type} event from {e.source.value} "
                f"but no corresponding documentation update found. "
                f"Team: {e.team}. Undocumented changes create knowledge drift."
            )

            opps.append(Opportunity(
                opportunity_id=self._make_id("DOC", f"doc-{e.event_id}"),
                title=f"Document: {e.subject[:60]}",
                category=OpportunityCategory.DOCUMENTATION,
                source_system=e.source,
                affected_team=e.team,
                frequency=1,
                evidence=evidence,
                confidence=confidence,
                first_seen=e.timestamp,
                last_seen=e.timestamp,
                event_ids=[e.event_id],
            ))

        return opps

    def _detect_process_improvement(self, events: list[Event]) -> list[Opportunity]:
        """
        Detect cross-team friction signals.

        Signal: events from multiple teams referencing the same subject,
        suggesting handoff friction or unclear ownership.
        """
        by_subject: dict[str, list[Event]] = defaultdict(list)
        for e in events:
            by_subject[e.subject].append(e)

        opps = []
        for subject, group in by_subject.items():
            teams = list(set(e.team for e in group))
            if len(teams) < 2:
                continue

            confidence = min(0.4 + len(teams) * 0.1, 0.85)
            evidence = (
                f"'{subject}' is referenced by {len(teams)} teams: {teams}. "
                f"Cross-team events ({len(group)} total) suggest unclear "
                f"ownership or handoff friction. Consider a shared runbook "
                f"or RACI matrix."
            )

            opps.append(Opportunity(
                opportunity_id=self._make_id("PROC", f"proc-{subject[:30]}"),
                title=f"Improve process: {subject[:60]}",
                category=OpportunityCategory.PROCESS_IMPROVEMENT,
                source_system=SourceSystem.INTERNAL,
                affected_team=", ".join(teams),
                frequency=len(group),
                evidence=evidence,
                confidence=confidence,
                first_seen=min(e.timestamp for e in group),
                last_seen=max(e.timestamp for e in group),
                event_ids=[e.event_id for e in group],
            ))

        return opps

    def _detect_knowledge_gap(self, events: list[Event]) -> list[Opportunity]:
        """
        Detect topics queried but not documented.

        Signal: search/query events with no matching document events.
        """
        query_events = [
            e for e in events
            if e.event_type in ("search", "query", "question")
        ]
        if not query_events:
            return []

        # Group by subject keywords
        by_subject: dict[str, list[Event]] = defaultdict(list)
        for e in query_events:
            by_subject[e.subject].append(e)

        doc_subjects = {
            e.subject.lower() for e in events
            if e.event_type in ("document_update", "wiki_edit", "ingestion")
        }

        opps = []
        for subject, group in by_subject.items():
            if subject.lower() in doc_subjects:
                continue
            if len(group) < 2:
                continue

            confidence = min(0.4 + len(group) * 0.1, 0.85)
            evidence = (
                f"'{subject}' was queried {len(group)} times but no "
                f"corresponding documentation exists. "
                f"Teams: {list(set(e.team for e in group))}. "
                f"This is a knowledge gap that affects multiple users."
            )

            opps.append(Opportunity(
                opportunity_id=self._make_id("KGAP", f"gap-{subject[:30]}"),
                title=f"Create documentation: {subject[:60]}",
                category=OpportunityCategory.KNOWLEDGE_GAP,
                source_system=group[0].source,
                affected_team=", ".join(set(e.team for e in group)),
                frequency=len(group),
                evidence=evidence,
                confidence=confidence,
                first_seen=min(e.timestamp for e in group),
                last_seen=max(e.timestamp for e in group),
                event_ids=[e.event_id for e in group],
            ))

        return opps

    def _detect_duplicate_work(self, events: list[Event]) -> list[Opportunity]:
        """
        Detect similar events across different teams.

        Signal: same event_type and similar subject across 2+ teams.
        """
        by_type: dict[str, list[Event]] = defaultdict(list)
        for e in events:
            by_type[e.event_type].append(e)

        opps = []
        for event_type, group in by_type.items():
            by_subject_key: dict[str, list[Event]] = defaultdict(list)
            for e in group:
                # Normalize subject for comparison
                key = e.subject.lower().strip()[:50]
                by_subject_key[key].append(e)

            for key, sub_group in by_subject_key.items():
                teams = list(set(e.team for e in sub_group))
                if len(teams) < DUPLICATE_THRESHOLD:
                    continue

                confidence = min(0.4 + len(teams) * 0.12, 0.85)
                evidence = (
                    f"Similar {event_type} events ('{sub_group[0].subject[:50]}') "
                    f"occur across teams: {teams}. "
                    f"Total occurrences: {len(sub_group)}. "
                    f"This suggests duplicate work or a shared problem "
                    f"that could be solved once for all teams."
                )

                opps.append(Opportunity(
                    opportunity_id=self._make_id("DUP", f"dup-{key[:30]}"),
                    title=f"Deduplicate: {sub_group[0].subject[:60]}",
                    category=OpportunityCategory.DUPLICATE_WORK,
                    source_system=sub_group[0].source,
                    affected_team=", ".join(teams),
                    frequency=len(sub_group),
                    evidence=evidence,
                    confidence=confidence,
                    first_seen=min(e.timestamp for e in sub_group),
                    last_seen=max(e.timestamp for e in sub_group),
                    event_ids=[e.event_id for e in sub_group],
                ))

        return opps

    def _detect_risk(self, events: list[Event]) -> list[Opportunity]:
        """
        Detect risk patterns: critical errors on production systems.

        Signal: error/failure events with high severity or on critical teams.
        """
        critical_teams = {"sdops", "spm", "ics"}
        risk_events = [
            e for e in events
            if e.event_type in ("error", "failure", "incident", "security")
            and (
                e.team.lower() in critical_teams
                or e.metadata.get("severity") in ("critical", "high")
                or e.quantity > 5
            )
        ]

        if not risk_events:
            return []

        # Group by subject
        by_subject: dict[str, list[Event]] = defaultdict(list)
        for e in risk_events:
            by_subject[e.subject].append(e)

        opps = []
        for subject, group in by_subject.items():
            if len(group) < 2:
                continue

            confidence = min(0.5 + len(group) * 0.1, 0.95)
            severity = "high" if any(
                e.metadata.get("severity") in ("critical", "high") for e in group
            ) else "medium"
            evidence = (
                f"Critical error pattern detected: '{subject}' "
                f"occurred {len(group)} times affecting teams: "
                f"{list(set(e.team for e in group))}. "
                f"Severity: {severity}. "
                f"This pattern indicates a systemic risk that requires "
                f"immediate investigation."
            )

            opps.append(Opportunity(
                opportunity_id=self._make_id("RISK", f"risk-{subject[:30]}"),
                title=f"Risk: {subject[:60]}",
                category=OpportunityCategory.RISK_DETECTION,
                source_system=group[0].source,
                affected_team=", ".join(set(e.team for e in group)),
                frequency=len(group),
                evidence=evidence,
                confidence=confidence,
                first_seen=min(e.timestamp for e in group),
                last_seen=max(e.timestamp for e in group),
                event_ids=[e.event_id for e in group],
                metadata={"severity": severity},
            ))

        return opps

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id(prefix: str, key: str) -> str:
        """Deterministic opportunity ID from prefix + content hash."""
        h = hashlib.md5(key.encode()).hexdigest()[:8]
        return f"OPP-{prefix}-{h}"
