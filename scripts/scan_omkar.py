"""Read-only scan of \\ina6fs01\Dept_shares\ICS\Omkar\Process Documents"""
import os
import hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime

SOURCE = Path(r"\\ina6fs01\Dept_shares\ICS\Omkar\Process Documents")

SUPPORTED = {".pdf", ".txt", ".md", ".docx", ".xlsx", ".xls", ".csv", ".rst", ".markdown"}

files = []
extensions = Counter()
by_folder = Counter()
unsupported = []
duplicates = Counter()
sizes = {}

for entry in SOURCE.rglob("*"):
    if not entry.is_file():
        continue
    try:
        stat = entry.stat()
        ext = entry.suffix.lower()
        rel = entry.relative_to(SOURCE)
        parts = rel.parts
        folder = parts[0] if len(parts) > 1 else "(root)"

        # Content hash for dedup detection
        sha = hashlib.sha256()
        with open(entry, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        chash = sha.hexdigest()[:12]

        files.append({
            "path": str(entry),
            "relative": str(rel),
            "name": entry.name,
            "extension": ext,
            "size": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "folder": folder,
            "supported": ext in SUPPORTED,
            "hash": chash,
        })

        extensions[ext] += 1
        by_folder[folder] += 1
        duplicates[(entry.name, chash)] += 1
        sizes[ext] = sizes.get(ext, 0) + stat.st_size

        if ext not in SUPPORTED:
            unsupported.append(f"  {entry.name} ({ext})")

    except (OSError, PermissionError) as e:
        print(f"  INACCESSIBLE: {entry} — {e}")

print(f"{'='*60}")
print(f"ICS/OMKAR/PROCESS DOCUMENTS — READ-ONLY SCAN")
print(f"{'='*60}")
print(f"  Source: {SOURCE}")
print(f"  Total files: {len(files)}")
print(f"  Readable: {len(files)}")
print()

print(f"{'Extension':<12} {'Count':>6} {'Size (KB)':>12} {'Supported':>10}")
print("-" * 44)
for ext, count in extensions.most_common():
    kb = sizes.get(ext, 0) / 1024
    ok = "YES" if ext in SUPPORTED else "NO"
    print(f"{ext:<12} {count:>6} {kb:>12,.1f} {ok:>10}")

print(f"\n{'='*60}")
print(f"FILES BY FOLDER")
print(f"{'='*60}")
for folder, count in by_folder.most_common():
    print(f"  {folder:<45} {count:>4}")

# Duplicate detection
dup_groups = {(name, h): cnt for (name, h), cnt in duplicates.items() if cnt > 1}
if dup_groups:
    print(f"\n{'='*60}")
    print(f"DUPLICATE FILES (same name + same content hash)")
    print(f"{'='*60}")
    for (name, h), cnt in sorted(dup_groups.items(), key=lambda x: -x[1]):
        print(f"  {name:<50} x{cnt}")

# Full file listing
print(f"\n{'='*60}")
print(f"FULL FILE LISTING")
print(f"{'='*60}")
for f in sorted(files, key=lambda x: x["relative"]):
    ok = "OK" if f["supported"] else "NO"
    kb = f["size"] / 1024
    print(f"  [{ok}] {kb:>8,.1f} KB  {f['relative']}")
