"""
Salesforce Transport Layer
==========================

Abstract transport that separates HTTP/API concerns from adapter logic.

The adapter calls transport.query(), transport.get_record(), etc.
The transport handles authentication, pagination, rate limiting, retries.

Two implementations:
- SalesforceHTTPTransport: Real Salesforce REST API (requires simple-salesforce)
- MockSalesforceTransport: Deterministic test data (no network)

This separation means:
1. The adapter logic is testable without API access
2. The transport can be swapped for different auth methods
3. Retry/rate-limit logic lives in one place
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator, Optional

try:
    import requests as _requests
except ImportError:
    _requests = None  # Lazy — SalesforceHTTPTransport will fail at connect() if missing

logger = logging.getLogger(__name__)


# ==================================================================
# Transport Models
# ==================================================================


@dataclass(slots=True)
class SFRecord:
    """A single Salesforce record returned by the transport."""

    record_id: str
    object_type: str
    fields: dict[str, Any]
    system_modstamp: Optional[datetime] = None
    last_modified_date: Optional[datetime] = None
    created_date: Optional[datetime] = None
    is_deleted: bool = False

    def get(self, field_name: str, default: Any = None) -> Any:
        return self.fields.get(field_name, default)


@dataclass(slots=True)
class SFQueryResult:
    """Result of a Salesforce SOQL query."""

    records: list[SFRecord]
    total_size: int
    done: bool = True
    next_records_url: Optional[str] = None


@dataclass(slots=True)
class SFTransportStats:
    """Statistics for a transport session."""

    queries_executed: int = 0
    records_fetched: int = 0
    api_calls: int = 0
    retries: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0


# ==================================================================
# Abstract Transport
# ==================================================================


class SalesforceTransport(ABC):
    """
    Abstract Salesforce transport.

    Handles: connection, authentication, query execution, pagination.
    Does NOT handle: adapter logic, content transformation, dedup.
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to Salesforce.

        Returns True if successful.
        """

    @abstractmethod
    def query(self, soql: str, limit: Optional[int] = None) -> SFQueryResult:
        """
        Execute a SOQL query and return results.

        Handles pagination internally — returns all matching records.
        """

    @abstractmethod
    def get_record(
        self, object_type: str, record_id: str
    ) -> Optional[SFRecord]:
        """Fetch a single record by ID."""

    @abstractmethod
    def get_deleted(
        self, object_type: str, since: datetime
    ) -> list[str]:
        """
        Get IDs of records deleted since the given timestamp.

        Uses Salesforce GetDeleted API if available, otherwise
        returns empty list (adapter must handle gracefully).
        """

    @abstractmethod
    def is_healthy(self) -> bool:
        """Quick health check — can we reach Salesforce?"""

    @abstractmethod
    def get_stats(self) -> SFTransportStats:
        """Return transport statistics."""

    def close(self) -> None:
        """Release resources. Default no-op."""


# ==================================================================
# Mock Transport
# ==================================================================


class MockSalesforceTransport(SalesforceTransport):
    """
    Deterministic mock transport for testing.

    Pre-loaded with test records. Supports:
    - SOQL query simulation
    - Record fetch by ID
    - Deletion tracking
    - Configurable latency/errors
    """

    def __init__(
        self,
        records: Optional[list[SFRecord]] = None,
        fail_query: bool = False,
        fail_count: int = 0,
        latency_ms: float = 0.0,
    ) -> None:
        self._records: dict[str, SFRecord] = {}
        self._deleted_ids: dict[str, list[str]] = {}  # object_type -> [ids]
        self._connected = False
        self._fail_query = fail_query
        self._fail_count = fail_count
        self._fail_remaining = fail_count
        self._latency_ms = latency_ms
        self._stats = SFTransportStats()

        if records:
            for rec in records:
                self._records[rec.record_id] = rec

    def add_record(self, record: SFRecord) -> None:
        """Add a record to the mock store."""
        self._records[record.record_id] = record

    def remove_record(self, record_id: str, object_type: str = "") -> None:
        """Simulate deletion of a record."""
        rec = self._records.pop(record_id, None)
        if rec:
            ot = object_type or rec.object_type
            self._deleted_ids.setdefault(ot, []).append(record_id)

    def update_record(self, record_id: str, fields: dict[str, Any]) -> None:
        """Update fields on an existing record."""
        if record_id in self._records:
            self._records[record_id].fields.update(fields)
            self._records[record_id].system_modstamp = datetime.utcnow()

    def connect(self) -> bool:
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)
        self._connected = True
        return True

    def query(self, soql: str, limit: Optional[int] = None) -> SFQueryResult:
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)

        self._stats.queries_executed += 1
        self._stats.api_calls += 1

        # Simulate transient failures
        if self._fail_query or (self._fail_count > 0 and self._fail_remaining > 0):
            if self._fail_remaining > 0:
                self._fail_remaining -= 1
            self._stats.errors += 1
            raise ConnectionError("Simulated Salesforce API error")

        # Simple SOQL simulation — extract object type and WHERE clause
        object_type = self._extract_object_type(soql)
        records = [
            r for r in self._records.values()
            if r.object_type == object_type and not r.is_deleted
        ]

        # Apply SystemModstamp filter if present
        records = self._apply_where_clause(soql, records)

        if limit:
            records = records[:limit]

        self._stats.records_fetched += len(records)

        return SFQueryResult(
            records=records,
            total_size=len(records),
            done=True,
        )

    def get_record(
        self, object_type: str, record_id: str
    ) -> Optional[SFRecord]:
        self._stats.api_calls += 1
        rec = self._records.get(record_id)
        if rec and not rec.is_deleted:
            return rec
        return None

    def get_deleted(
        self, object_type: str, since: datetime
    ) -> list[str]:
        self._stats.api_calls += 1
        ids = self._deleted_ids.get(object_type, [])
        return [rid for rid in ids]

    def is_healthy(self) -> bool:
        return self._connected

    def get_stats(self) -> SFTransportStats:
        return self._stats

    def close(self) -> None:
        self._connected = False

    def _extract_object_type(self, soql: str) -> str:
        """Extract object type from a simple SOQL query."""
        upper = soql.upper()
        from_idx = upper.find(" FROM ")
        if from_idx >= 0:
            rest = soql[from_idx + 6:].strip()
            # Take until space, comma, or end
            obj = ""
            for ch in rest:
                if ch in (" ", ",", "\n", "\t"):
                    break
                obj += ch
            return obj
        return ""

    def _apply_where_clause(
        self, soql: str, records: list[SFRecord]
    ) -> list[SFRecord]:
        """Apply simple WHERE clause filtering for SystemModstamp."""
        upper = soql.upper()
        where_idx = upper.find(" WHERE ")
        if where_idx < 0:
            return records

        where_clause = soql[where_idx + 7:].strip()

        # Parse: SystemModstamp > '2025-01-01T00:00:00'
        if "SYSTEMMODSTAMP" in where_clause.upper():
            # Extract the comparison operator and value
            for op in [">=", ">", "<=", "<", "="]:
                op_idx = where_clause.find(op)
                if op_idx >= 0:
                    # Find the value after the operator
                    val_str = where_clause[op_idx + len(op):].strip()
                    # Remove ORDER BY, LIMIT etc
                    for keyword in ["ORDER", "LIMIT", "OFFSET"]:
                        kw_idx = val_str.upper().find(keyword)
                        if kw_idx >= 0:
                            val_str = val_str[:kw_idx].strip()
                    # Remove quotes
                    val_str = val_str.strip("'\" ")
                    try:
                        since = datetime.fromisoformat(val_str)
                        filtered = []
                        for r in records:
                            mod = r.system_modstamp
                            if mod is None:
                                filtered.append(r)
                                continue
                            if op == ">" and mod > since:
                                filtered.append(r)
                            elif op == ">=" and mod >= since:
                                filtered.append(r)
                            elif op == "<" and mod < since:
                                filtered.append(r)
                            elif op == "<=" and mod <= since:
                                filtered.append(r)
                            elif op == "=" and mod == since:
                                filtered.append(r)
                        return filtered
                    except (ValueError, TypeError):
                        pass

        return records


# ==================================================================
# Production HTTP Transport
# ==================================================================


class SalesforceHTTPTransport(SalesforceTransport):
    """
    Production Salesforce REST API transport.

    Uses the Salesforce REST API with username/password OAuth flow.
    Handles: authentication, SOQL queries, pagination, rate limiting,
    retry with exponential backoff, timeout.

    Credential resolution (in order):
    1. Explicit constructor arguments
    2. Environment variables:
       - SF_USERNAME
       - SF_PASSWORD
       - SF_SECURITY_TOKEN
       - SF_INSTANCE_URL (optional, overrides config)
       - SF_CLIENT_ID (optional, for OAuth flows)
       - SF_CLIENT_SECRET (optional, for OAuth flows)

    Usage:
        transport = SalesforceHTTPTransport(
            instance_url="https://ideas.salesforce.com",
            username="user@ideas.com",
        )
        transport.connect()
        result = transport.query("SELECT Id, Title FROM Knowledge__kav")
    """

    def __init__(
        self,
        instance_url: str = "",
        username: str = "",
        password: str = "",
        security_token: str = "",
        client_id: str = "",
        client_secret: str = "",
        api_version: str = "v59.0",
        timeout_seconds: int = 30,
        max_retries: int = 3,
        retry_base_delay_ms: int = 1000,
        retry_max_delay_ms: int = 30000,
    ) -> None:
        # Resolve from env vars if not provided
        self._instance_url = (
            instance_url
            or os.environ.get("SF_INSTANCE_URL", "")
            or os.environ.get("SF_LOGIN_URL", "https://login.salesforce.com")
        )
        self._username = username or os.environ.get("SF_USERNAME", "")
        self._password = password or os.environ.get("SF_PASSWORD", "")
        self._security_token = security_token or os.environ.get("SF_SECURITY_TOKEN", "")
        self._client_id = client_id or os.environ.get("SF_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("SF_CLIENT_SECRET", "")
        self._api_version = api_version
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._retry_base_ms = retry_base_delay_ms
        self._retry_max_ms = retry_max_delay_ms

        self._session: Optional[Any] = None
        self._access_token: str = ""
        self._connected = False
        self._stats = SFTransportStats()

    # ------------------------------------------------------------------
    # Connection / Authentication
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Authenticate with Salesforce using username/password OAuth.

        POST /services/oauth2/token with grant_type=password.
        Stores the access_token and instance_url for subsequent API calls.
        """
        if _requests is None:
            raise ImportError("'requests' package required for SalesforceHTTPTransport. Install with: pip install requests")

        if not self._username or not self._password:
            raise ValueError(
                "Salesforce credentials required. Set SF_USERNAME and SF_PASSWORD "
                "environment variables, or pass username/password to constructor."
            )

        token_url = f"{self._instance_url}/services/oauth2/token"
        payload = {
            "grant_type": "password",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "username": self._username,
            "password": self._password + self._security_token,
        }

        # Remove empty optional fields
        payload = {k: v for k, v in payload.items() if v}

        self._session = _requests.Session()
        self._session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })

        try:
            response = self._session.post(
                token_url,
                data=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()

            token_data = response.json()
            self._access_token = token_data["access_token"]

            # Use the instance URL from the token response if different
            if "instance_url" in token_data:
                self._instance_url = token_data["instance_url"]

            # Update session headers for API calls
            self._session.headers.update({
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            })

            self._connected = True
            logger.info(f"Connected to Salesforce: {self._instance_url}")
            return True

        except Exception as e:
            logger.error(f"Salesforce authentication failed: {e}")
            self._connected = False
            raise ConnectionError(f"Salesforce auth failed: {e}") from e

    def is_healthy(self) -> bool:
        """Check if we can reach Salesforce by querying limits."""
        if not self._connected or not self._session:
            return False
        try:
            url = f"{self._instance_url}/services/data/{self._api_version}/limits"
            response = self._session.get(url, timeout=self._timeout)
            return response.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Query Execution
    # ------------------------------------------------------------------

    def query(self, soql: str, limit: Optional[int] = None) -> SFQueryResult:
        """
        Execute a SOQL query via REST API.

        Handles pagination: follows nextRecordsUrl until all records
        are fetched.
        """
        if not self._connected:
            raise ConnectionError("Not connected. Call connect() first.")

        start = time.time()
        self._stats.queries_executed += 1

        query_url = (
            f"{self._instance_url}/services/data/{self._api_version}"
            f"/query?q={soql}"
        )

        all_records: list[SFRecord] = []
        total_size = 0
        url = query_url

        while url:
            response = self._execute_with_retry(url)
            if response is None:
                break

            data = response.json()
            total_size = data.get("totalSize", 0)

            for raw_record in data.get("records", []):
                sf_record = self._parse_record(raw_record)
                if sf_record:
                    all_records.append(sf_record)
                    self._stats.records_fetched += 1

            if not data.get("done", True):
                next_url = data.get("nextRecordsUrl", "")
                if next_url:
                    url = f"{self._instance_url}{next_url}"
                else:
                    url = None
            else:
                url = None

        self._stats.total_latency_ms += (time.time() - start) * 1000

        return SFQueryResult(
            records=all_records,
            total_size=total_size,
            done=True,
        )

    def get_record(
        self, object_type: str, record_id: str
    ) -> Optional[SFRecord]:
        """Fetch a single record by ID."""
        if not self._connected:
            return None

        url = (
            f"{self._instance_url}/services/data/{self._api_version}"
            f"/sobjects/{object_type}/{record_id}"
        )

        self._stats.api_calls += 1

        try:
            response = self._session.get(url, timeout=self._timeout)
            if response.status_code == 404:
                return None
            response.raise_for_status()

            data = response.json()
            return self._parse_record(data)
        except Exception as e:
            logger.warning(f"Failed to fetch record {record_id}: {e}")
            return None

    def get_deleted(
        self, object_type: str, since: datetime
    ) -> list[str]:
        """
        Get IDs of records deleted since the given timestamp.

        Uses the Salesforce GetDeleted API.
        Requires Enterprise/Unlimited edition.
        """
        if not self._connected:
            return []

        self._stats.api_calls += 1

        since_str = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        until_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

        url = (
            f"{self._instance_url}/services/data/{self._api_version}"
            f"/sobjects/{object_type}/deleted/?start={since_str}&end={until_str}"
        )

        try:
            response = self._session.get(url, timeout=self._timeout)
            if response.status_code == 403:
                logger.debug(f"GetDeleted not available for {object_type}")
                return []
            response.raise_for_status()

            data = response.json()
            deleted_records = data.get("deletedRecords", [])
            return [r["id"] for r in deleted_records]
        except Exception as e:
            logger.warning(f"Failed to get deleted records for {object_type}: {e}")
            return []

    def get_stats(self) -> SFTransportStats:
        return self._stats

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False

    # ------------------------------------------------------------------
    # Internal: Retry Logic
    # ------------------------------------------------------------------

    def _execute_with_retry(self, url: str) -> Optional[Any]:
        """Execute an HTTP request with retry and rate-limit handling."""
        for attempt in range(self._max_retries + 1):
            try:
                self._stats.api_calls += 1
                response = self._session.get(url, timeout=self._timeout)

                # Handle rate limiting (HTTP 429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning(f"Rate limited. Waiting {retry_after}s...")
                    self._stats.retries += 1
                    time.sleep(retry_after)
                    continue

                # Handle transient errors (5xx)
                if response.status_code >= 500:
                    if attempt == self._max_retries:
                        self._stats.errors += 1
                        raise ConnectionError(
                            f"Salesforce server error {response.status_code}"
                        )
                    delay_ms = min(
                        self._retry_base_ms * (2 ** attempt),
                        self._retry_max_ms,
                    )
                    self._stats.retries += 1
                    logger.warning(
                        f"Server error {response.status_code}, "
                        f"retry {attempt + 1}/{self._max_retries} in {delay_ms}ms"
                    )
                    time.sleep(delay_ms / 1000)
                    continue

                # Handle auth expiration (401)
                if response.status_code == 401:
                    logger.warning("Access token expired. Re-authenticating...")
                    try:
                        self.connect()
                        continue
                    except Exception:
                        self._stats.errors += 1
                        raise ConnectionError("Re-authentication failed")

                response.raise_for_status()
                return response

            except ConnectionError:
                raise
            except Exception as e:
                if attempt == self._max_retries:
                    self._stats.errors += 1
                    raise ConnectionError(f"Request failed: {e}") from e
                delay_ms = min(
                    self._retry_base_ms * (2 ** attempt),
                    self._retry_max_ms,
                )
                self._stats.retries += 1
                logger.warning(
                    f"Request error: {e}, retry {attempt + 1} in {delay_ms}ms"
                )
                time.sleep(delay_ms / 1000)

        return None

    # ------------------------------------------------------------------
    # Internal: Record Parsing
    # ------------------------------------------------------------------

    def _parse_record(self, raw: dict) -> Optional[SFRecord]:
        """Parse a Salesforce REST API record into SFRecord."""
        try:
            record_id = raw.get("Id", "")
            if not record_id:
                return None

            attributes = raw.get("attributes", {})
            object_type = attributes.get("type", "Unknown")

            fields = {
                k: v for k, v in raw.items()
                if k not in ("Id", "attributes")
            }

            def parse_dt(val: Any) -> Optional[datetime]:
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val
                if isinstance(val, str):
                    try:
                        val = val.replace("+00:00", "").replace("Z", "")
                        return datetime.fromisoformat(val)
                    except (ValueError, TypeError):
                        return None
                return None

            return SFRecord(
                record_id=record_id,
                object_type=object_type,
                fields=fields,
                system_modstamp=parse_dt(fields.get("SystemModstamp")),
                last_modified_date=parse_dt(fields.get("LastModifiedDate")),
                created_date=parse_dt(fields.get("CreatedDate")),
                is_deleted=bool(fields.get("IsDeleted", False)),
            )
        except Exception as e:
            logger.warning(f"Failed to parse record: {e}")
            return None
