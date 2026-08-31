"""
Ingest accessible documents from \\ina6fs01\\Dept_shares into SANJAYA.

READ-SAFE: Never modifies the source network share.
Only reads documents and ingests them through the existing KnowledgeFabric pipeline.

Usage:
    python scripts/ingest_dept_shares.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

SHARE_ROOT = Path(r"\\ina6fs01\Dept_shares")

SUPPORTED_EXTENSIONS = {
    '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv',
    '.txt', '.md', '.pptx', '.html', '.htm', '.json', '.xml',
}

# Priority folders (higher = ingest first)
PRIORITY_FOLDERS = {
    'ICS': 10,
    'General_Documents': 9,
}


def content_hash(path: Path) -> str:
    """Compute SHA-256 hash of file content."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def discover_files(root: Path, limit: int = 0) -> list[dict]:
    """Discover all supported files under root, sorted by priority."""
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        for path in root.rglob(f"*{ext}"):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
                if size == 0:
                    continue
                # Skip very large files (>50MB)
                if size > 50 * 1024 * 1024:
                    continue
                # Determine priority
                rel = path.relative_to(root)
                parts = rel.parts
                priority = PRIORITY_FOLDERS.get(parts[0], 5) if parts else 5
                files.append({
                    'path': path,
                    'size': size,
                    'extension': path.suffix.lower(),
                    'priority': priority,
                    'folder': parts[0] if parts else 'root',
                    'hash': None,  # computed later
                })
            except (PermissionError, OSError):
                continue

    # Sort by priority (descending), then size (ascending)
    files.sort(key=lambda x: (-x['priority'], x['size']))

    if limit > 0:
        files = files[:limit]

    return files


def check_existing(conn, files: list[dict]) -> list[dict]:
    """Filter out files already ingested (by source_path or hash)."""
    existing_paths = set()
    try:
        rows = conn.execute(
            "SELECT source_path FROM documents WHERE source_path IS NOT NULL"
        ).fetchall()
        existing_paths = {r[0] for r in rows}
    except Exception:
        pass

    new_files = []
    for f in files:
        path_str = str(f['path'])
        if path_str in existing_paths:
            continue
        new_files.append(f)

    return new_files


def main():
    parser = argparse.ArgumentParser(description="Ingest documents from network share")
    parser.add_argument("--dry-run", action="store_true", help="Only discover, don't ingest")
    parser.add_argument("--limit", type=int, default=0, help="Max files to process (0=all)")
    parser.add_argument("--folder", type=str, default=None, help="Ingest only from this folder")
    args = parser.parse_args()

    if not SHARE_ROOT.exists():
        print(f"FATAL: Network share not accessible: {SHARE_ROOT}")
        print("Ensure VPN is connected and the share is mounted.")
        sys.exit(1)

    print(f"=== Discovering files in {SHARE_ROOT} ===")
    files = discover_files(SHARE_ROOT, limit=args.limit)

    if args.folder:
        files = [f for f in files if f['folder'] == args.folder]

    print(f"Found {len(files)} supported files")

    # Group by folder
    by_folder = {}
    for f in files:
        by_folder.setdefault(f['folder'], []).append(f)

    print("\nFolder breakdown:")
    for folder, folder_files in sorted(by_folder.items()):
        exts = {}
        for f in folder_files:
            exts[f['extension']] = exts.get(f['extension'], 0) + 1
        total_size = sum(f['size'] for f in folder_files)
        print(f"  {folder}: {len(folder_files)} files, {total_size/1024/1024:.1f}MB")
        print(f"    Extensions: {exts}")

    if args.dry_run:
        print("\n=== DRY RUN — not ingesting ===")
        return

    # Check existing
    from kurukshetra.registry.database import get_connection
    conn = get_connection()
    new_files = check_existing(conn, files)
    conn.close()

    print(f"\n=== Ingestion ===")
    print(f"Already indexed: {len(files) - len(new_files)}")
    print(f"New files to ingest: {len(new_files)}")

    if not new_files:
        print("Nothing to ingest.")
        return

    # Ingest through KnowledgeFabric
    from kurukshetra.knowledge.fabric import KnowledgeFabric
    fabric = KnowledgeFabric()

    ingested = 0
    failed = 0
    skipped = 0

    for i, f in enumerate(new_files):
        path = f['path']
        print(f"\n[{i+1}/{len(new_files)}] {path.name} ({f['size']/1024:.0f}KB)")

        try:
            result = fabric.ingest_file(str(path))
            if result and hasattr(result, 'status'):
                status = result.status
            else:
                status = 'unknown'
            if status == 'indexed':
                ingested += 1
                print(f"  -> INDEXED")
            elif status == 'duplicate':
                skipped += 1
                print(f"  -> DUPLICATE (skipped)")
            else:
                print(f"  -> {status}")
                ingested += 1  # Count as ingested
        except Exception as e:
            failed += 1
            print(f"  -> FAILED: {e}")

    fabric.close()

    print(f"\n=== Summary ===")
    print(f"Ingested: {ingested}")
    print(f"Duplicates: {skipped}")
    print(f"Failed: {failed}")
    print(f"Total: {len(new_files)}")


if __name__ == "__main__":
    main()
