#!/usr/bin/env python3
"""Mission 3.39 — Phase 1b: Focused scan of high-value directories.
Depth 3 max, skip large person-name subtrees.
"""

import os
import time
import json
from collections import defaultdict

SHARE_ROOT = r"\\ina6fs01\Dept_shares"
SUPPORTED_EXTS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.txt', '.md', '.markdown', '.rtf', '.html', '.htm', '.xml', '.json'}

# Directories to scan with their max depth
SCAN_CONFIG = [
    (r"ICS", 4),
    (r"Service Delivery", 3),
    (r"ROA", 2),       # shallow - has 71 subdirs
    (r"install", 2),
    (r"Hyatt Rollout", 2),
    (r"PST", 2),       # shallow - has 32 subdirs
    (r"ICS-DU", 1),
]


def scan_recursive(path, max_depth=3, current_depth=0):
    files = []
    errors = []
    if current_depth > max_depth:
        return files, errors

    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    name = entry.name
                    if entry.is_dir(follow_symlinks=False):
                        sub_files, sub_errors = scan_recursive(
                            os.path.join(path, name), max_depth, current_depth + 1
                        )
                        files.extend(sub_files)
                        errors.extend(sub_errors)
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            st = entry.stat(follow_symlinks=False)
                            ext = os.path.splitext(name)[1].lower()
                            rel_path = os.path.relpath(os.path.join(path, name), SHARE_ROOT)
                            files.append({
                                'name': name,
                                'ext': ext,
                                'size': st.st_size,
                                'mtime': st.st_mtime,
                                'rel_path': rel_path,
                                'supported': ext in SUPPORTED_EXTS,
                            })
                        except Exception as e:
                            errors.append(f"{name}: {e}")
                except Exception as e:
                    errors.append(f"entry: {e}")
    except PermissionError:
        errors.append(f"PERMISSION DENIED: {path}")
    except OSError as e:
        errors.append(f"OS error: {e}")

    return files, errors


def main():
    print("=" * 70)
    print("MISSION 3.39 — PHASE 1b: DEEP SCAN")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    all_supported = {}
    summary = {}

    for d, max_d in SCAN_CONFIG:
        dpath = os.path.join(SHARE_ROOT, d)
        print(f"\n--- {d} (depth {max_d}) ---", flush=True)
        start = time.time()
        files, errors = scan_recursive(dpath, max_depth=max_d)
        elapsed = time.time() - start

        supported = [f for f in files if f['supported']]
        sup_size = sum(f['size'] for f in supported)

        summary[d] = {
            'total': len(files),
            'supported': len(supported),
            'errors': len(errors),
            'size_mb': sup_size / (1024*1024),
            'time': elapsed,
        }

        ext_counts = defaultdict(int)
        for f in files:
            ext_counts[f['ext']] += 1

        print(f"  {len(files)} total, {len(supported)} supported, {len(errors)} errors, {sup_size/(1024*1024):.1f} MB, {elapsed:.1f}s")
        print(f"  Exts: {dict(sorted(ext_counts.items(), key=lambda x: -x[1])[:8])}")

        all_supported[d] = supported

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_supported = 0
    total_size = 0
    for d, s in summary.items():
        total_supported += s['supported']
        total_size += s['size_mb']
        print(f"  {d:25s}: {s['supported']:4d} files, {s['size_mb']:.1f} MB")

    print(f"\n  TOTAL: {total_supported} supported files, {total_size:.1f} MB")

    # Team distribution
    teams = defaultdict(lambda: {'count': 0, 'size': 0})
    for d, files in all_supported.items():
        for f in files:
            rel = f['rel_path']
            if 'ICS' in rel.split(os.sep)[0]:
                team = 'ICS'
            elif rel.startswith('Service Delivery'):
                team = 'Service Delivery'
            elif rel.startswith('ROA'):
                team = 'ROA'
            elif rel.startswith('install'):
                team = 'Install'
            elif rel.startswith('Hyatt'):
                team = 'Hyatt'
            elif rel.startswith('PST'):
                team = 'PST'
            else:
                team = 'Other'
            teams[team]['count'] += 1
            teams[team]['size'] += f['size']

    print("\n--- By team ---")
    for team, info in sorted(teams.items(), key=lambda x: -x[1]['count']):
        print(f"  {team:25s}: {info['count']:4d} files, {info['size']/(1024*1024):.1f} MB")

    # Save full file list for ingestion
    os.makedirs('reports', exist_ok=True)
    all_files_flat = []
    for d, files in all_supported.items():
        for f in files:
            all_files_flat.append(f)

    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'summary': summary,
        'teams': {k: {'count': v['count'], 'size_mb': v['size']/(1024*1024)} for k, v in teams.items()},
        'total_supported': total_supported,
        'total_size_mb': total_size,
        'file_manifest': [{'rel_path': f['rel_path'], 'name': f['name'], 'ext': f['ext'], 'size': f['size']} for f in all_files_flat],
    }

    with open('reports/mission339_deep_scan.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nSaved to reports/mission339_deep_scan.json ({len(all_files_flat)} files)")
    print("Phase 1b COMPLETE.")


if __name__ == '__main__':
    main()
