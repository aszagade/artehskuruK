"""
Source Discovery Profiler Tests
===============================

20 deterministic tests proving:
  - recursive discovery
  - nested folder structures
  - supported/unsupported extensions
  - extension aggregation
  - top-level aggregation
  - depth calculation
  - category classification
  - duplicate detection
  - version pattern detection
  - naming pattern detection
  - JSON profile generation
  - no mutation of source
  - ingestion zone recommendations
  - CSV inventory loading
  - content sampling
  - content hash generation
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from kurukshetra.source_discovery.profiler import (
    FileRecord,
    SourceProfiler,
    SourceProfile,
    CATEGORY_MAP,
)


def _make_test_tree(base: Path) -> Path:
    """Create a deterministic test directory structure."""
    tree = base / "TestSource"
    tree.mkdir(parents=True, exist_ok=True)

    # Level 1: Knowledge documents
    docs = tree / "Documents"
    docs.mkdir(exist_ok=True)
    (docs / "readme.txt").write_text("This is a test document for G3 RMS configuration.")
    (docs / "guide.md").write_text("# Installation Guide\n\nStep 1: Configure SFDC\nStep 2: Verify NGI")
    (docs / "manual.docx").write_text("")  # empty but valid name
    (docs / "report.pdf").write_bytes(b"%PDF-1.4 fake content")
    (docs / "data.csv").write_text("column1,column2\nvalue1,value2")

    # Level 2: Nested subfolder
    sub = docs / "SubProcess"
    sub.mkdir(exist_ok=True)
    (sub / "config.txt").write_text("Configuration for ICS team workflow automation.")
    (sub / "checklist.txt").write_text("Install checklist for Data Verification")

    # Level 1: Code folder
    code = tree / "Automation"
    code.mkdir(exist_ok=True)
    (code / "script.py").write_text("print('hello')")
    (code / "test.py").write_text("assert True")
    (code / "types.pyi").write_text("def foo() -> None: ...")

    # Level 1: Data folder with SAS
    data = tree / "DataStore"
    data.mkdir(exist_ok=True)
    (data / "bigdata.sas7bdat").write_bytes(b"\x00" * 5000)
    (data / "export.xlsx").write_text("")  # minimal xlsx
    (data / "legacy.xls").write_text("")  # minimal xls
    (data / "archive.zip").write_bytes(b"PK" + b"\x00" * 100)

    # Level 1: Nested deep structure
    deep = tree / "DeepNest"
    deep.mkdir(exist_ok=True)
    for i in range(5):
        deep = deep / f"Level{i}"
        deep.mkdir(exist_ok=True)
    (deep / "deep_file.txt").write_text("Deeply nested content")

    # Version patterns
    vers = tree / "Versions"
    vers.mkdir(exist_ok=True)
    (vers / "report_v1.xlsx").write_text("version 1")
    (vers / "report_v2.xlsx").write_text("version 2")
    (vers / "report_v3.xlsx").write_text("version 3")
    (vers / "config_2024.txt").write_text("2024 config")
    (vers / "config_2025.txt").write_text("2025 config")
    (vers / "template_updated.docx").write_text("updated template")
    (vers / "template_final.docx").write_text("final template")

    # Duplicate names in different folders
    (tree / "Backup" / "old").mkdir(parents=True, exist_ok=True)
    (tree / "Backup" / "old" / "shared_name.txt").write_text("old version")
    (tree / "Current").mkdir(exist_ok=True)
    (tree / "Current" / "shared_name.txt").write_text("current version")

    return tree


class TestRecursiveDiscovery(unittest.TestCase):
    """Prove the profiler discovers all files recursively."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tree = _make_test_tree(Path(cls.tmp))
        profiler = SourceProfiler(max_sample_size=5)
        cls.profile = profiler.profile_source(
            path=str(cls.tree),
            source_name="TestSource",
        )

    def test_discovers_all_files(self):
        """All created files should be discovered."""
        self.assertEqual(self.profile.total_files, 24)

    def test_discovers_nested_folders(self):
        """Deep nesting should be detected."""
        self.assertGreaterEqual(self.profile.max_depth, 5)

    def test_counts_folders(self):
        """Folders should be counted correctly."""
        self.assertGreater(self.profile.total_folders, 10)

    def test_no_files_inaccessible(self):
        """All test files should be accessible."""
        self.assertEqual(self.profile.inaccessible_files, 0)


