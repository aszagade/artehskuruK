"""
Source Discovery Profiler
=========================

Read-only discovery and profiling of network knowledge sources.

Supports two modes:
  1. Live scan: recursively scan a filesystem path
  2. CSV inventory: analyze a pre-existing CSV inventory file

Outputs structured SourceProfile with:
  - folder/file statistics
  - extension distribution
  - pattern detection
  - content sampling via TextExtractor
  - duplicate/version detection
  - ingestion zone recommendations
  - future connector architecture mapping

READ-ONLY: never modifies the source filesystem.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from kurukshetra.extractors.text_extractor import TextExtractor


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

CATEGORY_MAP = {
    ".pdf": "DOCUMENT",
    ".docx": "DOCUMENT",
    ".doc": "DOCUMENT",
    ".txt": "TEXT",
    ".md": "TEXT",
    ".markdown": "TEXT",
    ".rst": "TEXT",
    ".xlsx": "SPREADSHEET",
    ".xls": "SPREADSHEET",
    ".csv": "DATA",
    ".psv": "DATA",
    ".json": "DATA",
    ".xml": "DATA",
    ".html": "TEXT",
    ".htm": "TEXT",
    ".css": "CODE",
    ".py": "CODE",
    ".pyi": "CODE",
    ".pyc": "CODE",
    ".f90": "CODE",
    ".f": "CODE",
    ".h": "CODE",
    ".lib": "CODE",
    ".sas7bdat": "DATA",
    ".zip": "ARCHIVE",
    ".gz": "ARCHIVE",
    ".tar": "ARCHIVE",
    ".rar": "ARCHIVE",
    ".exe": "APPLICATION",
    ".msi": "APPLICATION",
    ".pbix": "DATA",
    ".mp4": "MEDIA",
    ".mp3": "MEDIA",
    ".jpg": "MEDIA",
    ".png": "MEDIA",
    ".pptx": "DOCUMENT",
    ".ppt": "DOCUMENT",
}

SUPPORTED_BY_EXTRACTOR = TextExtractor.supported_extensions()

# Pattern keywords for folder classification
ZONE_SIGNALS = {
    "HIGH_VALUE_KNOWLEDGE": [
        "process", "document", "workflow", "configuration",
        "manual", "install", "validation", "technical",
        "setup", "guide", "procedure", "standard",
    ],
    "OPERATIONAL_DATA": [
        "input", "output", "logs", "data", "monitor",
        "automation", "script", "code", "test",
    ],
    "LIKELY_NOISE": [
        "temp", "download", "backup", "old", "archive",
        "recycle", "cache", "tmp", "copy",
    ],
    "VERSIONED_ARTIFACTS": [
        "v1", "v2", "v3", "updated", "final", "draft",
        "new", "old", "latest", "2024", "2025", "2026",
    ],
    "PEOPLE_ORGANIZED": [
        # Detected by person-name patterns in folder names
    ],
}


@dataclass
class FileRecord:
    """Lightweight file metadata. Never stores file contents."""
    full_path: str
    relative_path: str
    filename: str
    extension: str
    size: int
    last_modified: str
    creation_time: str
    depth: int
    top_folder: str
    folder_hierarchy: str
    supported: bool
    category: str
    accessible: bool = True
    content_hash: Optional[str] = None  # Only computed for samples


@dataclass
class FolderStats:
    """Aggregated statistics for a folder."""
    path: str
    depth: int
    file_count: int
    total_size: int
    extensions: dict[str, int]
    supported_count: int
    unsupported_count: int
    categories: dict[str, int]
    most_recent_modified: str
    oldest_modified: str


@dataclass
class DuplicateGroup:
    """Group of potentially duplicate files."""
    files: list[str]
    match_type: str  # "same_size", "same_name", "same_hash"
    size: int = 0


@dataclass
class VersionPattern:
    """Detected version pattern in filenames."""
    base_name: str
    versions: list[str]
    pattern_type: str  # "v1/v2", "dated", "numbered", "suffix"


@dataclass
class ContentSample:
    """Result of sampling a document for content analysis."""
    path: str
    extension: str
    extraction_ok: bool
    char_count: int
    pages_sheets: int
    probable_content_type: str
    systems_detected: list[str]
    acronyms_detected: list[str]
    identifiers_detected: list[str]
    team_signals: list[str]
    process_signals: list[str]
    first_preview: str  # Safe metadata preview (100 chars max)
    error: Optional[str] = None


@dataclass
class IngestionZone:
    """Recommended ingestion zone for a folder."""
    path: str
    classification: str
    signals: list[str]
    file_count: int
    supported_count: int
    confidence: float  # 0-1


@dataclass
class SourceProfile:
    """Complete source profile - machine-readable output."""
    source_name: str
    source_type: str
    source_path: str
    scan_mode: str  # "live" or "csv_inventory"
    scan_timestamp: str
    elapsed_seconds: float

    # Inventory
    total_folders: int
    total_files: int
    readable_files: int
    inaccessible_files: int
    supported_files: int
    unsupported_files: int
    max_depth: int

    # Extensions
    extension_counts: dict[str, int]
    extension_sizes: dict[str, float]  # bytes
    category_counts: dict[str, int]

    # Folders
    top_level_folders: dict[str, int]
    folder_depth_distribution: dict[int, int]

    # Patterns
    duplicate_groups: list[dict]
    version_patterns: list[dict]
    naming_patterns: list[str]

    # Content sampling
    sampled_documents: list[dict]
    sampling_summary: dict[str, Any]

    # Zone recommendations
    ingestion_zones: list[dict]
    excluded_zones: list[dict]

    # Architecture
    reusable_components: list[str]
    gaps: list[str]

    # Metadata
    limitations: list[str]
    access_issues: list[str]


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

class SourceProfiler:
    """
    Read-only source discovery profiler.

    Usage:
        profiler = SourceProfiler()
        profile = profiler.profile_source(
            path="\\\\ina6fs01\\Dept_shares\\ICS",
            source_name="ICS",
        )
        profiler.save_profile(profile, "reports/source_profiles/ics.json")
    """

    def __init__(
        self,
        max_sample_size: int = 20,
        extension_filter: Optional[set[str]] = None,
        skip_network_sampling: bool = True,
    ) -> None:
        self.max_sample_size = max_sample_size
        self.extension_filter = extension_filter
        self.skip_network_sampling = skip_network_sampling
        self.extractor = TextExtractor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def profile_source(
        self,
        path: str,
        source_name: str = "unknown",
        csv_inventory: Optional[str] = None,
        csv_folder_access: Optional[str] = None,
    ) -> SourceProfile:
        """
        Profile a source. Either scan live from `path`, or analyze from CSV.
        """
        start = time.time()

        if csv_inventory:
            records = self._load_from_csv(csv_inventory, csv_folder_access, path)
            scan_mode = "csv_inventory"
        else:
            records = self._scan_live(path)
            scan_mode = "live"

        elapsed = time.time() - start

        # Aggregate
        stats = self._aggregate(records)

        # Pattern detection
        dupes = self._detect_duplicates(records)
        versions = self._detect_version_patterns(records)
        naming = self._detect_naming_patterns(records)

        # Content sampling
        samples = self._sample_content(records) if self.max_sample_size > 0 else []
        sample_summary = self._summarize_samples(samples)

        # Zone recommendations
        zones, excluded = self._recommend_zones(records, stats)

        # Architecture mapping
        reusable, gaps = self._map_architecture()

        # Limitations
        limitations = self._identify_limitations(records, scan_mode)

        return SourceProfile(
            source_name=source_name,
            source_type="network_filesystem",
            source_path=path,
            scan_mode=scan_mode,
            scan_timestamp=datetime.now().isoformat(),
            elapsed_seconds=round(elapsed, 1),
            total_folders=stats["total_folders"],
            total_files=stats["total_files"],
            readable_files=stats["readable_files"],
            inaccessible_files=stats["inaccessible_files"],
            supported_files=stats["supported_files"],
            unsupported_files=stats["unsupported_files"],
            max_depth=stats["max_depth"],
            extension_counts=stats["extension_counts"],
            extension_sizes=stats["extension_sizes"],
            category_counts=stats["category_counts"],
            top_level_folders=stats["top_level_folders"],
            folder_depth_distribution=stats["folder_depth_distribution"],
            duplicate_groups=dupes,
            version_patterns=versions,
            naming_patterns=naming,
            sampled_documents=[asdict(s) for s in samples],
            sampling_summary=sample_summary,
            ingestion_zones=[asdict(z) for z in zones],
            excluded_zones=[asdict(z) for z in excluded],
            reusable_components=reusable,
            gaps=gaps,
            limitations=limitations,
            access_issues=stats["access_issues"],
        )

    def save_profile(self, profile: SourceProfile, path: str) -> None:
        """Save profile as JSON."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(asdict(profile), f, indent=2, default=str)

    def print_summary(self, profile: SourceProfile) -> None:
        """Print a concise human-readable summary."""
        p = profile
        print(f"\n{'='*60}")
        print(f"SOURCE DISCOVERY: {p.source_name}")
        print(f"{'='*60}")
        print(f"  Source:   {p.source_path}")
        print(f"  Mode:     {p.scan_mode}")
        print(f"  Scanned:  {p.scan_timestamp}")
        print(f"  Elapsed:  {p.elapsed_seconds}s")
        print(f"\n  Folders:       {p.total_folders:>10,}")
        print(f"  Files:         {p.total_files:>10,}")
        print(f"  Readable:      {p.readable_files:>10,}")
        print(f"  Inaccessible:  {p.inaccessible_files:>10,}")
        print(f"  Supported:     {p.supported_files:>10,}")
        print(f"  Unsupported:   {p.unsupported_files:>10,}")
        print(f"  Max depth:     {p.max_depth:>10}")

        print(f"\n{'='*60}")
        print(f"EXTENSION DISTRIBUTION")
        print(f"{'='*60}")
        for ext, count in sorted(
            p.extension_counts.items(), key=lambda x: -x[1]
        )[:15]:
            mb = p.extension_sizes.get(ext, 0) / (1024 * 1024)
            ok = "OK" if ext in SUPPORTED_BY_EXTRACTOR else "  "
            print(f"  {ext:<12} {count:>10,}  {mb:>10,.1f} MB  {ok}")

        print(f"\n{'='*60}")
        print(f"TOP-LEVEL FOLDERS")
        print(f"{'='*60}")
        for folder, count in sorted(
            p.top_level_folders.items(), key=lambda x: -x[1]
        )[:20]:
            print(f"  {folder:<55} {count:>8,}")

        if p.ingestion_zones:
            print(f"\n{'='*60}")
            print(f"INGESTION ZONE RECOMMENDATIONS")
            print(f"{'='*60}")
            for z in p.ingestion_zones:
                print(f"\n  [{z['classification']}] {z['path']}")
                print(f"    Files: {z['file_count']:,}  Supported: {z['supported_count']:,}")
                for signal in z["signals"][:3]:
                    print(f"    - {signal}")

        if p.version_patterns:
            print(f"\n{'='*60}")
            print(f"VERSION PATTERNS ({len(p.version_patterns)} detected)")
            print(f"{'='*60}")
            for vp in p.version_patterns[:10]:
                print(f"  {vp['base_name'][:60]:<60} [{vp['pattern_type']}]")

        if p.duplicate_groups:
            print(f"\n{'='*60}")
            print(f"DUPLICATE GROUPS ({len(p.duplicate_groups)} detected)")
            print(f"{'='*60}")
            for dg in p.duplicate_groups[:10]:
                files_short = [f.split("\\")[-1][:30] for f in dg["files"][:3]]
                print(f"  [{dg['match_type']}] {', '.join(files_short)}")

        if p.sampled_documents:
            print(f"\n{'='*60}")
            print(f"CONTENT SAMPLING ({len(p.sampled_documents)} documents)")
            print(f"{'='*60}")
            for s in p.sampled_documents:
                name = s["path"].split("\\")[-1][:50]
                ok = "OK" if s["extraction_ok"] else "FAIL"
                print(f"  [{ok}] {name:<50} {s['char_count']:>8,} chars")
                if s["systems_detected"]:
                    print(f"       Systems: {', '.join(s['systems_detected'][:5])}")
                if s["acronyms_detected"]:
                    print(f"       Acronyms: {', '.join(s['acronyms_detected'][:5])}")

        print(f"\n{'='*60}")
        print(f"ARCHITECTURE READINESS")
        print(f"{'='*60}")
        print(f"  Reusable components: {len(p.reusable_components)}")
        for c in p.reusable_components:
            print(f"    + {c}")
        print(f"  Gaps: {len(p.gaps)}")
        for g in p.gaps:
            print(f"    - {g}")

        print(f"\n{'='*60}")
        print(f"LIMITATIONS")
        print(f"{'='*60}")
        for l in p.limitations:
            print(f"  ! {l}")

    # ------------------------------------------------------------------
    # Live scanning
    # ------------------------------------------------------------------

    def _scan_live(self, root: str) -> list[FileRecord]:
        """Recursively scan a filesystem path."""
        records: list[FileRecord] = []
        root_path = Path(root)

        if not root_path.exists():
            raise FileNotFoundError(f"Source path not accessible: {root}")

        for dirpath, dirnames, filenames in os.walk(str(root_path)):
            # Compute depth relative to root
            rel = os.path.relpath(dirpath, str(root_path))
            depth = rel.count(os.sep) + 1 if rel != "." else 0
            top = rel.split(os.sep)[0] if rel != "." else "(root)"

            for fname in filenames:
                full = os.path.join(dirpath, fname)
                try:
                    stat = os.stat(full)
                    ext = os.path.splitext(fname)[1].lower()
                    rel_to_source = os.path.relpath(full, str(root_path))

                    category = CATEGORY_MAP.get(ext, "UNKNOWN")
                    supported = ext in SUPPORTED_BY_EXTRACTOR

                    # Apply extension filter
                    if self.extension_filter and ext not in self.extension_filter:
                        continue

                    records.append(FileRecord(
                        full_path=full,
                        relative_path=rel_to_source,
                        filename=fname,
                        extension=ext,
                        size=stat.st_size,
                        last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        creation_time=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        depth=depth,
                        top_folder=top,
                        folder_hierarchy=rel,
                        supported=supported,
                        category=category,
                    ))
                except (OSError, PermissionError):
                    records.append(FileRecord(
                        full_path=full,
                        relative_path=os.path.relpath(full, str(root_path)),
                        filename=fname,
                        extension=os.path.splitext(fname)[1].lower(),
                        size=0,
                        last_modified="",
                        creation_time="",
                        depth=depth,
                        top_folder=top,
                        folder_hierarchy=rel,
                        supported=False,
                        category="UNKNOWN",
                        accessible=False,
                    ))

        return records

    # ------------------------------------------------------------------
    # CSV inventory loading
    # ------------------------------------------------------------------

    def _load_from_csv(
        self,
        inventory_path: str,
        folder_access_path: Optional[str],
        source_prefix: str,
    ) -> list[FileRecord]:
        """Load file records from a pre-existing CSV inventory."""
        records: list[FileRecord] = []

        # Normalize the prefix for matching
        # CSV stores paths like: \\ina6fs01\Dept_shares\ICS\...
        norm_prefix = source_prefix.replace("/", "\\")
        if not norm_prefix.endswith("\\"):
            norm_prefix += "\\"

        # Load access info if available
        access_map: dict[str, str] = {}
        if folder_access_path and os.path.exists(folder_access_path):
            with open(folder_access_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    access_map[row.get("Path", "")] = row.get("Access", "UNKNOWN")

        with open(inventory_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                full_path = row.get("FullName", "")
                dept = row.get("TopDepartment", "")
                rel = row.get("RelativePath", "")

                # Match by department or path prefix
                is_match = False
                if dept and rel.startswith(dept + "\\"):
                    # Check if this dept matches our source
                    source_dept = norm_prefix.rstrip("\\").split("\\")[-1]
                    if dept == source_dept:
                        is_match = True
                elif full_path.startswith(norm_prefix.replace("\\\\", "\\\\")):
                    is_match = True

                if not is_match:
                    continue

                ext = row.get("Extension", "").lower()
                if self.extension_filter and ext not in self.extension_filter:
                    continue

                size = int(row.get("Length", 0) or 0)
                last_mod = row.get("LastWriteTime", "")
                creation = row.get("CreationTime", "")
                depth = int(row.get("Depth", 0) or 0)
                hierarchy = row.get("RelativePath", "")

                parts = hierarchy.split("\\")
                top = parts[0] if parts else "(root)"
                folder_part = "\\".join(parts[:-1]) if len(parts) > 1 else "(root)"

                accessible = access_map.get(full_path, "UNKNOWN") != "INACCESSIBLE"

                records.append(FileRecord(
                    full_path=full_path,
                    relative_path=hierarchy,
                    filename=row.get("Name", ""),
                    extension=ext,
                    size=size,
                    last_modified=last_mod,
                    creation_time=creation,
                    depth=depth,
                    top_folder=top,
                    folder_hierarchy=folder_part,
                    supported=ext in SUPPORTED_BY_EXTRACTOR,
                    category=CATEGORY_MAP.get(ext, "UNKNOWN"),
                    accessible=accessible,
                ))

        return records

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(self, records: list[FileRecord]) -> dict[str, Any]:
        """Compute aggregate statistics from file records."""
        ext_counts: Counter = Counter()
        ext_sizes: dict[str, int] = defaultdict(int)
        cat_counts: Counter = Counter()
        top_folders: Counter = Counter()
        depth_dist: Counter = Counter()
        access_issues: list[str] = []

        total_folders = set()
        max_depth = 0
        readable = 0
        inaccessible = 0

        for r in records:
            ext_counts[r.extension] += 1
            ext_sizes[r.extension] += r.size
            cat_counts[r.category] += 1
            top_folders[r.top_folder] += 1
            depth_dist[r.depth] += 1
            max_depth = max(max_depth, r.depth)

            # Track unique folders
            folder = r.folder_hierarchy
            parts = folder.split("\\")
            for i in range(len(parts)):
                total_folders.add("\\".join(parts[: i + 1]))

            if r.accessible:
                readable += 1
            else:
                inaccessible += 1
                if len(access_issues) < 20:
                    access_issues.append(r.relative_path)

        supported = sum(1 for r in records if r.supported)

        return {
            "total_folders": len(total_folders),
            "total_files": len(records),
            "readable_files": readable,
            "inaccessible_files": inaccessible,
            "supported_files": supported,
            "unsupported_files": len(records) - supported,
            "max_depth": max_depth,
            "extension_counts": dict(ext_counts.most_common()),
            "extension_sizes": dict(ext_sizes),
            "category_counts": dict(cat_counts),
            "top_level_folders": dict(top_folders.most_common(50)),
            "folder_depth_distribution": dict(sorted(depth_dist.items())),
            "access_issues": access_issues,
        }

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def _detect_duplicates(self, records: list[FileRecord]) -> list[dict]:
        """Detect potential duplicates by name or size."""
        groups: list[dict] = []

        # Same filename in different locations
        by_name: dict[str, list[str]] = defaultdict(list)
        for r in records:
            if r.filename:
                by_name[r.filename].append(r.full_path)

        for name, paths in by_name.items():
            if len(paths) > 1:
                groups.append({
                    "files": paths[:10],
                    "match_type": "same_name",
                    "size": 0,
                })

        # Same size files (potential content duplicates) — only for text docs
        by_size: dict[int, list[str]] = defaultdict(list)
        for r in records:
            if r.size > 100 and r.supported:
                by_size[r.size].append(r.full_path)

        for size, paths in by_size.items():
            if 2 <= len(paths) <= 10:
                groups.append({
                    "files": paths[:5],
                    "match_type": "same_size",
                    "size": size,
                })

        return groups[:50]

    # ------------------------------------------------------------------
    # Version pattern detection
    # ------------------------------------------------------------------

    def _detect_version_patterns(self, records: list[FileRecord]) -> list[dict]:
        """Detect version patterns in filenames."""
        patterns: list[dict] = []

        # Pattern: base_v1, base_v2, base_v3
        version_re = re.compile(r"^(.+?)[_\-\s]?(v\d+|V\d+)[_\-\s]?", re.IGNORECASE)
        # Pattern: base_2024, base_2025, base_2026
        year_re = re.compile(r"^(.+?)[_\-\s]?(20[12]\d)[_\-\s]?", re.IGNORECASE)
        # Pattern: base_updated, base_final, base_draft
        suffix_re = re.compile(
            r"^(.+?)[_\-\s]?(updated|final|draft|new|old|latest|copy|backup)[_\-\s]?\.\w+$",
            re.IGNORECASE,
        )

        base_groups: dict[str, list[str]] = defaultdict(list)

        for r in records:
            name = r.filename
            m = version_re.match(name)
            if m:
                base_groups[("versioned", m.group(1))].append(name)
                continue
            m = year_re.match(name)
            if m:
                base_groups[("dated", m.group(1))].append(name)
                continue
            m = suffix_re.match(name)
            if m:
                base_groups[("suffixed", m.group(1))].append(name)

        for (ptype, base), files in base_groups.items():
            if len(files) > 1:
                patterns.append({
                    "base_name": base,
                    "versions": files[:10],
                    "pattern_type": ptype,
                })

        return sorted(patterns, key=lambda x: -len(x["versions"]))[:30]

    # ------------------------------------------------------------------
    # Naming pattern detection
    # ------------------------------------------------------------------

    def _detect_naming_patterns(self, records: list[FileRecord]) -> list[str]:
        """Detect common naming patterns."""
        patterns: list[str] = []

        # Check for property/hotel naming convention
        hotel_pattern = re.compile(
            r"^(?:\d{6,8}_)?([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)", re.IGNORECASE
        )
        hotels: Counter = Counter()
        for r in records:
            m = hotel_pattern.match(r.filename)
            if m:
                hotels[m.group(1)] += 1

        if len(hotels) > 5:
            top_hotels = [f"{n}({c})" for n, c in hotels.most_common(5)]
            patterns.append(f"Hotel/property naming: {', '.join(top_hotels)}")

        # Check for ID-based naming (6-8 digit prefixes)
        id_pattern = re.compile(r"^(\d{6,8})_")
        ids: Counter = Counter()
        for r in records:
            m = id_pattern.match(r.filename)
            if m:
                ids[m.group(1)] += 1
        if len(ids) > 5:
            patterns.append(f"ID-prefixed files: {len(ids)} unique IDs, {sum(ids.values())} files")

        # Check for SFDC workflow naming
        sfdc_count = sum(1 for r in records if "SFDC" in r.filename.upper() or "sfdc" in r.filename.lower())
        if sfdc_count > 5:
            patterns.append(f"SFDC workflow documents: {sfdc_count} files")

        # Check for person-name folders
        person_folders: Counter = Counter()
        for r in records:
            parts = r.folder_hierarchy.split("\\")
            for part in parts:
                if re.match(r"^[A-Z][a-z]+(?:'s)?$", part):
                    person_folders[part] += 1
        if person_folders:
            top_persons = [f"{n}({c})" for n, c in person_folders.most_common(5)]
            patterns.append(f"Person-organized folders: {', '.join(top_persons)}")

        return patterns

    # ------------------------------------------------------------------
    # Content sampling
    # ------------------------------------------------------------------

    def _sample_content(self, records: list[FileRecord]) -> list[ContentSample]:
        """Sample a small number of documents for content analysis."""
        samples: list[ContentSample] = []

        # Select samples: spread across extensions and folders
        supported = [r for r in records if r.supported and r.accessible and r.size > 0]
        if not supported:
            return samples

        # Prioritize: different extensions, different top folders
        by_ext_folder: dict[tuple, list[FileRecord]] = defaultdict(list)
        for r in supported:
            key = (r.extension, r.top_folder)
            by_ext_folder[key].append(r)

        # Sample from each unique (extension, folder) pair, up to max
        selected: list[FileRecord] = []
        for key in sorted(by_ext_folder.keys()):
            files = sorted(by_ext_folder[key], key=lambda r: -r.size)
            selected.append(files[0])  # Largest file from each combo
            if len(selected) >= self.max_sample_size:
                break

        # Fill remaining with random spread
        remaining = [r for r in supported if r not in selected]
        remaining.sort(key=lambda r: -r.size)
        for r in remaining:
            if len(selected) >= self.max_sample_size:
                break
            selected.append(r)

        for r in selected[: self.max_sample_size]:
            sample = self._analyze_sample(r)
            samples.append(sample)

        return samples

    def _analyze_sample(self, record: FileRecord) -> ContentSample:
        """Extract and analyze a single document sample."""
        path = Path(record.full_path)
        extraction_ok = False
        char_count = 0
        pages_sheets = 0
        content_type = "unknown"
        systems = []
        acronyms = []
        identifiers = []
        team_signals = []
        process_signals = []
        preview = ""
        error = None

        try:
            text = self.extractor.extract(path)
            if text is not None:
                extraction_ok = True
                char_count = len(text)
                preview = text[:100].replace("\n", " ").strip()

                # Classify content type
                if record.extension == ".xlsx":
                    content_type = "spreadsheet"
                    pages_sheets = text.count("--- Sheet:")
                elif record.extension == ".pdf":
                    content_type = "pdf_document"
                    pages_sheets = text.count("\f") + 1
                elif record.extension == ".docx":
                    content_type = "word_document"
                elif record.extension in (".txt", ".md"):
                    content_type = "text"
                elif record.extension == ".csv":
                    content_type = "tabular_data"
                else:
                    content_type = "other"

                # Entity detection (basic regex-based)
                systems = self._detect_systems(text)
                acronyms = self._detect_acronyms(text)
                identifiers = self._detect_identifiers(text)
                team_signals = self._detect_team_signals(text)
                process_signals = self._detect_process_signals(text)
            else:
                error = "Extraction returned None (unsupported format)"
        except Exception as e:
            error = str(e)[:200]

        return ContentSample(
            path=record.full_path,
            extension=record.extension,
            extraction_ok=extraction_ok,
            char_count=char_count,
            pages_sheets=pages_sheets,
            probable_content_type=content_type,
            systems_detected=systems,
            acronyms_detected=acronyms,
            identifiers_detected=identifiers,
            team_signals=team_signals,
            process_signals=process_signals,
            first_preview=preview,
            error=error,
        )

    def _detect_systems(self, text: str) -> list[str]:
        """Detect known system names in text."""
        known_systems = [
            "G3", "RMS", "NGI", "SFDC", "Salesforce", "Datadog",
            "FDS", "Opera", "IDeaS", "Demand360", "D360",
            "SFTP", "EDF", "BDE", "CRM", "STR", "PMS",
            "BMR", "RDC", "DV", "CCFG", "NOVA",
        ]
        found = []
        text_upper = text.upper()
        for sys in known_systems:
            if re.search(r"\b" + re.escape(sys.upper()) + r"\b", text_upper):
                found.append(sys)
        return sorted(set(found))

    def _detect_acronyms(self, text: str) -> list[str]:
        """Detect 2-5 letter ALL CAPS acronyms."""
        acronyms = re.findall(r"\b([A-Z]{2,5})\b", text)
        # Filter common English words
        stopwords = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "DID", "GET", "LET", "SAY", "SHE", "TOO", "USE", "DAD", "MOM", "YES", "TRY", "ASK", "MAY", "JOB", "LOT"}
        return sorted(set(a for a in acronyms if a not in stopwords))[:20]

    def _detect_identifiers(self, text: str) -> list[str]:
        """Detect ticket numbers, IDs, project codes."""
        ids = set()
        # 6-8 digit IDs
        ids.update(re.findall(r"\b(\d{6,8})\b", text))
        # Project codes like NOVA-742, PRJ-001
        ids.update(re.findall(r"\b([A-Z]{2,}-\d{3,})\b", text))
        return sorted(ids)[:10]

    def _detect_team_signals(self, text: str) -> list[str]:
        """Detect team/dept signals in text."""
        team_keywords = [
            "ICS", "SDOPS", "SPM", "CPM", "ROA", "HR", "IT",
            "install", "data verification", "technical verification",
            "forecast", "audit", "monitoring",
        ]
        found = []
        text_lower = text.lower()
        for kw in team_keywords:
            if kw.lower() in text_lower:
                found.append(kw)
        return sorted(set(found))[:10]

    def _detect_process_signals(self, text: str) -> list[str]:
        """Detect process/workflow signals."""
        process_keywords = [
            "configuration", "installation", "workflow", "migration",
            "validation", "verification", "monitoring", "automation",
            "discrepancy", "pricing", "evaluation", "setup",
            "data feed", "integration", "testing", "deployment",
        ]
        found = []
        text_lower = text.lower()
        for kw in process_keywords:
            if kw in text_lower:
                found.append(kw)
        return sorted(set(found))[:10]

    def _summarize_samples(self, samples: list[ContentSample]) -> dict:
        """Summarize content sampling results."""
        if not samples:
            return {"count": 0}

        ok = sum(1 for s in samples if s.extraction_ok)
        all_systems = set()
        all_acronyms = set()
        all_teams = set()
        all_processes = set()

        for s in samples:
            all_systems.update(s.systems_detected)
            all_acronyms.update(s.acronyms_detected)
            all_teams.update(s.team_signals)
            all_processes.update(s.process_signals)

        return {
            "count": len(samples),
            "successful_extractions": ok,
            "systems_detected": sorted(all_systems),
            "acronyms_detected": sorted(all_acronyms),
            "team_signals": sorted(all_teams),
            "process_signals": sorted(all_processes),
        }

    # ------------------------------------------------------------------
    # Zone recommendations
    # ------------------------------------------------------------------

    def _recommend_zones(
        self, records: list[FileRecord], stats: dict
    ) -> tuple[list[IngestionZone], list[IngestionZone]]:
        """Recommend ingestion zones based on deterministic evidence."""
        zones: list[IngestionZone] = []
        excluded: list[IngestionZone] = []

        # Group files by 2-level folder path
        folder_files: dict[str, list[FileRecord]] = defaultdict(list)
        for r in records:
            parts = r.relative_path.split("\\")
            key = "\\".join(parts[:2]) if len(parts) >= 2 else "(root)"
            folder_files[key].append(r)

        for folder_path, files in folder_files.items():
            signals: list[str] = []
            supported = sum(1 for f in files if f.supported)
            total = len(files)
            supported_ratio = supported / total if total > 0 else 0

            # Analyze extension mix
            exts = Counter(f.extension for f in files)
            doc_ratio = sum(
                exts.get(e, 0) for e in [".pdf", ".docx", ".doc", ".txt", ".md"]
            ) / total if total > 0 else 0
            code_ratio = sum(
                exts.get(e, 0) for e in [".py", ".pyc", ".pyi", ".h", ".f90"]
            ) / total if total > 0 else 0
            data_ratio = sum(
                exts.get(e, 0) for e in [".sas7bdat", ".csv", ".xlsx"]
            ) / total if total > 0 else 0

            # Classify
            classification = "REVIEW_REQUIRED"
            confidence = 0.5

            if doc_ratio > 0.3:
                classification = "HIGH_VALUE_KNOWLEDGE"
                signals.append(f"High document ratio ({doc_ratio:.0%})")
                confidence = min(0.9, 0.5 + doc_ratio)
            elif code_ratio > 0.5:
                classification = "OPERATIONAL_DATA"
                signals.append(f"High code ratio ({code_ratio:.0%})")
                confidence = 0.7
            elif data_ratio > 0.7:
                classification = "OPERATIONAL_DATA"
                signals.append(f"High data/automation ratio ({data_ratio:.0%})")
                confidence = 0.6

            # Check for noise signals
            folder_lower = folder_path.lower()
            for zone_type, keywords in ZONE_SIGNALS.items():
                for kw in keywords:
                    if kw in folder_lower:
                        if zone_type == "LIKELY_NOISE":
                            classification = "LIKELY_NOISE"
                            signals.append(f"Noise signal: '{kw}' in path")
                            confidence = 0.7
                        elif zone_type == "VERSIONED_ARTIFACTS":
                            signals.append(f"Versioned content: '{kw}'")
                        elif zone_type == "PEOPLE_ORGANIZED":
                            signals.append("Person-organized folder")

            # File count signal
            if total > 1000:
                signals.append(f"Large collection ({total:,} files)")
            if supported_ratio > 0.5:
                signals.append(f"{supported_ratio:.0%} files are ingestible")

            zone = IngestionZone(
                path=folder_path,
                classification=classification,
                signals=signals,
                file_count=total,
                supported_count=supported,
                confidence=confidence,
            )

            if classification == "LIKELY_NOISE":
                excluded.append(zone)
            else:
                zones.append(zone)

        # Sort by confidence and file count
        zones.sort(key=lambda z: (-z.confidence, -z.file_count))

        return zones[:20], excluded[:10]

    # ------------------------------------------------------------------
    # Architecture mapping
    # ------------------------------------------------------------------

    def _map_architecture(self) -> tuple[list[str], list[str]]:
        """Map existing components and identify gaps."""
        reusable = [
            "TextExtractor (PDF, DOCX, XLSX, XLS, TXT, MD, CSV)",
            "IngestionPipeline (extract -> register -> classify -> chunk -> persist -> graph)",
            "DocumentRegistrar (SHA-256 dedup, provenance storage)",
            "TeamClassifier (OrgMap keyword matching)",
            "ChunkRepository (DuckDB persistence)",
            "GraphRegistry (entity/relationship/evidence persistence)",
            "GlossaryManager (unknown term detection)",
            "DatabaseBM25Retriever (BM25 text search)",
            "VectorRetriever (BGE embeddings)",
            "StatusTracker (ingestion lifecycle monitoring)",
            "InboxWatcher (file detection + movement)",
            "documents.source_path column (provenance)",
            "documents.sha256 column (dedup)",
            "documents.last_updated column (freshness)",
        ]

        gaps = [
            "Source abstraction: no universal SOURCE interface for FS/Salesforce/Confluence/etc.",
            "Folder-aware watcher: current watcher is flat (no subfolder tracking)",
            "Incremental change detection: no mtime/size-based delta scan",
            "Batch ingestion orchestration: no priority queue for large sources",
            "Network path normalization: UNC paths not standardized",
            "File version management: no CURRENT/HISTORICAL distinction",
            "Source-specific filtering: no per-source include/exclude rules",
            "Cross-source dedup: same doc in ICS share + inbox not detected",
            "Large-scale embedding: no batch embedding for 40K+ files",
            "Graph entity dedup across sources: entity IDs not globally unique",
            "Source health monitoring: no access/latency tracking",
            "Connector registry: no plugin architecture for future connectors",
        ]

        return reusable, gaps

    def _identify_limitations(
        self, records: list[FileRecord], scan_mode: str
    ) -> list[str]:
        """Identify limitations of the current scan."""
        limitations = []

        if scan_mode == "csv_inventory":
            limitations.append(
                "CSV inventory may not reflect current filesystem state"
            )

        unsupported = sum(1 for r in records if not r.supported)
        if unsupported > 0:
            limitations.append(
                f"{unsupported:,} files cannot be extracted "
                f"(no TextExtractor support)"
            )

        sas_count = sum(1 for r in records if r.extension == ".sas7bdat")
        if sas_count > 0:
            limitations.append(
                f"{sas_count:,} SAS data files not supported "
                f"(would need SAS reader)"
            )

        py_count = sum(
            1 for r in records if r.extension in (".py", ".pyc", ".pyi")
        )
        if py_count > 0:
            limitations.append(
                f"{py_count:,} Python files (code, not knowledge documents)"
            )

        limitations.append(
            "Content sampling is limited to metadata extraction, "
            "not full semantic analysis"
        )
        limitations.append(
            "Entity extraction is regex-based only "
            "(known system patterns, not AI-driven discovery)"
        )

        return limitations
