"""Fix the broken regex in kurukshetra/chunking/semantic.py"""
with open('kurukshetra/chunking/semantic.py', 'rb') as f:
    content = f.read()

# The broken section has literal 0x0a (newline) bytes inside regex strings
# We need to replace them with backslash + n (0x5c 0x6e)

# Find the broken re.sub line
broken_pattern = b're.sub(r"\n{3,}", "\n\n", cleaned)'
fixed_pattern = b're.sub(r"\\n{3,}", "\\n\\n", cleaned)'

count = content.count(broken_pattern)
print(f"Found {count} broken pattern(s)")

if count > 0:
    content = content.replace(broken_pattern, fixed_pattern, 1)
    with open('kurukshetra/chunking/semantic.py', 'wb') as f:
        f.write(content)
    print("Fixed!")
else:
    print("Pattern not found, checking for variations...")
    # Try to find by looking for the exact bytes
    import re
    for m in re.finditer(b're\\.sub\\(r"', content):
        start = m.start()
        chunk = content[start:start+50]
        print(f"  Found re.sub at byte {start}: {chunk}")