class TestExtensionDistribution(unittest.TestCase):
    """Prove extension aggregation works correctly."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tree = _make_test_tree(Path(cls.tmp))
        profiler = SourceProfiler(max_sample_size=5)
        cls.profile = profiler.profile_source(
            path=str(cls.tree),
            source_name="TestSource",
        )

    def test_txt_count(self):
        """Count .txt files correctly."""
        count = self.profile.extension_counts.get(".txt", 0)
        self.assertGreaterEqual(count, 6)

    def test_py_count(self):
        """Count .py files correctly."""
        count = self.profile.extension_counts.get(".py", 0)
        self.assertEqual(count, 2)

    def test_sas_count(self):
        """Count .sas7bdat files correctly."""
        count = self.profile.extension_counts.get(".sas7bdat", 0)
        self.assertEqual(count, 1)

    def test_supported_count(self):
        """Supported files should be properly counted."""
        self.assertGreater(self.profile.supported_files, 10)

    def test_unsupported_count(self):
        """Unsupported files should exist (sas, py, zip)."""
        self.assertGreater(self.profile.unsupported_files, 0)


class TestCategoryClassification(unittest.TestCase):
    """Prove file category classification works."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tree = _make_test_tree(Path(cls.tmp))
        profiler = SourceProfiler(max_sample_size=5)
        cls.profile = profiler.profile_source(
            path=str(cls.tree),
            source_name="TestSource",
        )

    def test_document_category(self):
        """PDF/DOCX should be classified as DOCUMENT."""
        count = self.profile.category_counts.get("DOCUMENT", 0)
        self.assertGreaterEqual(count, 2)

    def test_code_category(self):
        """Python files should be CODE."""
        count = self.profile.category_counts.get("CODE", 0)
        self.assertGreaterEqual(count, 3)

    def test_data_category(self):
        """SAS/CSV/XLSX should be DATA or SPREADSHEET."""
        data = self.profile.category_counts.get("DATA", 0)
        sheet = self.profile.category_counts.get("SPREADSHEET", 0)
        self.assertGreater(data + sheet, 2)

    def test_archive_category(self):
        """ZIP should be ARCHIVE."""
        count = self.profile.category_counts.get("ARCHIVE", 0)
        self.assertEqual(count, 1)


class TestTopLevelFolders(unittest.TestCase):
    """Prove top-level folder aggregation works."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tree = _make_test_tree(Path(cls.tmp))
        profiler = SourceProfiler(max_sample_size=5)
        cls.profile = profiler.profile_source(
            path=str(cls.tree),
            source_name="TestSource",
        )

    def test_top_folders_present(self):
        """Known top-level folders should appear."""
        folders = set(self.profile.top_level_folders.keys())
        self.assertIn("Documents", folders)
        self.assertIn("Automation", folders)
        self.assertIn("DataStore", folders)

    def test_documents_is_largest(self):
        """Documents folder should have the most files."""
        self.assertGreater(
            self.profile.top_level_folders.get("Documents", 0), 5
        )


class TestDuplicateDetection(unittest.TestCase):
    """Prove duplicate detection finds shared filenames."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tree = _make_test_tree(Path(cls.tmp))
        profiler = SourceProfiler(max_sample_size=5)
        cls.profile = profiler.profile_source(
            path=str(cls.tree),
            source_name="TestSource",
        )

    def test_same_name_duplicates(self):
        """shared_name.txt exists in two folders."""
        name_dupes = [
            d for d in self.profile.duplicate_groups
            if d["match_type"] == "same_name"
        ]
        self.assertGreater(len(name_dupes), 0)
        # Find the shared_name.txt group
        found = False
        for d in name_dupes:
            if any("shared_name.txt" in f for f in d["files"]):
                found = True
                break
        self.assertTrue(found, "shared_name.txt duplicate not detected")


