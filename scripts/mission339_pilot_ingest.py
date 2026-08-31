#!/usr/bin/env python3
"""Mission 3.39 — Phase 2-3: Pilot corpus selection and ingestion.

Selects ~200 representative documents from the accessible network share
and ingests them through KnowledgeFabric to populate the knowledge base.

READ-SAFE: Never modifies the source network share.
"""

import os
import sys
import time
import hashlib
import json
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, '.')

SHARE_ROOT = r"\\ina6fs01\Dept_shares"
SUPPORTED_EXTS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.txt', '.md'}

# Selected pilot directories with priority weighting
PILOT_SELECTIONS = [
    # ICS Process Documents - HIGHEST PRIORITY
    (r"ICS\Omkar", "ICS", "ICS Omkar Process Documents"),
    (r"ICS\Install", "ICS", "ICS Installation"),
    (r"ICS\Audit", "ICS", "ICS Audit"),

    # Service Delivery - ICS and process governance
    (r"Service Delivery\ICS", "ICS", "Service Delivery ICS"),
    (r"Service Delivery\ICS Operations", "ICS", "ICS Operations"),
    (r"Service Delivery\Process Governance", "SPM", "Process Governance"),
    (r"Service Delivery\Install Maintenance", "ICS", "Install Maintenance"),
    (r"Service Delivery\Activities and Processes", "SPM", "Activities and Processes"),
    (r"Service Delivery\Activities with financial impact", "SPM", "Financial Activities"),
    (r"Service Delivery\IBANK Automation", "ICS", "IBANK Automation"),
    (r"Service Delivery\Old Files", "ICS", "Service Delivery Legacy"),

    # ROA - G3 and rate operations
    (r"ROA\G3", "ROA", "ROA G3"),
    (r"ROA\CASPER", "ROA", "CASPER"),
    (r"ROA\CPRMS", "ROA", "CPRMS"),
    (r"ROA\CSS", "ROA", "CSS"),
    (r"ROA\FVRs_CJ", "ROA", "FVRs"),
    (r"ROA\G2", "ROA", "ROA G2"),

    # Install / Configuration
    (r"install\@023", "ICS", "Install @023"),
    (r"install\Audit", "ICS", "Install Audit"),
    (r"install\Install", "ICS", "Install Process"),

    # ICS-DU (data uploads)
    (r"ICS-DU", "ICS", "ICS Data Uploads"),

    # Hyatt Rollout
    (r"Hyatt Rollout\Waves", "SDOPS", "Hyatt Rollout Waves"),
    (r"Hyatt Rollout\was", "SDOPS", "Hyatt Rollout WAS"),
]


def sha256_file(filepath):
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def collect_files_from_dir(dir_path, max_files=15):
    """Collect supported files from a directory, up to max_files."""
    files = []
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in SUPPORTED_EXTS and not entry.name.startswith('~$'):
                            st = entry.stat(follow_symlinks=False)
                            files.append({
                                'path': entry.path,
                                'name': entry.name,
                                'ext': ext,
                                'size': st.st_size,
                                'mtime': st.st_mtime,
                            })
                except Exception:
                    continue
    except (PermissionError, OSError):
        pass

    # Filter: skip very large files (>5MB) for faster pilot ingestion
    files = [f for f in files if f['size'] < 5 * 1024 * 1024]
    # Sort by size (prefer smaller, more readable files for pilot)
    files.sort(key=lambda x: x['size'])

    # Take up to max_files
    return files[:max_files]


