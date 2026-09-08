"""
Agent Extraction Adapter
==========================

SourceAdapter for "agent email extraction" SQL Server databases — CareAgent
and ICSAgent today, and any future team database of the same shape.

Design goal: adding a new team/database, a new table generation, or a
schema change to an existing table should NEVER require a new file or a
code change here — only a new (or edited) config dict, registered via
kurukshetra/sources/persistent_registry.py. See `load_registered_adapters()`
at the bottom of this file and scripts/register_agent_extraction_sources.py
for how a config becomes a running source.

One adapter INSTANCE = one (server, database) = one team. Each instance can
cover multiple table "generations" (e.g. a frozen legacy table plus an
actively-growing V3 table) — that's expressed entirely in config, not in
subclasses.

Config shape (all non-secret; credentials always come from
AGENT_DB_USER / AGENT_DB_PASSWORD environment variables, never from here):

    {
        "source_id": "care-email-extraction",       # required, stable
        "display_name": "Care Agent Email Extraction",
        "server": "172.26.122.106",
        "database": "CareAgent",
        "team": "care",                              # SourceDocument.team_ids tag
        "team_owner": "Support",                      # CLAUDE.md ownership enum value
        "default_visibility": "Internal",
        "tables": [
            {
                "name": "Care_Email_Extraction",
                "version_tag": "legacy",
                "cursor_column": None,                 # None = one-time backfill
            },
            {
                "name": "Care_Email_Extraction_V3",
                "version_tag": "v3",
                "cursor_column": "last_updated_at",     # incremental sync column
            },
        ],
    }

Adding a third table generation later, or a fourth team's database, means
adding one more dict like this — nothing in this file changes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Iterator, Optional

from .adapter import SourceAdapter
from .agent_extraction_transport import AgentExtractionTransport
from .models import (
    DocumentProvenance,
    SourceCapability,
    SourceDocument,
    SourceHealth,
    SourceIdentity,
    SourceType,
)

logger = logging.getLogger(__name__)

BACKFILL_DONE_MARKER = "__backfilled__"

# Known fields rendered first, in a fixed human-readable order, for good
# chunk/embedding quality. Anything the row has that ISN'T in this list
# still gets included (see _row_to_document) — schema drift never silently
# drops data, it just renders in a less curated order.
_KNOWN_FIELD_ORDER = [
    ("case_number", "Case Number"),
    ("cleaned_subject", "Subject"),
    ("property_name", "Property"),
    ("property_code", "Property Code"),
    ("chain_code", "Chain Code"),
    ("product", "Product"),
    ("issue_type", "Issue Type"),
    ("error_type", "Error Type"),
    ("issue_status", "Issue Status"),
    ("issue_ownership", "Issue Ownership"),
    ("intervention_type", "Intervention Type"),
    ("sla_flag", "SLA Flag"),
    ("waiting_minutes", "Waiting Minutes"),
    ("client_waiting_flag", "Client Waiting"),
    ("multi_property_flag", "Multi-Property"),
    ("conversation_start_at", "Conversation Started"),
    ("last_inbound_at", "Last Inbound"),
    ("closed_at", "Closed At"),
    ("last_updated_at", "Last Updated"),
]
_IDENTITY_FIELDS = {"conversation_id"}  # used for identity, not rendered as a body line


class AgentExtractionAdapter(SourceAdapter):
    """Reads one or more "email extraction" tables from a single SQL
    Server database and yields them as SourceDocuments."""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        cfg = self.config
        for required in ("source_id", "server", "database", "team", "tables"):
            if not cfg.get(required):
                raise ValueError(f"AgentExtractionAdapter config missing required key: {required!r}")

        self.transport = AgentExtractionTransport(
            server=cfg["server"],
            database=cfg["database"],
        )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def identify(self) -> SourceIdentity:
        cfg = self.config
        return SourceIdentity(
            source_id=cfg["source_id"],
            source_type=SourceType.SQL,
            display_name=cfg.get("display_name", cfg["source_id"]),
            description=cfg.get(
                "description",
                f"Agent email extraction ({cfg['database']} on {cfg['server']})",
            ),
            owner_team=cfg.get("team_owner", "UNKNOWN"),
            config={
                "database": cfg["database"],
                "team": cfg["team"],
                "tables": [t["name"] for t in cfg["tables"]],
            },
        )

    def capabilities(self) -> SourceCapability:
        return SourceCapability(
            supports_discovery=True,
            supports_incremental=True,
            supports_content_fetch=True,
            supports_metadata=True,
            supports_deletion=False,   # extraction tables don't signal deletes
            supports_versioning=True,  # legacy vs v3, via provenance.version_tag
            supports_teams=True,
            supports_visibility=True,
            max_batch_size=500,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> SourceHealth:
        source_id = self.config["source_id"]
        healthy = self.transport.health_check()
        return SourceHealth(
            source_id=source_id,
            healthy=healthy,
            last_error="" if healthy else "Connection or authentication failed",
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, cursor: Optional[str] = None) -> Iterator[SourceDocument]:
        """Yield SourceDocuments from every configured table.

        `cursor` is a JSON object, one entry per table name, so several
        tables with different sync semantics (one-time backfill vs.
        ongoing incremental) can share a single opaque cursor string —
        the shape the Fabric's load/save_source_cursor already expects.
        """
        state: dict[str, str] = {}
        if cursor:
            try:
                state = json.loads(cursor)
            except (TypeError, json.JSONDecodeError):
                logger.warning("Ignoring unparseable cursor for %s", self.config["source_id"])

        for table_cfg in self.config["tables"]:
            yield from self._discover_table(table_cfg, state)

        self._save_cursor(json.dumps(state))

    def _discover_table(self, table_cfg: dict, state: dict[str, str]) -> Iterator[SourceDocument]:
        table = table_cfg["name"]
        cursor_column = table_cfg.get("cursor_column")

        if cursor_column is None:
            # One-time backfill: skip entirely once done.
            if state.get(table) == BACKFILL_DONE_MARKER:
                return
            since_value = None
        else:
            since_value = state.get(table)

        latest_seen = since_value
        row_count = 0
        try:
            for row in self.transport.fetch_rows(table, cursor_column, since_value):
                row_count += 1
                doc = self._row_to_document(row, table_cfg)
                if doc is not None:
                    yield doc
                if cursor_column:
                    val = row.get(cursor_column)
                    # max(), not overwrite: transport.fetch_rows() only
                    # guarantees ascending order for the incremental case
                    # (since_value set) — a full/first-run scan is
                    # deliberately unordered (see fetch_rows' docstring,
                    # avoids an expensive full-table sort), so rows can
                    # arrive in any order. ISO 8601 strings compare
                    # correctly as plain strings, so no datetime parsing
                    # is needed here.
                    if val and (latest_seen is None or str(val) > latest_seen):
                        latest_seen = str(val)
        except Exception as exc:
            logger.error("AgentExtractionAdapter failed reading %s: %s", table, exc)
            return  # leave this table's cursor state untouched, retry next run

        if cursor_column is None:
            state[table] = BACKFILL_DONE_MARKER
            logger.info("Backfilled %s: %d rows (one-time, won't repeat)", table, row_count)
        elif latest_seen is not None:
            state[table] = latest_seen
            logger.info("Synced %s: %d new/changed rows, cursor now %s", table, row_count, latest_seen)

    # ------------------------------------------------------------------
    # Row -> SourceDocument
    # ------------------------------------------------------------------

    def _row_to_document(self, row: dict[str, Any], table_cfg: dict) -> Optional[SourceDocument]:
        conversation_id = row.get("conversation_id")
        if not conversation_id:
            return None  # no stable identity to key a document on

        cfg = self.config
        team = cfg["team"]
        version_tag = table_cfg["version_tag"]

        lines: list[str] = []
        for key, label in _KNOWN_FIELD_ORDER:
            val = row.get(key)
            if val not in (None, ""):
                lines.append(f"{label}: {val}")

        # Anything the row has that isn't in the known list still gets
        # included — schema drift never silently drops data.
        known_keys = {k for k, _ in _KNOWN_FIELD_ORDER} | _IDENTITY_FIELDS
        for key, val in sorted(row.items()):
            if key not in known_keys and val not in (None, ""):
                lines.append(f"{key.replace('_', ' ').title()}: {val}")

        if not lines:
            return None  # nothing meaningful to index

        case_number = row.get("case_number") or ""
        subject = row.get("cleaned_subject") or ""
        property_name = row.get("property_name") or ""
        # Real source data observed: `property_name` sometimes duplicates
        # the subject verbatim (an upstream extraction quirk, not
        # something to silently "fix" — this adapter renders what the
        # source has). Don't repeat it in the title when that happens.
        title_bits = [case_number, subject]
        if property_name and property_name.lower() not in subject.lower():
            title_bits.append(property_name)
        title_bits = [b for b in title_bits if b]
        title = f"[{team.upper()}] " + (
            " — ".join(title_bits) if title_bits else f"Conversation {conversation_id}"
        )

        text_content = "\n".join(lines)
        content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()

        tags = [t for t in (row.get("issue_type"), row.get("error_type")) if t]
        identifiers = [case_number] if case_number else []

        source_path = f"sql://{cfg['database']}/{table_cfg['name']}/{conversation_id}"

        return SourceDocument(
            title=title[:300],
            text_content=text_content,
            content_type="text/plain",
            format_hint="sql_row",
            provenance=DocumentProvenance(
                source_id=cfg["source_id"],
                source_type=SourceType.SQL,
                source_path=source_path,
                source_collection=table_cfg["name"],
                external_id=str(conversation_id),
                external_url=row.get("web_link") or "",
                last_modified_at=_parse_iso(row.get("last_updated_at")),
                content_hash=content_hash,
                version_tag=version_tag,
                trust_level="observed",
            ),
            team_ids=[team],
            ownership_type="associated",
            team_confidence=0.9,
            visibility=cfg.get("default_visibility", "Internal"),
            metadata=row,
            tags=tags,
            detected_identifiers=identifiers,
        )

    # ------------------------------------------------------------------
    # Cursor persistence (self-managed, same pattern as salesforce_adapter.py)
    # ------------------------------------------------------------------

    def _save_cursor(self, cursor_value: str) -> None:
        try:
            from kurukshetra.knowledge.fabric import KnowledgeFabric
            fabric = KnowledgeFabric()
            fabric.save_source_cursor(self.config["source_id"], cursor_value)
        except Exception as exc:
            logger.warning("Failed to persist cursor for %s: %s", self.config["source_id"], exc)


def _parse_iso(value: Any) -> Optional[Any]:
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


# ==================================================================
# Registry-driven loading — the "no new file for a new source" path
# ==================================================================

def load_registered_adapters() -> list["AgentExtractionAdapter"]:
    """Instantiate one AgentExtractionAdapter per enabled
    `source_type == "sql_agent_extraction"` row in the persistent source
    registry.

    This is the only place that turns durable config into a live adapter.
    Adding a new team/database is a `register_source(...)` call (see
    scripts/register_agent_extraction_sources.py) — nothing here needs to
    change to pick it up.

    PersistentSourceRegistry splits a source's identity (source_id,
    display_name, owner_team, default_visibility — its own real columns)
    from adapter-specific config (config_json: server, database, team,
    tables). This merges both into the single flat dict
    AgentExtractionAdapter.__init__ expects.
    """
    from .persistent_registry import PersistentSourceRegistry

    registry = PersistentSourceRegistry()
    adapters = []
    for record in registry.list_sources(enabled_only=True):
        if record.source_type != "sql_agent_extraction":
            continue
        try:
            record_dict = record.to_dict()
            merged_config = {
                "source_id": record.source_id,
                "display_name": record.display_name,
                "description": record.description,
                "team_owner": record.owner_team,
                "default_visibility": record.default_visibility,
                **record_dict["config"],  # server, database, team, tables
            }
            adapters.append(AgentExtractionAdapter(config=merged_config))
        except Exception as exc:
            logger.error("Failed to construct adapter for %s: %s", record.source_id, exc)
    return adapters
