"""
Agent Extraction Transport
===========================

Thin, schema-agnostic SQL Server data-access layer for "agent email
extraction" style databases (CareAgent, ICSAgent today; any future team
database following the same shape needs zero new code here).

Deliberately schema-agnostic: reads whatever columns a table actually has
via cursor.description rather than a hardcoded column list, so adding a
column upstream — or pointing this at a new, differently-shaped table —
never requires a code change in this file.

Credentials are NEVER read from adapter config — only from environment
variables (AGENT_DB_USER, AGENT_DB_PASSWORD), matching
kurukshetra/sources/adapter.py's contract and salesforce_transport.py's
precedent. server/database are not secrets and may come from config.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import time
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

DEFAULT_DRIVER = "{ODBC Driver 18 for SQL Server}"
DEFAULT_BATCH_SIZE = 500
DEFAULT_TIMEOUT_S = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY_S = 2


def _json_safe(value: Any) -> Any:
    """Normalize a pyodbc cell value to something JSON/DuckDB-safe.

    datetime/date -> ISO string (so cursor values and metadata are always
    plain strings, never driver-specific objects); everything else passes
    through unchanged.
    """
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return value


class AgentExtractionTransport:
    """pyodbc-backed transport for agent-extraction SQL Server databases.

    One instance = one (server, database) connection. Multiple tables in
    that database are fetched through the same instance via fetch_rows().
    """

    def __init__(
        self,
        server: str,
        database: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: str = DEFAULT_DRIVER,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.server = server
        self.database = database
        self.username = username or os.environ.get("AGENT_DB_USER", "")
        self.password = password or os.environ.get("AGENT_DB_PASSWORD", "")
        self.driver = driver
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._conn = None

    @property
    def is_configured(self) -> bool:
        return bool(self.server and self.database and self.username and self.password)

    def _connection_string(self) -> str:
        return (
            f"DRIVER={self.driver};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            "TrustServerCertificate=yes;"
            f"Connection Timeout={self.timeout_s};"
        )

    def connect(self):
        """Lazily connect, with retry/backoff. Never logs the password —
        only server/database/attempt count."""
        if self._conn is not None:
            return self._conn
        if not self.is_configured:
            raise RuntimeError(
                "AgentExtractionTransport is not configured — set AGENT_DB_USER "
                "and AGENT_DB_PASSWORD (server/database come from adapter config)."
            )
        import pyodbc

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._conn = pyodbc.connect(self._connection_string())
                return self._conn
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "AgentExtractionTransport connect attempt %d/%d to %s.%s failed: %s",
                    attempt, self.max_retries, self.server, self.database, exc,
                )
                if attempt < self.max_retries:
                    time.sleep(DEFAULT_RETRY_BASE_DELAY_S * attempt)
        raise ConnectionError(
            f"Could not connect to {self.server}.{self.database} after "
            f"{self.max_retries} attempts: {last_error}"
        )

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def health_check(self) -> bool:
        try:
            conn = self.connect()
            conn.cursor().execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def fetch_rows(
        self,
        table: str,
        cursor_column: Optional[str] = None,
        since_value: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Iterator[dict[str, Any]]:
        """Yield rows from `table` as plain dicts, keyed by whatever
        columns the table actually has (via cursor.description) — no
        hardcoded column list.

        If cursor_column is given AND since_value is given (an incremental
        run with a small expected result set), rows are filtered
        server-side and ORDER BY is cheap. If cursor_column is given but
        since_value is None (a full/first-run scan — potentially the
        entire table), deliberately SKIP the server-side ORDER BY: sorting
        an unfiltered, possibly huge table before returning even one row
        is a real, measured cost (found live against Care_Email_Extraction_V3,
        ~58k rows) for no benefit — the caller (AgentExtractionAdapter)
        tracks the max cursor value itself as rows stream by, in Python,
        instead of relying on SQL-side ordering. If cursor_column is None
        entirely, rows are returned once, unordered — for one-time/legacy
        backfill tables that aren't tracked incrementally at all.

        Table/column names are validated against SQL Server identifier
        rules before use (this method builds SQL by string formatting,
        since parameters can't be used for identifiers) — only
        adapter-config-supplied names ever reach here, never raw user
        input, but the check is cheap insurance regardless.
        """
        _validate_identifier(table)
        if cursor_column:
            _validate_identifier(cursor_column)

        conn = self.connect()
        cur = conn.cursor()

        if cursor_column and since_value:
            cur.execute(
                f"SELECT * FROM [{table}] WHERE [{cursor_column}] > ? "
                f"ORDER BY [{cursor_column}] ASC",
                (since_value,),
            )
        else:
            # No ORDER BY for the full-scan case (cursor_column is None, or
            # it's a first run with no since_value) — see docstring.
            cur.execute(f"SELECT * FROM [{table}]")

        columns = [d[0] for d in cur.description]
        while True:
            batch = cur.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                yield {col: _json_safe(val) for col, val in zip(columns, row)}


def _validate_identifier(name: str) -> None:
    """Guard against SQL injection via table/column identifiers, which
    can't be parameterized. Config-supplied only, but cheap to check."""
    if not name or not all(c.isalnum() or c == "_" for c in name):
        raise ValueError(f"Unsafe SQL identifier rejected: {name!r}")