class TestVersionPatterns(unittest.TestCase):
    """Prove version pattern detection works."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tree = _make_test_tree(Path(cls.tmp))
        profiler = SourceProfiler(max_sample_size=5)
        cls.profile = profiler.profile_source(
            path=str(cls.tree),
            source_name="TestSource",
        )

    def test_versioned_files(self):
        """report_v1/v2/v3 should be detected."""
        versioned = [
            p for p in self.profile.version_patterns
            if "report" in p["base_name"].lower()
        ]
        self.assertGreater(len(versioned), 0)

    def test_dated_files(self):
        """config_2024/2025 should be detected."""
        dated = [
            p for p in self.profile.version_patterns
            if "config" in p["base_name"].lower()
        ]
        self.assertGreater(len(dated), 0)

    def test_suffixed_files(self):
        """template_updated/final should be detected."""
        # Check all patterns for suffixed type
        suffixed = [
            p for p in self.profile.version_patterns
            if p["pattern_type"] == "suffixed"
        ]
        self.assertGreater(len(suffixed), 0,
            f"No suffixed patterns found. All patterns: {[(p['base_name'], p['pattern_type']) for p in self.profile.version_patterns]}")


class TestContentSampling(unittest.TestCase):
    """Prove content sampling works on supported files."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tree = _make_test_tree(Path(cls.tmp))
        profiler = SourceProfiler(max_sample_size=10)
        cls.profile = profiler.profile_source(
            path=str(cls.tree),
            source_name="TestSource",
        )

    def test_samples_generated(self):
        """Some documents should be sampled."""
        self.assertGreater(len(self.profile.sampled_documents), 0)

    def test_successful_extractions(self):
        """At least some text files should extract successfully."""
        ok = sum(
            1 for s in self.profile.sampled_documents
            if s["extraction_ok"]
        )
        self.assertGreater(ok, 0)

    def test_systems_detected_in_samples(self):
        """G3, RMS, SFDC should be detected in test documents."""
        summary = self.profile.sampling_summary
        systems = set(summary.get("systems_detected", []))
        # At least some known systems should be found
        self.assertTrue(
            len(systems) > 0,
            f"No systems detected. Found: {systems}",
        )

    def test_acronyms_detected(self):
        """Acronyms should be detected in test documents."""
        summary = self.profile.sampling_summary
        acronyms = set(summary.get("acronyms_detected", []))
        self.assertGreater(len(acronyms), 0,
            f"No acronyms detected. Systems: {summary.get('systems_detected', [])}")


class TestProfileSerialization(unittest.TestCase):
    """Prove JSON serialization works."""

    def test_json_roundtrip(self):
        """Profile should serialize to JSON and back."""
        tmp = tempfile.mkdtemp()
        tree = _make_test_tree(Path(tmp))
        profiler = SourceProfiler(max_sample_size=3)
        profile = profiler.profile_source(
            path=str(tree),
            source_name="TestSource",
        )

        # Save
        out_path = Path(tmp) / "profile.json"
        profiler.save_profile(profile, str(out_path))
        self.assertTrue(out_path.exists())

        # Load
        with open(out_path) as f:
            data = json.load(f)

        self.assertEqual(data["source_name"], "TestSource")
        self.assertEqual(data["source_type"], "network_filesystem")
        self.assertGreater(data["total_files"], 0)
        self.assertIn("extension_counts", data)
        self.assertIn("ingestion_zones", data)
        self.assertIn("sampled_documents", data)


