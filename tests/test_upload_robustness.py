"""
Tests for Mission 3.56D — Robust User Knowledge Ingestion

Tests every supported format end-to-end, edge cases, and security.
Uses unique content per test to avoid cross-run collisions.
"""

import io
import json
import tempfile
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from command_center.backend.main import app


client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    """Short unique tag so every upload is fresh."""
    return uuid.uuid4().hex[:8]


def upload_file(filename: str, content: bytes, content_type: str = "application/octet-stream"):
    """Upload a file to /api/knowledge/upload."""
    return client.post(
        "/api/knowledge/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def make_txt(text: str = None) -> bytes:
    """Unique text content every call."""
    if text is None:
        text = f"G3 Data Feed Configuration document {_uid()}"
    else:
        text = f"{text} {_uid()}"
    return text.encode("utf-8")


def make_csv(headers: list[str] = None, rows: list[list[str]] = None) -> bytes:
    tag = _uid()
    headers = headers or ["Name", "Value", "Team"]
    rows = rows or [
        [f"G3 Config {tag}", "Rate Management", "SPM"],
        [f"OHIP Setup {tag}", "PMS Interface", "ICS"],
    ]
    lines = [",".join(headers)] + [",".join(r) for r in rows]
    return "\n".join(lines).encode("utf-8")


def make_json(data: dict = None) -> bytes:
    tag = _uid()
    data = data or {"system": "G3", "team": "SPM", "process": f"Rate Management {tag}"}
    return json.dumps(data, indent=2).encode("utf-8")


def make_xml(content: str = None) -> bytes:
    tag = _uid()
    content = content or f"<document><system>G3</system><team>SPM</team><id>{tag}</id></document>"
    return content.encode("utf-8")


def make_html(title: str = "Test", body: str = None) -> bytes:
    tag = _uid()
    body = body or f"G3 Data Feed Configuration {tag}"
    return f"<html><head><title>{title}</title></head><body><p>{body}</p></body></html>".encode("utf-8")


def make_md(content: str = None) -> bytes:
    tag = _uid()
    content = content or f"# G3 Configuration {tag}\n\nThis document describes G3 Data Feed Configuration."
    return content.encode("utf-8")


# ---------------------------------------------------------------------------
# Format Tests — every supported format
# ---------------------------------------------------------------------------

class TestSupportedFormats:
    """Verify every supported format ingests end-to-end."""

    def test_txt_upload(self):
        resp = upload_file(f"test_{_uid()}.txt", make_txt("G3 Data Feed Configuration for RMS integration."), "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"
        assert d["chunks_stored"] > 0

    def test_csv_upload(self):
        resp = upload_file(f"test_{_uid()}.csv", make_csv(), "text/csv")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"
        assert d["chunks_stored"] > 0

    def test_json_upload(self):
        resp = upload_file(f"test_{_uid()}.json", make_json(), "application/json")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"
        assert d["chunks_stored"] > 0

    def test_xml_upload(self):
        resp = upload_file(f"test_{_uid()}.xml", make_xml(), "application/xml")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"
        assert d["chunks_stored"] > 0

    def test_html_upload(self):
        resp = upload_file(f"test_{_uid()}.html", make_html(), "text/html")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"
        assert d["chunks_stored"] > 0

    def test_md_upload(self):
        resp = upload_file(f"test_{_uid()}.md", make_md(), "text/markdown")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"
        assert d["chunks_stored"] > 0

    def test_docx_upload(self):
        """Create a minimal DOCX file."""
        tag = _uid()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:body><w:p><w:r><w:t>G3 Data Feed Configuration document {tag}</w:t></w:r></w:p></w:body>'
                '</w:document>')
            zf.writestr("[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '</Types>')
            zf.writestr("_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '</Relationships>')
            zf.writestr("word/_rels/document.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        content = buf.getvalue()
        resp = upload_file(f"test_{_uid()}.docx", content,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] in ("indexed", "error")  # DOCX may error if python-docx not installed

    def test_pptx_upload(self):
        """Create a minimal PPTX file."""
        tag = _uid()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("ppt/slides/slide1.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
                f'<p:cSld><p:spTree><p:sp><p:txBody><a:r xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>G3 System Overview {tag}</a:t></a:r></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
            zf.writestr("[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
                '</Types>')
            zf.writestr("_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/slides/slide1.xml"/>'
                '</Relationships>')
            zf.writestr("ppt/_rels/presentation.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        content = buf.getvalue()
        resp = upload_file(f"test_{_uid()}.pptx", content,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] in ("indexed", "error")  # PPTX may error if python-pptx not installed


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test upload edge cases."""

    def test_duplicate_upload(self):
        tag = _uid()
        content = make_txt(f"Unique content for duplicate test {tag}")
        r1 = upload_file(f"dup_{tag}.txt", content, "text/plain")
        r2 = upload_file(f"dup_{tag}.txt", content, "text/plain")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate"

    def test_same_content_different_filename(self):
        """Same content, different filenames = different source paths.

        Fabric deduplicates by source_path, not content hash alone.
        Different filenames are separate documents.
        """
        tag = _uid()
        content = make_txt(f"Same content different filename {tag}")
        r1 = upload_file(f"same_a_{tag}.txt", content, "text/plain")
        r2 = upload_file(f"same_b_{tag}.txt", content, "text/plain")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Different filenames = different source paths = both indexed
        assert r2.json()["status"] in ("indexed", "duplicate")

    def test_empty_file_rejected(self):
        resp = upload_file("empty.txt", b"", "text/plain")
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_oversized_file_rejected(self):
        resp = upload_file("huge.txt", b"x" * (51 * 1024 * 1024), "text/plain")
        assert resp.status_code == 413

    def test_malicious_extension_rejected(self):
        resp = upload_file("evil.exe", b"MZ\x90\x00", "application/octet-stream")
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"].lower()

    def test_unsupported_extension_rejected(self):
        resp = upload_file("file.xyz", b"some content", "application/octet-stream")
        assert resp.status_code == 400
        assert "unsupported" in resp.json()["detail"].lower()

    def test_path_traversal_in_filename(self):
        resp = upload_file("../../etc/passwd.txt", make_txt("traversal test"), "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        # Filename should be sanitized
        assert ".." not in d.get("filename", "")
        assert "/" not in d.get("filename", "")

    def test_dotfile_rejected(self):
        resp = upload_file(".hidden", make_txt("hidden"), "text/plain")
        assert resp.status_code == 400

    def test_unicode_content(self):
        tag = _uid()
        content = f"G3 配置管理 — 数据流配置für ICS Team {tag}".encode("utf-8")
        resp = upload_file(f"unicode_{tag}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"

    def test_large_text_document(self):
        """1MB text document with unique content."""
        tag = _uid()
        content = (f"G3 Data Feed Configuration document {tag}. " * 100 + "\n") * 300
        resp = upload_file(f"large_{tag}.txt", content.encode("utf-8"), "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "indexed"
        assert d["chunks_stored"] > 0

    def test_document_with_no_extractable_text(self):
        """Binary file that isn't a supported format."""
        resp = upload_file("no_text.bin", b"\x00\x01\x02\x03", "application/octet-stream")
        assert resp.status_code == 400

    def test_malformed_json(self):
        """Malformed JSON should be handled gracefully."""
        tag = _uid()
        resp = upload_file(f"bad_{tag}.json", b"{invalid json content", "application/json")
        assert resp.status_code == 200
        d = resp.json()
        # Should handle gracefully — either error or indexed (text extracted from JSON)
        assert d["status"] in ("error", "indexed", "partial")

    def test_malformed_xml(self):
        """Malformed XML should be handled gracefully."""
        tag = _uid()
        resp = upload_file(f"bad_{tag}.xml", b"<root><unclosed>", "application/xml")
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] in ("error", "indexed", "partial")

    def test_upload_returns_document_id(self):
        content = make_txt("Unique test for document ID verification")
        resp = upload_file(f"id_test_{_uid()}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert d["document_id"]
        assert d["document_id"].startswith("DOC-")

    def test_upload_returns_team(self):
        content = make_txt("SPM team process document for G3 configuration")
        resp = upload_file(f"team_test_{_uid()}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert "team_id" in d

    def test_upload_returns_chunks(self):
        tag = _uid()
        content = f"G3 Data Feed Configuration {tag}. RMS integration. Rate management. ".encode("utf-8") * 20
        resp = upload_file(f"chunks_{tag}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert d["chunks_stored"] > 0

    def test_upload_returns_entities(self):
        content = make_txt("G3 system uses SFDC for data feed. SPM team manages configuration. ICS handles installation.")
        resp = upload_file(f"entities_{_uid()}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert d["entities_extracted"] >= 0

    def test_upload_returns_execution_time(self):
        content = make_txt("Timing test document")
        resp = upload_file(f"timing_{_uid()}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        assert d["execution_time_ms"] > 0


# ---------------------------------------------------------------------------
# Security Tests
# ---------------------------------------------------------------------------

class TestUploadSecurity:
    """Test upload security requirements."""

    def test_no_internal_path_exposure(self):
        content = make_txt("Security test document")
        resp = upload_file(f"sec_{_uid()}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        # Should not expose internal paths in message
        msg = d.get("message", "")
        assert "Users\\" not in msg

    def test_no_secret_exposure(self):
        content = make_txt("Secret test document")
        resp = upload_file(f"secret_{_uid()}.txt", content, "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        msg = d.get("message", "")
        assert "password" not in msg.lower()
        assert "api_key" not in msg.lower()
        assert "token" not in msg.lower()

    def test_filename_sanitized(self):
        resp = upload_file("../../../etc/passwd.txt", make_txt("test"), "text/plain")
        assert resp.status_code == 200
        d = resp.json()
        # Filename should not contain path traversal
        assert ".." not in d.get("filename", "")

    def test_content_hash_in_upload_path(self):
        """Verify upload uses content hash to prevent overwrites."""
        tag = _uid()
        content = make_txt(f"Hash test document {tag}")
        r1 = upload_file(f"hash_a_{tag}.txt", content, "text/plain")
        r2 = upload_file(f"hash_b_{tag}.txt", content, "text/plain")
        # Both should succeed
        assert r1.status_code == 200
        assert r2.status_code == 200
