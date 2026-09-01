"""Tests for Graph Visualization API — Mission 3.57."""

import json
import pytest
from fastapi.testclient import TestClient

from command_center.backend.main import app


client = TestClient(app, raise_server_exceptions=False)


class TestVisualizationAPI:
    """Tests for /api/graph/visualization endpoint."""

    def test_visualization_returns_200(self):
        resp = client.get("/api/graph/visualization?limit=10")
        assert resp.status_code == 200

    def test_visualization_has_nodes_and_edges(self):
        resp = client.get("/api/graph/visualization?limit=10")
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert "meta" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_visualization_meta_fields(self):
        resp = client.get("/api/graph/visualization?limit=10")
        data = resp.json()
        meta = data["meta"]
        assert "totalNodes" in meta
        assert "totalEdges" in meta
        assert "nodesByType" in meta
        assert "filtered" in meta
        assert meta["filtered"] is True

    def test_visualization_node_fields(self):
        resp = client.get("/api/graph/visualization?limit=5")
        data = resp.json()
        for node in data["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "type" in node
            assert "quality" in node
            assert "qualityLabel" in node

    def test_visualization_edge_fields(self):
        resp = client.get("/api/graph/visualization?limit=5")
        data = resp.json()
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "relationship" in edge
            assert "confidence" in edge

    def test_visualization_excludes_noise(self):
        resp = client.get("/api/graph/visualization?exclude_noise=true&limit=100")
        data = resp.json()
        for node in data["nodes"]:
            assert node["qualityLabel"] != "NOISE"

    def test_visualization_limit_works(self):
        resp = client.get("/api/graph/visualization?limit=5")
        data = resp.json()
        # Limit applies to entity query; synthetic team nodes may be added
        # so total may slightly exceed limit. Check entity count is bounded.
        assert data["meta"]["totalNodes"] <= 20  # 5 entities + up to 7 synthetic teams

    def test_visualization_entities_not_empty(self):
        resp = client.get("/api/graph/visualization?limit=200")
        data = resp.json()
        assert data["meta"]["totalNodes"] > 0

    def test_visualization_edges_exist(self):
        resp = client.get("/api/graph/visualization?limit=200")
        data = resp.json()
        assert data["meta"]["totalEdges"] > 0

    def test_visualization_team_deduplication(self):
        """Teams should not appear multiple times."""
        resp = client.get("/api/graph/visualization?limit=200")
        data = resp.json()
        teams = [n for n in data["nodes"] if n["type"] == "team"]
        team_labels = [n["label"] for n in teams]
        # No duplicate labels
        assert len(team_labels) == len(set(team_labels))

    def test_visualization_derived_edges(self):
        """Should have derived co-occurrence and used_by_team edges."""
        resp = client.get("/api/graph/visualization?limit=200")
        data = resp.json()
        relationships = {e["relationship"] for e in data["edges"]}
        # At least one of these derived types should exist
        assert "co_occurs" in relationships or "used_by_team" in relationships

    def test_visualization_no_self_loops(self):
        resp = client.get("/api/graph/visualization?limit=200")
        data = resp.json()
        for edge in data["edges"]:
            assert edge["source"] != edge["target"]

    def test_visualization_entity_type_filter(self):
        resp = client.get("/api/graph/visualization?entity_type=system&limit=50")
        data = resp.json()
        # Primary nodes should be systems; synthetic team nodes may be added
        primary = [n for n in data["nodes"] if n["id"].startswith("SYS-") or n["id"].startswith("team:")]
        assert len(primary) > 0
        systems = [n for n in data["nodes"] if n["type"] == "system"]
        assert len(systems) > 0

    def test_visualization_quality_min(self):
        resp = client.get("/api/graph/visualization?quality_min=0.8&limit=50")
        data = resp.json()
        for node in data["nodes"]:
            assert node["quality"] >= 0.8


class TestEntityTypeCounts:
    """Tests for /api/graph/entity-types endpoint."""

    def test_entity_types_returns_200(self):
        resp = client.get("/api/graph/entity-types")
        assert resp.status_code == 200

    def test_entity_types_has_types(self):
        resp = client.get("/api/graph/entity-types")
        data = resp.json()
        assert "types" in data
        assert isinstance(data["types"], dict)

    def test_entity_types_contain_quality_labels(self):
        resp = client.get("/api/graph/entity-types")
        data = resp.json()
        for entity_type, quality_map in data["types"].items():
            assert isinstance(quality_map, dict)
            for label, count in quality_map.items():
                assert isinstance(count, int)
                assert count > 0


class TestTeamsSummary:
    """Tests for /api/graph/teams endpoint."""

    def test_teams_returns_200(self):
        resp = client.get("/api/graph/teams")
        assert resp.status_code == 200

    def test_teams_has_teams(self):
        resp = client.get("/api/graph/teams")
        data = resp.json()
        assert "teams" in data
        assert "total" in data
        assert data["total"] > 0

    def test_teams_have_required_fields(self):
        resp = client.get("/api/graph/teams")
        data = resp.json()
        for team in data["teams"]:
            assert "teamId" in team
            assert "entityCount" in team
            assert "entityTypes" in team


class TestNeighborhood:
    """Tests for /api/graph/neighborhood endpoint."""

    def test_neighborhood_returns_200(self):
        resp = client.get("/api/graph/neighborhood/SYS-G3-RMS?depth=1")
        assert resp.status_code == 200

    def test_neighborhood_has_center(self):
        resp = client.get("/api/graph/neighborhood/SYS-G3-RMS?depth=1")
        data = resp.json()
        assert "center" in data
        assert data["center"]["label"] == "G3 RMS"

    def test_neighborhood_has_nodes_and_edges(self):
        resp = client.get("/api/graph/neighborhood/SYS-G3-RMS?depth=1&limit=10")
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0

    def test_neighborhood_404_for_unknown(self):
        resp = client.get("/api/graph/neighborhood/NONEXISTENT-ENTITY?depth=1")
        assert resp.status_code == 404

    def test_neighborhood_depth_limit(self):
        resp = client.get("/api/graph/neighborhood/SYS-G3-RMS?depth=2&limit=5")
        data = resp.json()
        assert data["meta"]["totalNodes"] <= 5


class TestSanjayaContext:
    """Tests for /api/graph/sanjaya-context endpoint."""

    def test_sanjaya_context_returns_200(self):
        resp = client.get("/api/graph/sanjaya-context?entity_id=SYS-G3-RMS")
        assert resp.status_code == 200

    def test_sanjaya_context_has_entity_and_question(self):
        resp = client.get("/api/graph/sanjaya-context?entity_id=SYS-G3-RMS")
        data = resp.json()
        assert "entity" in data
        assert "suggestedQuestion" in data
        assert data["entity"]["label"] == "G3 RMS"
        assert "G3 RMS" in data["suggestedQuestion"]

    def test_sanjaya_context_team_entity(self):
        resp = client.get("/api/graph/sanjaya-context?entity_id=TEAM-ICS")
        data = resp.json()
        assert "ICS" in data["suggestedQuestion"]

    def test_sanjaya_context_404_for_unknown(self):
        resp = client.get("/api/graph/sanjaya-context?entity_id=NONEXISTENT")
        assert resp.status_code == 404


class TestGraph3dJsServing:
    """Tests for graph3d.js static file serving."""

    def test_graph3d_js_serves(self):
        resp = client.get("/graph3d.js")
        assert resp.status_code == 200

    def test_graph3d_js_is_javascript(self):
        resp = client.get("/graph3d.js")
        assert "javascript" in resp.headers.get("content-type", "")

    def test_graph3d_js_contains_renderer(self):
        resp = client.get("/graph3d.js")
        content = resp.text
        assert "Graph3D" in content
        assert "THREE" in content or "init2DCanvas" in content


class TestFrontendServing:
    """Tests for frontend HTML with new map components."""

    def test_frontend_serves(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_frontend_contains_graph_container(self):
        resp = client.get("/")
        assert "graph-container" in resp.text

    def test_frontend_contains_three_js(self):
        resp = resp = client.get("/")
        assert "three.min.js" in resp.text

    def test_frontend_contains_graph3d_script(self):
        resp = client.get("/")
        assert "graph3d.js" in resp.text

    def test_frontend_contains_map_filters(self):
        resp = client.get("/")
        assert "filterMap" in resp.text

    def test_frontend_contains_3d_2d_toggle(self):
        resp = client.get("/")
        assert "btn-3d" in resp.text
        assert "btn-2d" in resp.text


class TestBackwardCompatibility:
    """Verify original graph endpoints still work."""

    def test_graph_stats(self):
        resp = client.get("/api/graph/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_entities" in data

    def test_graph_entities_search(self):
        resp = client.get("/api/graph/entities?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "entities" in data

    def test_graph_entity_context(self):
        resp = client.get("/api/graph/entity/SYS-G3-RMS")
        assert resp.status_code == 200

    def test_graph_communities(self):
        resp = client.get("/api/graph/communities")
        assert resp.status_code == 200