def main():
    print("=" * 70)
    print("MISSION 3.39 — PHASE 2-3: PILOT CORPUS SELECTION & INGESTION")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Step 1: Collect files from each pilot directory
    print("\n--- Collecting pilot files ---")
    pilot_files = []
    by_team = {}
    by_folder = {}

    for dir_rel, team, label in PILOT_SELECTIONS:
        dir_path = os.path.join(SHARE_ROOT, dir_rel)
        print(f"\n  [{label}] {dir_rel}", end="", flush=True)

        # For directories that might have subdirectories, scan recursively (depth 2)
        all_files = collect_files_from_dir(dir_path, max_files=10)

        # Also check immediate subdirectories
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        sub_files = collect_files_from_dir(entry.path, max_files=5)
                        all_files.extend(sub_files)
                        if len(all_files) >= 15:
                            break
        except (PermissionError, OSError):
            pass

        # Deduplicate by path
        seen = set()
        unique = []
        for f in all_files:
            if f['path'] not in seen:
                seen.add(f['path'])
                unique.append(f)
        all_files = unique[:15]  # Cap at 15 per directory

        print(f" -> {len(all_files)} files")

        for f in all_files:
            f['team'] = team
            f['folder'] = dir_rel
            f['label'] = label
            pilot_files.append(f)

            by_team.setdefault(team, []).append(f)
            by_folder.setdefault(dir_rel, []).append(f)

    print(f"\n--- Total pilot files collected: {len(pilot_files)} ---")

    # Print summary
    print("\n--- By team ---")
    for team, files in sorted(by_team.items(), key=lambda x: -len(x[1])):
        total_size = sum(f['size'] for f in files)
        print(f"  {team:10s}: {len(files):3d} files, {total_size/1024:.0f} KB")

    print("\n--- By folder ---")
    for folder, files in sorted(by_folder.items()):
        total_size = sum(f['size'] for f in files)
        print(f"  {folder:50s}: {len(files):3d} files, {total_size/1024:.0f} KB")

    # Print file manifest
    print("\n--- File manifest ---")
    for f in pilot_files:
        print(f"  {f['team']:6s} | {f['ext']:6s} | {f['size']/1024:7.1f} KB | {f['path'][:90]}")

    # Step 2: Ingest via KnowledgeFabric
    print("\n" + "=" * 70)
    print("PHASE 3: INGESTING VIA KNOWLEDGEFABRIC")
    print("=" * 70)

    from kurukshetra.knowledge.fabric import KnowledgeFabric

    fabric = KnowledgeFabric()

    ingested = 0
    skipped = 0
    failed = 0
    errors = []
    
    # Limit to 100 files for the pilot
    pilot_files = pilot_files[:100]
    print(f"\nPilot limited to {len(pilot_files)} files for speed.")

    for f in pilot_files:
        print(f"\n  Ingesting: {f['name'][:60]}...", end="", flush=True)
        start = time.time()

        try:
            from pathlib import Path as P
            result = fabric.ingest_file(P(f['path']))
            elapsed = (time.time() - start) * 1000

            if result.change_type == 'none':
                print(f" SKIP (duplicate) {elapsed:.0f}ms")
                skipped += 1
            else:
                chunks = result.chunks_stored if hasattr(result, 'chunks_stored') else '?'
                print(f" OK ({chunks} chunks) {elapsed:.0f}ms")
                ingested += 1

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            err_msg = str(e)[:80]
            print(f" FAIL ({err_msg}) {elapsed:.0f}ms")
            failed += 1
            errors.append({'file': f['name'], 'error': err_msg})

    # Summary
    print("\n" + "=" * 70)
    print("INGESTION SUMMARY")
    print("=" * 70)
    print(f"Ingested: {ingested}")
    print(f"Skipped (duplicates): {skipped}")
    print(f"Failed: {failed}")

    if errors:
        print("\n--- Errors ---")
        for e in errors[:10]:
            print(f"  {e['file']}: {e['error']}")

    # Step 3: Verify database state
    print("\n--- Database state after ingestion ---")
    from kurukshetra.registry.database import get_connection
    conn = get_connection()

    docs = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
    chunks = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
    entities = conn.execute('SELECT COUNT(*) FROM graph_entities').fetchone()[0]
    rels = conn.execute('SELECT COUNT(*) FROM graph_relationships').fetchone()[0]
    ct = conn.execute('SELECT COUNT(*) FROM concept_teams').fetchone()[0]
    dv = conn.execute('SELECT COUNT(*) FROM document_versions').fetchone()[0]
    ds = conn.execute('SELECT COUNT(*) FROM document_state').fetchone()[0]

    print(f"Documents: {docs}")
    print(f"Chunks: {chunks}")
    print(f"Entities: {entities}")
    print(f"Relationships: {rels}")
    print(f"concept_teams: {ct}")
    print(f"document_versions: {dv}")
    print(f"document_state: {ds}")

    # Network share documents
    nw = conn.execute("SELECT COUNT(*) FROM documents WHERE source_path LIKE '%ina6fs01%'").fetchone()[0]
    print(f"Network share docs: {nw}")

    # Team distribution of new docs
    print("\n--- Team distribution (network share docs) ---")
    rows = conn.execute("""
        SELECT team_owner, COUNT(*)
        FROM documents
        WHERE source_path LIKE '%ina6fs01%'
        GROUP BY team_owner
        ORDER BY COUNT(*) DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]}")

    # Save report
    os.makedirs('reports', exist_ok=True)
    report = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'files_collected': len(pilot_files),
        'ingested': ingested,
        'skipped': skipped,
        'failed': failed,
        'errors': errors,
        'db_after': {
            'documents': docs,
            'chunks': chunks,
            'entities': entities,
            'relationships': rels,
            'concept_teams': ct,
            'document_versions': dv,
            'document_state': ds,
            'network_share_docs': nw,
        },
        'team_distribution': {r[0]: r[1] for r in rows},
    }
    with open('reports/mission339_ingestion.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nSaved to reports/mission339_ingestion.json")
    print("Phase 2-3 COMPLETE.")


if __name__ == '__main__':
    main()
