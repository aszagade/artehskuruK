#!/usr/bin/env python3
"""Quick drive/network check."""
import os
import string

print("=== Checking drives ===")
for letter in string.ascii_uppercase:
    drive = letter + ":\\"
    try:
        if os.path.exists(drive):
            is_dir = os.path.isdir(drive)
            if is_dir:
                try:
                    entries = os.listdir(drive)
                    print(f"  {drive} DIR ({len(entries)} entries)")
                    for e in entries[:5]:
                        print(f"    {e}")
                except Exception as e2:
                    print(f"  {drive} DIR (cannot list: {e2})")
            else:
                print(f"  {drive} FILE")
    except Exception:
        pass

# Try different UNC path variations
print("\n=== Testing UNC paths ===")
unc_paths = [
    r"\\ina6fs01\Dept_shares",
    r"\\ina6fs01",
    r"\\INA6FS01\Dept_shares",
    r"\\ina6fs01.dept.shares",
]
for p in unc_paths:
    try:
        exists = os.path.exists(p)
        if exists:
            entries = os.listdir(p)
            print(f"  {p} -> ACCESSIBLE ({len(entries)} entries)")
            for e in entries[:5]:
                print(f"    {e}")
        else:
            print(f"  {p} -> path does not exist")
    except PermissionError:
        print(f"  {p} -> PERMISSION DENIED")
    except OSError as e:
        print(f"  {p} -> OS Error: {e}")
    except Exception as e:
        print(f"  {p} -> Error: {type(e).__name__}: {e}")

# Check the OneDrive path for clues
print("\n=== Checking local OneDrive structure ===")
onedrive = r"C:\Users\aszaga\OneDrive - SAS\Desktop\artehskuruK"
if os.path.exists(onedrive):
    print(f"  OneDrive project path exists: {onedrive}")
    # Check if there's a reference to the network share in the project
    for root, dirs, files in os.walk(onedrive):
        depth = root.replace(onedrive, '').count(os.sep)
        if depth > 2:
            dirs.clear()
            continue
        for f in files:
            if f.endswith('.py') or f.endswith('.md') or f.endswith('.env'):
                fp = os.path.join(root, f)
                try:
                    with open(fp, 'r', errors='ignore') as fh:
                        content = fh.read(5000)
                    if 'ina6fs01' in content.lower() or 'dept_shares' in content.lower():
                        print(f"  REF: {fp}")
                        # Find the line
                        for line in content.split('\n'):
                            if 'ina6fs01' in line.lower() or 'dept_shares' in line.lower():
                                print(f"    {line.strip()[:120]}")
                except:
                    pass
else:
    print(f"  OneDrive path does not exist")
