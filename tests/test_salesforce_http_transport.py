"""
Salesforce HTTP Transport Tests
================================

Deterministic tests for the production HTTP transport using
unittest.mock to simulate Salesforce API responses.

No network access or credentials required.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from kurukshetra.sources.salesforce_transport import (
    SalesforceHTTPTransport,
    SFRecord,
)


# ==================================================================
# Mock Response Helpers
# ==================================================================


def _mock_response(status_code: int = 200, json_data: dict = None, headers: dict = None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"{status_code}")
    return resp


def _mock_token_response():
    """Create a mock OAuth token response."""
    return _mock_response(200, {
        "access_token": "00D000000000000!AQBAQ",
        "instance_url": "https://test.salesforce.com",
        "id": "https://test.salesforce.com/id/00D000000000000/005000000000000",
        "token_type": "Bearer",
        "issued_at": "1234567890000",
        "signature": "abc123",
    })


def _mock_query_response(records: list[dict], total_size: int = None, done: bool = True):
    """Create a mock SOQL query response."""
    return _mock_response(200, {
        "totalSize": total_size or len(records),
        "done": done,
        "records": records,
    })


def _mock_sf_record(
    record_id: str = "001000000000001",
    title: str = "Test Article",
    body: str = "Test body content",
    modstamp: str = "2025-06-15T10:30:00.000Z",
    object_type: str = "Knowledge__kav",
) -> dict:
    """Create a mock Salesforce record dict."""
    return {
        "Id": record_id,
        "attributes": {"type": object_type, "url": f"/services/data/v59.0/sobjects/{object_type}/{record_id}"},
        "Title": title,
        "KnowledgeBody__c": body,
        "Summary": f"Summary of {title}",
        "ArticleNumber": f"ART-{record_id[-3:]}",
        "SystemModstamp": modstamp,
        "LastModifiedDate": modstamp,
        "CreatedDate": "2024-01-01T00:00:00.000Z",
        "IsDeleted": False,
        "PublishStatus": "Published",
        "ValidationStatus": "Approved",
        "Language": "en",
    }


# ==================================================================
# Transport Construction Tests
# ==================================================================


class TestSalesforceHTTPTransportConstruction(unittest.TestCase):
    """Test transport instantiation and credential resolution."""

    @patch.dict(os.environ, {}, clear=True)
    def test_explicit_credentials(self):
        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com",
            password="pass123",
            security_token="token123",
        )
        self.assertEqual(t._instance_url, "https://test.salesforce.com")
        self.assertEqual(t._username, "user@test.com")
        self.assertEqual(t._password, "pass123")
        self.assertEqual(t._security_token, "token123")

    @patch.dict(os.environ, {
        "SF_USERNAME": "env_user@test.com",
        "SF_PASSWORD": "env_pass",
        "SF_SECURITY_TOKEN": "env_token",
        "SF_INSTANCE_URL": "https://env.salesforce.com",
    })
    def test_env_var_credentials(self):
        t = SalesforceHTTPTransport()
        self.assertEqual(t._username, "env_user@test.com")
        self.assertEqual(t._password, "env_pass")
        self.assertEqual(t._instance_url, "https://env.salesforce.com")

    def test_default_api_version(self):
        t = SalesforceHTTPTransport()
        self.assertEqual(t._api_version, "v59.0")

    def test_custom_timeout(self):
        t = SalesforceHTTPTransport(timeout_seconds=60)
        self.assertEqual(t._timeout, 60)


# ==================================================================
# Authentication Tests
# ==================================================================


class TestSalesforceHTTPTransportAuth(unittest.TestCase):
    """Test OAuth authentication flow."""

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_connect_success(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.post.return_value = _mock_token_response()

        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com",
            password="pass123",
            security_token="token123",
        )
        result = t.connect()

        self.assertTrue(result)
        self.assertTrue(t._connected)
        self.assertEqual(t._access_token, "00D000000000000!AQBAQ")
        # Instance URL should be updated from token response
        self.assertEqual(t._instance_url, "https://test.salesforce.com")

    def test_connect_missing_credentials(self):
        t = SalesforceHTTPTransport()
        with self.assertRaises(ValueError):
            t.connect()

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_connect_auth_failure(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.post.return_value = _mock_response(400, {"error": "invalid_grant"})

        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com",
            password="wrong",
        )
        with self.assertRaises(ConnectionError):
            t.connect()
        self.assertFalse(t._connected)


# ==================================================================
# Query Tests
# ==================================================================


class TestSalesforceHTTPTransportQuery(unittest.TestCase):
    """Test SOQL query execution."""

    def _connected_transport(self, mock_session):
        """Create a pre-connected transport with mocked session."""
        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com",
            password="pass",
        )
        t._session = mock_session
        t._connected = True
        t._access_token = "test_token"
        return t

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_query_returns_records(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        records = [
            _mock_sf_record("SF-001", "Article 1", "Body 1"),
            _mock_sf_record("SF-002", "Article 2", "Body 2"),
        ]
        mock_session.get.return_value = _mock_query_response(records)

        t = self._connected_transport(mock_session)
        result = t.query("SELECT Id, Title FROM Knowledge__kav")

        self.assertEqual(result.total_size, 2)
        self.assertEqual(len(result.records), 2)
        self.assertTrue(result.done)
        self.assertEqual(result.records[0].record_id, "SF-001")
        self.assertEqual(result.records[0].get("Title"), "Article 1")

    def test_query_not_connected(self):
        t = SalesforceHTTPTransport()
        with self.assertRaises(ConnectionError):
            t.query("SELECT Id FROM Knowledge__kav")

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_query_pagination(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # First page: 2 records, not done
        page1 = _mock_query_response(
            [_mock_sf_record("SF-001", "Art 1"), _mock_sf_record("SF-002", "Art 2")],
            total_size=3, done=False,
        )
        # Second page: 1 record, done
        page2 = _mock_query_response(
            [_mock_sf_record("SF-003", "Art 3")],
            total_size=3, done=True,
        )
        page1.json.return_value["nextRecordsUrl"] = "/services/data/v59.0/query/01g00000000001/next"

        mock_session.get.side_effect = [page1, page2]

        t = self._connected_transport(mock_session)
        result = t.query("SELECT Id, Title FROM Knowledge__kav")

        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.total_size, 3)

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_query_retry_on_500(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # First call: 500, second call: success
        error_resp = _mock_response(500)
        success_resp = _mock_query_response([_mock_sf_record("SF-001")])
        mock_session.get.side_effect = [error_resp, success_resp]

        t = self._connected_transport(mock_session)
        t._retry_base_ms = 10  # Fast for testing
        result = t.query("SELECT Id FROM Knowledge__kav")

        self.assertEqual(len(result.records), 1)
        self.assertGreater(t._stats.retries, 0)

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_query_retry_on_429(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Rate limited, then success
        rate_resp = _mock_response(429, headers={"Retry-After": "1"})
        success_resp = _mock_query_response([_mock_sf_record("SF-001")])
        mock_session.get.side_effect = [rate_resp, success_resp]

        t = self._connected_transport(mock_session)
        result = t.query("SELECT Id FROM Knowledge__kav")

        self.assertEqual(len(result.records), 1)
        self.assertGreater(t._stats.retries, 0)


# ==================================================================
# Record Fetch Tests
# ==================================================================


class TestSalesforceHTTPTransportGetRecord(unittest.TestCase):
    """Test single record fetch."""

    def _connected_transport(self, mock_session):
        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com", password="pass",
        )
        t._session = mock_session
        t._connected = True
        return t

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_get_record_found(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = _mock_response(200, _mock_sf_record("SF-001", "Found"))

        t = self._connected_transport(mock_session)
        rec = t.get_record("Knowledge__kav", "SF-001")

        self.assertIsNotNone(rec)
        self.assertEqual(rec.record_id, "SF-001")
        self.assertEqual(rec.get("Title"), "Found")

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_get_record_not_found(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = _mock_response(404)

        t = self._connected_transport(mock_session)
        rec = t.get_record("Knowledge__kav", "NONEXISTENT")
        self.assertIsNone(rec)


# ==================================================================
# Deletion Detection Tests
# ==================================================================


class TestSalesforceHTTPTransportGetDeleted(unittest.TestCase):
    """Test deleted record detection."""

    def _connected_transport(self, mock_session):
        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com", password="pass",
        )
        t._session = mock_session
        t._connected = True
        return t

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_get_deleted_returns_ids(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = _mock_response(200, {
            "deletedRecords": [
                {"id": "SF-DEL-1", "deletedDate": "2025-06-01T00:00:00.000Z"},
                {"id": "SF-DEL-2", "deletedDate": "2025-06-02T00:00:00.000Z"},
            ],
        })

        t = self._connected_transport(mock_session)
        deleted = t.get_deleted("Knowledge__kav", datetime(2025, 5, 1))

        self.assertEqual(len(deleted), 2)
        self.assertIn("SF-DEL-1", deleted)

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_get_deleted_403_returns_empty(self, mock_session_cls):
        """Professional edition doesn't support GetDeleted."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = _mock_response(403)

        t = self._connected_transport(mock_session)
        deleted = t.get_deleted("Knowledge__kav", datetime(2025, 5, 1))
        self.assertEqual(deleted, [])


