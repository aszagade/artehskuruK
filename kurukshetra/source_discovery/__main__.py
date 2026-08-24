"""
Source Discovery CLI

Usage:
    python -m kurukshetra.source_discovery PATH
    python -m kurukshetra.source_discovery PATH --csv-inventory FILE
    python -m kurukshetra.source_discovery PATH --sample-size 30

Examples:
    python -m kurukshetra.source_discovery "\\\\ina6fs01\\Dept_shares\\ICS"
    python -m kurukshetra.source_discovery "\\\\ina6fs01\\Dept_shares\\ICS" --csv-inventory ina6fs01_inventory.csv --csv-access ina6fs01_folder_access.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kurukshetra.source_discovery.profiler import SourceProfiler


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only source discovery profiler for KURUKSHETRA",
    )
    parser.add_argument(
        "path",
        help="Network share path or local directory to profile",
    )
    parser.add_argument(
        "--name",
        default="unknown",
        help="Source name (default: derived from path)",
    )
    parser.add_argument(
        "--csv-inventory",
        default=None,
        help="Pre-existing CSV inventory file (avoids live scan)",
    )
    parser.add_argument(
        "--csv-access",
        default=None,
        help="Pre-existing folder access CSV",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Max documents to sample for content analysis (default: 20)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON profile path (default: reports/source_profiles/{name}_profile.json)",
    )

    args = parser.parse_args()

    # Derive name from path if not provided
    name = args.name
    if name == "unknown":
        parts = args.path.replace("\\", "/").rstrip("/").split("/")
        name = parts[-1] if parts else "unknown"

    print(f"\n{'='*60}")
    print(f"KURUKSHETRA SOURCE DISCOVERY")
    print(f"{'='*60}")
    print(f"  Mode:     READ-ONLY")
    print(f"  Source:   {args.path}")
    print(f"  Name:     {name}")
    if args.csv_inventory:
        print(f"  CSV:      {args.csv_inventory}")
    print(f"  Samples:  {args.sample_size}")
    print()

    profiler = SourceProfiler(
        max_sample_size=args.sample_size,
    )

    try:
        profile = profiler.profile_source(
            path=args.path,
            source_name=name,
            csv_inventory=args.csv_inventory,
            csv_folder_access=args.csv_access,
        )
    except FileNotFoundError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR during scan: {e}", file=sys.stderr)
        sys.exit(1)

    # Print summary
    profiler.print_summary(profile)

    # Save profile
    output = args.output
    if not output:
        output = f"reports/source_profiles/{name}_profile.json"
    profiler.save_profile(profile, output)
    print(f"\n  Profile saved to: {output}")
    print(f"\n{'='*60}")


if __name__ == "__main__":
    main()
