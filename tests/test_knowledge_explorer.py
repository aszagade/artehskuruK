"""Tests for Knowledge Explorer backend endpoints."""
import unittest


class TestExplorerSources(unittest.TestCase):
    """/api/sources returns structured source catalog."""

    def test_sources_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/sources")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("sources", data)
        self.assertIsInstance(data["sources"], list)
        self.assertGreater(data["total"], 0)
        print(f"  [OK] Sources: {data['total']} sources found")

    def test_sources_have_required_fields(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/sources")
        data = r.json()
        for source in data["sources"]:
            self.assertIn("source_id", source)
            self.assertIn("name", source)
            self.assertIn("source_type", source)
            self.assertIn("status", source)
            self.assertIn(source["status"], ["indexed", "live", "unavailable", "not_connected"])
        print(f"  [OK] All sources have required fields with valid status values")

    def test_sources_include_local_documents(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/sources")
        data = r.json()
        ids = [s["source_id"] for s in data["sources"]]
        self.assertIn("local_documents", ids)
        local = [s for s in data["sources"] if s["source_id"] == "local_documents"][0]
        self.assertGreater(local["document_count"], 0)
        print(f"  [OK] Local documents: {local['document_count']} docs")


class TestExplorerTimeline(unittest.TestCase):
    """/api/knowledge/timeline returns ingestion events."""

    def test_timeline_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/knowledge/timeline")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("events", data)
        self.assertIsInstance(data["events"], list)
        print(f"  [OK] Timeline: {data['total']} events")

    def test_timeline_events_have_structure(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/knowledge/timeline?limit=5")
        data = r.json()
        for event in data["events"][:5]:
            self.assertIn("event_id", event)
            self.assertIn("event_type", event)
            self.assertIn("description", event)
            self.assertIn("timestamp", event)
        print(f"  [OK] Timeline events have correct structure")


class TestExplorerHealth(unittest.TestCase):
    """/api/health/detail returns subsystem health."""

    def test_health_detail_endpoint(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/health/detail")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("overall", data)
        self.assertIn("checks", data)
        self.assertIsInstance(data["checks"], list)
        self.assertGreater(len(data["checks"]), 0)
        print(f"  [OK] Health detail: {data['overall']}, {len(data['checks'])} checks")

    def test_health_checks_have_structure(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/health/detail")
        data = r.json()
        for check in data["checks"]:
            self.assertIn("component", check)
            self.assertIn("status", check)
            self.assertIn("message", check)
            self.assertIn(check["status"], ["healthy", "degraded", "unavailable", "not_configured"])
        print(f"  [OK] All health checks have valid structure")

    def test_database_is_healthy(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/health/detail")
        data = r.json()
        db_check = [c for c in data["checks"] if c["component"] == "Database"]
        self.assertEqual(len(db_check), 1)
        self.assertEqual(db_check[0]["status"], "healthy")
        print(f"  [OK] Database is healthy")


class TestExplorerMemory(unittest.TestCase):
    """/api/memory/summary returns user-scoped memory."""

    def test_memory_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/memory/summary")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("working_memory", data)
        self.assertIn("episodic_memory", data)
        self.assertIn("semantic_memory", data)
        self.assertIn("procedural_memory", data)
        self.assertIn("prospective_memory", data)
        self.assertIn("external_memory", data)
        print(f"  [OK] Memory summary: all 6 types present")

    def test_memory_is_user_scoped(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r1 = client.get("/api/memory/summary?user_id=alice")
        r2 = client.get("/api/memory/summary?user_id=bob")
        d1, d2 = r1.json(), r2.json()
        self.assertEqual(d1["user_id"], "alice")
        self.assertEqual(d2["user_id"], "bob")
        print(f"  [OK] Memory is user-scoped: alice vs bob")


class TestExplorerGaps(unittest.TestCase):
    """/api/knowledge/gaps returns gap analysis."""

    def test_gaps_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/knowledge/gaps")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("strong_areas", data)
        self.assertIn("weak_areas", data)
        self.assertIn("coverage_summary", data)
        print(f"  [OK] Gaps: {len(data['strong_areas'])} strong, {len(data['weak_areas'])} weak")

    def test_gaps_have_team_data(self):
        from fastapi.testclient import TestClient
        from command_center.backend.main import app
        client = TestClient(app)
        r = client.get("/api/knowledge/gaps")
        data = r.json()
        all_areas = data["strong_areas"] + data["weak_areas"]
        for area in all_areas:
            self.assertIn("area", area)
            self.assertIn("documents", area)
            self.assertIn("reason", area)
        print(f"  [OK] All gap areas have required fields")


if __name__ == "__main__":
    unittest.main()