# ==================================================================
# Health Check Tests
# ==================================================================


class TestSalesforceHTTPTransportHealth(unittest.TestCase):
    """Test health check."""

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_healthy_when_connected(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = _mock_response(200, {"maxConcurrentApexExecutions": 40})

        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com", password="pass",
        )
        t._session = mock_session
        t._connected = True

        self.assertTrue(t.is_healthy())

    def test_unhealthy_when_not_connected(self):
        t = SalesforceHTTPTransport()
        self.assertFalse(t.is_healthy())


# ==================================================================
# Record Parsing Tests
# ==================================================================


class TestSalesforceHTTPTransportParsing(unittest.TestCase):
    """Test Salesforce record parsing."""

    def test_parse_valid_record(self):
        t = SalesforceHTTPTransport()
        raw = _mock_sf_record("SF-001", "Test", "Body", modstamp="2025-06-15T10:30:00.000Z")
        rec = t._parse_record(raw)

        self.assertIsNotNone(rec)
        self.assertEqual(rec.record_id, "SF-001")
        self.assertEqual(rec.object_type, "Knowledge__kav")
        self.assertEqual(rec.get("Title"), "Test")
        self.assertIsNotNone(rec.system_modstamp)

    def test_parse_record_without_id(self):
        t = SalesforceHTTPTransport()
        rec = t._parse_record({"Title": "No ID"})
        self.assertIsNone(rec)

    def test_parse_deleted_record(self):
        t = SalesforceHTTPTransport()
        raw = _mock_sf_record("SF-DEL", "Deleted", "Body")
        raw["IsDeleted"] = True
        rec = t._parse_record(raw)
        self.assertTrue(rec.is_deleted)


# ==================================================================
# Close/Cleanup Tests
# ==================================================================


class TestSalesforceHTTPTransportClose(unittest.TestCase):
    """Test cleanup."""

    def test_close(self):
        t = SalesforceHTTPTransport()
        t._connected = True
        t._session = MagicMock()
        t.close()
        self.assertFalse(t._connected)
        self.assertIsNone(t._session)


# ==================================================================
# Stats Tests
# ==================================================================


class TestSalesforceHTTPTransportStats(unittest.TestCase):
    """Test statistics tracking."""

    @patch("kurukshetra.sources.salesforce_transport._requests.Session")
    def test_stats_tracked(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = _mock_query_response(
            [_mock_sf_record("SF-001"), _mock_sf_record("SF-002")]
        )

        t = SalesforceHTTPTransport(
            instance_url="https://test.salesforce.com",
            username="user@test.com", password="pass",
        )
        t._session = mock_session
        t._connected = True

        t.query("SELECT Id FROM Knowledge__kav")

        stats = t.get_stats()
        self.assertEqual(stats.queries_executed, 1)
        self.assertEqual(stats.records_fetched, 2)
        self.assertGreater(stats.total_latency_ms, 0)


if __name__ == "__main__":
    unittest.main()
