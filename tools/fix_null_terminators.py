#!/usr/bin/env python3
"""Fix null-terminator bugs introduced by earlier edits.

Previous Python edits wrote literal null bytes (0x00) into C source where
the C escape sequence '\0' (backslash + zero) was intended. This script
replaces all occurrences of single-quoted literal null bytes ('\\x00') with
the correct escape sequence ('\\0').

Also fixes the space vs null-char sentinel in the marquee scroll guard.
"""
import re

path = r'C:\Users\Colin\Documents\GitHub\Kobra_Max\source\Marlin\src\lcd\extui\lib\anycubic_dgus\dgus_tft.cpp'

with open(path, 'rb') as f:
    raw = f.read()

# Bytes we want to replace: single-quote, NUL (0x00), single-quote
OLD = bytes([0x27, 0x00, 0x27])   # '\x00'
# Bytes we want to write: single-quote, backslash (0x5C), zero (0x30), single-quote
NEW = bytes([0x27, 0x5C, 0x30, 0x27])  # '\0'

count = raw.count(OLD)
print(f"Found {count} occurrences of literal null byte char literals to replace")

fixed = raw.replace(OLD, NEW)

with open(path, 'wb') as f:
    f.write(fixed)

# Verify
with open(path, 'rb') as f:
    verify = f.read()

remaining = verify.count(OLD)
print(f"Remaining literal null byte char literals: {remaining}")
if remaining == 0:
    print("All fixed.")
else:
    print("WARNING: some were not replaced!")

# Print the fixed lines for confirmation
content = verify.decode('utf-8', errors='replace')
lines = content.split('\n')
for lineno in [1271, 1573, 1582, 1588]:
    print(f"Line {lineno}: {lines[lineno-1].rstrip()}")