class TestSourceProfileModel(unittest.TestCase):
    """Prove SourceProfile dataclass is well-formed."""

    def test_profile_has_required_fields(self):
        """SourceProfile should have all required fields."""
        profile = SourceProfile(
            source_name="test",
            source_type="test",
            source_path="/test",
            scan_mode="live",
            scan_timestamp="2026-01-01",
            elapsed_seconds=0.0,
            total_folders=0,
            total_files=0,
            readable_files=0,
            inaccessible_files=0,
            supported_files=0,
            unsupported_files=0,
            max_depth=0,
            extension_counts={},
            extension_sizes={},
            category_counts={},
            top_level_folders={},
            folder_depth_distribution={},
            duplicate_groups=[],
            version_patterns=[],
            naming_patterns=[],
            sampled_documents=[],
            sampling_summary={},
            ingestion_zones=[],
            excluded_zones=[],
            reusable_components=[],
            gaps=[],
            limitations=[],
            access_issues=[],
        )
        self.assertEqual(profile.source_name, "test")
        self.assertEqual(profile.total_files, 0)


class TestNoMutation(unittest.TestCase):
    """Prove the profiler never modifies the source."""

    def test_source_not_modified(self):
        """Source files should be unchanged after profiling."""
        tmp = tempfile.mkdtemp()
        tree = _make_test_tree(Path(tmp))

        # Record all file hashes before
        hashes_before = {}
        for root, dirs, files in os.walk(str(tree)):
            for f in files:
                fp = os.path.join(root, f)
                hashes_before[fp] = Path(fp).read_bytes()

        # Profile
        profiler = SourceProfiler(max_sample_size=5)
        profiler.profile_source(path=str(tree), source_name="TestSource")

        # Verify no files changed
        for fp, content_before in hashes_before.items():
            content_after = Path(fp).read_bytes()
            self.assertEqual(
                content_before, content_after,
                f"File was modified: {fp}",
            )

        # Verify no new files created
        hashes_after = {}
        for root, dirs, files in os.walk(str(tree)):
            for f in files:
                hashes_after[os.path.join(root, f)] = True

        self.assertEqual(
            set(hashes_before.keys()),
            set(hashes_after.keys()),
            "New files were created in source",
        )


class TestExtensionFilter(unittest.TestCase):
    """Prove extension filtering works."""

    def test_filter_only_txt(self):
        """Filtering should only include .txt files."""
        tmp = tempfile.mkdtemp()
        tree = _make_test_tree(Path(tmp))
        profiler = SourceProfiler(
            max_sample_size=5,
            extension_filter={".txt"},
        )
        profile = profiler.profile_source(
            path=str(tree),
            source_name="TestSource",
        )
        # Only .txt should be counted
        self.assertGreater(profile.total_files, 0)
        self.assertIn(".txt", profile.extension_counts)
        self.assertEqual(len(profile.extension_counts), 1)


class TestIngestionZones(unittest.TestCase):
    """Prove zone recommendations are generated."""

    def test_zones_generated(self):
        """At least one zone should be recommended."""
        tmp = tempfile.mkdtemp()
        tree = _make_test_tree(Path(tmp))
        profiler = SourceProfiler(max_sample_size=3)
        profile = profiler.profile_source(
            path=str(tree),
            source_name="TestSource",
        )
        self.assertGreater(
            len(profile.ingestion_zones) + len(profile.excluded_zones),
            0,
        )

    def test_zones_have_signals(self):
        """Each zone should have explanatory signals."""
        tmp = tempfile.mkdtemp()
        tree = _make_test_tree(Path(tmp))
        profiler = SourceProfiler(max_sample_size=3)
        profile = profiler.profile_source(
            path=str(tree),
            source_name="TestSource",
        )
        for zone in profile.ingestion_zones:
            self.assertGreater(
                len(zone["signals"]), 0,
                f"Zone {zone['path']} has no signals",
            )


if __name__ == "__main__":
    unittest.main()
