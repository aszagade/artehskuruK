#!/usr/bin/env python3
"""Mission 3.39 — Phase 1: Quick top-level access discovery.
Scans only depth 1 (immediate children of Dept_shares).
"""

import os
import sys
import time
import json
from collections import defaultdict

SHARE_ROOT = r"\\ina6fs01\Dept_shares"
SUPPORTED_EXTS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.txt', '.md', '.markdown', '.rtf', '.html', '.htm', '.xml', '.json'}


def scan_one_level(path):
    """Scan one level: return (files, subdirs, errors)."""
    files = []
    subdirs = []
    errors = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    name = entry.name
                    is_dir = entry.is_dir(follow_symlinks=False)
                    if is_dir:
                        subdirs.append(name)
                    else:
                        try:
                            st = entry.stat(follow_symlinks=False)
                            files.append({'name': name, 'ext': os.path.splitext(name)[1].lower(), 'size': st.st_size})
                        except Exception as e:
                            errors.append(f"{name}: {e}")
                except Exception as e:
                    errors.append(f"entry: {e}")
    except PermissionError:
        errors.append("PERMISSION DENIED")
    except OSError as e:
        errors.append(str(e))
    return files, subdirs, errors


def main():
    print("=" * 70)
    print("MISSION 3.39 — PHASE 1: QUICK ACCESS DISCOVERY")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Scan root
    print(f"\nScanning root: {SHARE_ROOT}")
    root_files, root_dirs, root_errors = scan_one_level(SHARE_ROOT)
    if root_errors and not root_dirs:
        print(f"FATAL: {root_errors}")
        sys.exit(1)

    print(f"Root: {len(root_dirs)} dirs, {len(root_files)} files, {len(root_errors)} errors")

    # For each top-level dir, scan depth 2 (its immediate children)
    results = {}
    for d in sorted(root_dirs):
        dpath = os.path.join(SHARE_ROOT, d)
        print(f"\n  [{d}]", end="", flush=True)
        start = time.time()
        files, subdirs, errors = scan_one_level(dpath)
        elapsed = time.time() - start

        supported = sum(1 for f in files if f['ext'] in SUPPORTED_EXTS)
        total_size = sum(f['size'] for f in files)

        print(f" {len(files)} files ({supported} supported), {len(subdirs)} subdirs, {elapsed:.1f}s")
        if errors:
            for e in errors[:3]:
                print(f"    ERR: {e}")

        # Store result
        results[d] = {
            'files': files,
            'subdirs': subdirs,
            'errors': errors,
            'supported': supported,
            'total_size': total_size,
        }

        # Also scan depth 2 subdirs (their immediate children)
        for sd in sorted(subdirs)[:20]:  # limit to 20 subdirs
            sdpath = os.path.join(dpath, sd)
            sd_files, sd_subdirs, sd_errors = scan_one_level(sdpath)
            sd_supported = sum(1 for f in sd_files if f['ext'] in SUPPORTED_EXTS)
            sd_size = sum(f['size'] for f in sd_files)
            results[f"{d}/{sd}"] = {
                'files': sd_files,
                'subdirs': sd_subdirs,
                'errors': sd_errors,
                'supported': sd_supported,
                'total_size': sd_size,
            }
            if sd_errors:
                print(f"    [{sd}] ERR: {sd_errors[:2]}")
            elif sd_files or sd_subdirs:
                print(f"    [{sd}] {len(sd_files)} files ({sd_supported} sup), {len(sd_subdirs)} subdirs")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_files = 0
    total_supported = 0
    total_size = 0
    ext_counts = defaultdict(int)

    for key, res in results.items():
        for f in res['files']:
            total_files += 1
            total_size += f['size']
            ext_counts[f['ext']] += 1
            if f['ext'] in SUPPORTED_EXTS:
                total_supported += 1

    print(f"\nDiscovered directories: {len([k for k in results if '/' not in k])}")
    print(f"Discovered subdirectories: {len([k for k in results if '/' in k])}")
    print(f"Total files: {total_files}")
    print(f"Supported files: {total_supported}")
    print(f"Total size: {total_size / (1024*1024):.1f} MB")

    print("\n--- Extension distribution ---")
    for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])[:20]:
        marker = " [S]" if ext in SUPPORTED_EXTS else ""
        print(f"  {ext:10s} {count:6d}{marker}")

    # High-value directories for SANJAYA
    print("\n--- High-value directories for SANJAYA ---")
    for key, res in sorted(results.items()):
        if '/' not in key:  # top-level only
            continue
        if res['supported'] > 0:
            print(f"  {key}: {res['supported']} supported files")

    # Save
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_files': total_files,
        'supported_files': total_supported,
        'total_size_mb': total_size / (1024*1024),
        'extensions': dict(ext_counts),
        'directories': {k: {'file_count': len(v['files']), 'supported': v['supported'], 'subdirs': v['subdirs'], 'errors': v['errors']} for k, v in results.items()},
    }
    os.makedirs('reports', exist_ok=True)
    with open('reports/mission339_access_discovery.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nSaved to reports/mission339_access_discovery.json")
    print("Phase 1 COMPLETE.")


if __name__ == '__main__':
    main()
