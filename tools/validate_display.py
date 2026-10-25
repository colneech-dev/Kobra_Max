#!/usr/bin/env python3
"""
DWIN Display Consistency Validator — KobraMax-HC32

Mechanically checks that every VP the firmware writes to has a display record
in 14ShowFile.bin for the correct page, and that every page navigated to has
a BMP and touch-zone coverage.

Exit code: 0 = all checks pass, 1 = gaps found.

NOTE: superseded by tools/cross_check_display.py, which compares the actual art, touch zones,
show-file records and handler keys. This script is a text-heuristic check of the firmware source;
it reports false positives for helper-based navigation and for deliberately dead cases, so do
not treat its failures as authoritative (and its passes never covered handlers whose '{' was on
the next line before the 2026-10-25 regex fix).

Run from project root:
    python tools/validate_display.py
"""

import re
import sys
import struct
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

CPP  = Path("source/Marlin/src/lcd/extui/lib/anycubic_dgus/dgus_tft.cpp")
H    = Path("source/Marlin/src/lcd/extui/lib/anycubic_dgus/dgus_tft.h")
SHOWFILE = Path("DWIN_SET/14ShowFile.bin")
TOUCHFILE = Path("DWIN_SET/13TouchFile.bin")
DWIN_SET  = Path("DWIN_SET")

errors   = []
warnings = []

def fail(msg):  errors.append(msg)
def warn(msg):  warnings.append(msg)

# ── 1. Parse dgus_tft.h constants ────────────────────────────────────────────

h_text = H.read_text(encoding='utf-8', errors='replace')

PAGE_OFFSET = 0
page_defs = {}  # name -> value
for m in re.finditer(r'#define\s+(PAGE_\w+)\s+\((\d+)\+PAGE_OFFSET\)', h_text):
    page_defs[m.group(1)] = int(m.group(2)) + PAGE_OFFSET
for m in re.finditer(r'#define\s+(PAGE_\w+)\s+(\d+)\b', h_text):
    if m.group(1) not in page_defs:
        page_defs[m.group(1)] = int(m.group(2))

vp_defs = {}  # name -> value
for m in re.finditer(r'#define\s+(TXT_\w+)\s+\(?(0x[0-9a-fA-F]+|\d+)(?:\+\d+\*0x30)?\)?', h_text):
    try:
        val = int(m.group(2), 16)
        vp_defs[m.group(1)] = val
    except ValueError:
        pass
# Also parse expressions like (0x2000+8*0x30)
for m in re.finditer(r'#define\s+(TXT_\w+)\s+\((0x[0-9a-fA-F]+)\+(\d+)\*(0x[0-9a-fA-F]+)\)', h_text):
    try:
        val = int(m.group(2), 16) + int(m.group(3)) * int(m.group(4), 16)
        vp_defs[m.group(1)] = val
    except ValueError:
        pass

key_defs = {}  # KEY_* name -> integer key code
for m in re.finditer(r'#define\s+(KEY_\w+)\s+(\d+)\b', h_text):
    try:
        key_defs[m.group(1)] = int(m.group(2))
    except ValueError:
        pass

# ── 2. Parse 14ShowFile.bin ───────────────────────────────────────────────────

show_vps = {}   # page_num -> set of vp_addrs with records

if SHOWFILE.exists():
    data = SHOWFILE.read_bytes()
    count = int.from_bytes(data[8:10], 'big')
    for i in range(count):
        tbl = 16 + i * 4
        if tbl + 4 > len(data):
            break
        n   = int.from_bytes(data[tbl:tbl+2], 'little')
        off = int.from_bytes(data[tbl+2:tbl+4], 'big')
        page_num = i   # table index == DGUS page ID (0-based)
        vp_set = set()
        for j in range(n):
            rec_off = off + j * 32
            if rec_off + 32 > len(data):
                break
            rec = data[rec_off:rec_off+32]
            rtype = int.from_bytes(rec[0:2], 'big')
            vp    = int.from_bytes(rec[6:8], 'big')
            if rtype in (0x5A10, 0x5A11):
                vp_set.add(vp)
        show_vps[page_num] = vp_set
else:
    warn("14ShowFile.bin not found — run patch_14showfile.py first")

# ── 3. Parse 13TouchFile.bin ─────────────────────────────────────────────────

touch_pages = {}  # page_num -> set of key codes

if TOUCHFILE.exists():
    raw = TOUCHFILE.read_bytes()
    i = 0
    while i + 32 <= len(raw):
        chunk = raw[i:i+32]
        if chunk[:2] == b'\xff\xff':
            break
        page = int.from_bytes(chunk[0:2], 'big')
        key  = chunk[21]
        touch_pages.setdefault(page, set()).add(key)
        i += 32
else:
    warn("13TouchFile.bin not found — run generate_dwin_controls.py first")

# ── 4. Collect BMP pages ─────────────────────────────────────────────────────

bmp_pages = set()
for f in DWIN_SET.glob("*.bmp"):
    try:
        bmp_pages.add(int(f.stem))
    except ValueError:
        pass

# ── 5. Parse firmware source ──────────────────────────────────────────────────

_IF0_RE = re.compile(r'#\s*if\s+0(\s|$)')

def strip_if_zero(text):
    """Remove #if 0 ... #endif blocks (nested-depth aware).

    Handles:
      - '#if 0 // comment' variants (V6)
      - '#else'/'#elif' at depth 1 resume live output (V3)
    """
    out, skip = [], 0
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if skip == 0:
            if _IF0_RE.match(s):
                skip = 1
            else:
                out.append(line)
        else:
            if s.startswith('#if'):
                skip += 1
            elif skip == 1 and (s.startswith('#else') or s.startswith('#elif')):
                skip = 0  # resume from the live branch
            elif s == '#endif':
                skip -= 1
    return ''.join(out)

cpp_text = strip_if_zero(CPP.read_text(encoding='utf-8', errors='replace'))

# 5a. ChangePageOfTFT calls → set of navigated page numbers (pre-translation)
navigate_pages = set()
for m in re.finditer(r'ChangePageOfTFT\s*\(\s*([^)]+?)\s*\)', cpp_text):
    arg = m.group(1).strip()
    if arg in page_defs:
        navigate_pages.add(page_defs[arg])
    else:
        try:
            navigate_pages.add(int(arg, 0))
        except ValueError:
            pass

# 5b. VP sends per handler: map page_num -> set of vp_addrs written
#     Heuristic: find page*_handle functions and track SendTxtToTFT/SendValueToTFT calls.

def resolve_vp(token):
    """Return integer VP address or None."""
    token = token.strip()
    if token in vp_defs:
        return vp_defs[token]
    try:
        return int(token, 0)
    except ValueError:
        return None

# Split cpp into named handler blocks
handler_blocks = {}  # page_num -> text block
# `[^)]*\)[^{;]*\{` (not `.*?\{`): `.` does not cross newlines, so the old pattern silently
# skipped every handler whose opening brace is on the line after the signature (42 of 54).
for m in re.finditer(r'void\s+DgusTFT::page(\w+)_handle\s*\([^)]*\)[^{;]*\{', cpp_text):
    name = m.group(1)
    # Skip multi-page alias names (digits + underscores); the named-alias loop handles them
    if '_' in name:
        continue
    start = m.end()
    # Find matching closing brace (simple depth counter)
    depth = 1
    pos = start
    while pos < len(cpp_text) and depth > 0:
        if cpp_text[pos] == '{':
            depth += 1
        elif cpp_text[pos] == '}':
            depth -= 1
        pos += 1
    block = cpp_text[start:pos]
    try:
        page_num = int(name)
        handler_blocks[page_num] = block
    except ValueError:
        pass

# Named multi-page handlers
for alias_name, pages in [('page211_212', [211, 212]),
                           ('page207_209',  [207, 209]),
                           ('page177_to_198', list(range(177, 199))),
                           ('page199_to_200', [199, 200])]:
    m = re.search(r'void\s+DgusTFT::' + re.escape(alias_name) + r'_handle\s*\(.*?\{', cpp_text, re.DOTALL)
    if m:
        start = m.end()
        depth = 1; pos = start
        while pos < len(cpp_text) and depth > 0:
            if cpp_text[pos] == '{': depth += 1
            elif cpp_text[pos] == '}': depth -= 1
            pos += 1
        block = cpp_text[start:pos]
        for pg in pages:
            handler_blocks[pg] = block

# Extract VP writes per handler.
# VPs written in the same case block as a ChangePageOfTFT call are "setup writes" for the
# target page — they're excluded from the source handler's own-VP set to avoid Check C
# false positives (e.g. about-page data written in the system-page handler before navigating).
def _extract_vps(text):
    vps = set()
    for fn in ('SendTxtToTFT', 'SendValueToTFT', 'LCD_SEND_VAL'):
        for m in re.finditer(fn + r'\s*\([^,]+,\s*([^)]+)\)', text):
            vp = resolve_vp(m.group(1))
            if vp is not None:
                vps.add(vp)
    return vps

def _split_cases(block):
    """Split a handler block into per-case text segments."""
    segments, current = [], []
    for line in block.split('\n'):
        if re.match(r'\s*case\s+', line) and current:
            segments.append('\n'.join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        segments.append('\n'.join(current))
    return segments

# Extract VP writes from non-handler helper functions (e.g. printerStatsToTFT)
_helper_vps = {}  # func_name -> set of vp_addrs
for m in re.finditer(r'void\s+DgusTFT::(\w+)\s*\([^)]*\)\s*\{', cpp_text, re.DOTALL):
    fname = m.group(1)
    if fname.endswith('_handle'):
        continue
    start = m.end()
    depth = 1; pos = start
    while pos < len(cpp_text) and depth > 0:
        if cpp_text[pos] == '{': depth += 1
        elif cpp_text[pos] == '}': depth -= 1
        pos += 1
    vps = _extract_vps(cpp_text[start:pos])
    if vps:
        _helper_vps[fname] = vps

handler_vp_writes = {}  # page_num -> set of vp_addrs (own writes, not navigation setup)
for page_num, block in handler_blocks.items():
    own_vps = set()
    for seg in _split_cases(block):
        seg_vps = _extract_vps(seg)
        # Also include VP writes from helper function calls in this segment
        for hname, hvps in _helper_vps.items():
            if re.search(r'\b' + re.escape(hname) + r'\s*\(', seg):
                seg_vps.update(hvps)
        if re.search(r'(?:ChangePageOfTFT\w*|Go\w+Page)\s*\(', seg):
            pass  # navigation-setup write — attributed to target page, not this handler
        else:
            own_vps.update(seg_vps)
    handler_vp_writes[page_num] = own_vps

# Key codes handled per handler (resolve KEY_* named constants via key_defs)
handler_keys = {}
for page_num, block in handler_blocks.items():
    keys = set()
    for m in re.finditer(r'case\s+(\w+)\s*:', block):
        token = m.group(1).strip()
        try:
            keys.add(int(token, 0))
        except ValueError:
            if token in key_defs:
                keys.add(key_defs[token])
    keys.discard(0)
    handler_keys[page_num] = keys

# ── 6. ChangePageOfTFT translation (approximate) ─────────────────────────────

def translate_chs_arg(page_num):
    """Return set of actual DWIN page numbers that ChangePageOfTFT(page_num) may display.

    Caller must pass CHS-domain arguments only (1–119 range, or known named constants).
    Mirrors DgusTFT::ChangePageOfTFT() branching:
      CHN mode  → page_num as-is
      ENG mode  → page_num + 120 (default), with specific exceptions listed below
    """
    # Language-neutral pages — no ENG offset applied in ChangePageOfTFT
    # 115 = PAGE_AUTO_OFFSET: calibration page, shared across languages, no ENG BMP generated
    if page_num in (115, 214, 215, 216, 217):
        return {page_num}
    # CHS error/homing pages (177–188) → +12 in ENG mode
    if 177 <= page_num <= 188:
        return {page_num, page_num + 12}
    # CHS probe precheck pages (201–203) → +3 in ENG mode
    if 201 <= page_num <= 203:
        return {page_num, page_num + 3}
    # One-off special cases from ChangePageOfTFT source
    if page_num == 171:  # PAGE_OUTAGE_RECOVERY → PAGE_ENG_OUTAGE_RECOVERY (173)
        return {171, 173}
    if page_num == 176:  # PAGE_CHS_PROBE_PREHEATING → PAGE_ENG_PROBE_PREHEATING (175)
        return {175, 176}
    if page_num == 207:  # PAGE_CHS_TOOL_CASELIGHT → +2
        return {207, 209}
    if page_num == 211:  # PAGE_CHS_PRINTING_SETTING → +1
        return {211, 212}
    # Raw ENG-offset arg: ChangePageOfTFT(50) is called ONLY in ENG branches;
    # ChangePageOfTFT adds +120 → actual display page 170. No CHS page 50 exists.
    if page_num == 50:
        return {170}
    # PAGE_SYSTEM_CHS_AUDIO_OFF (117) is called only from CHN branches;
    # ENG mode uses ChangePageOfTFT(50) separately → page 170. No ENG page 237 exists.
    if page_num == 117:
        return {117}
    # Pages already in ENG display range (≥120): return as absolute page number.
    # These are either ENG-specific pages or named ENG constants navigated to directly.
    if page_num >= 120:
        return {page_num}
    # Standard CHS pages (1–119): dual-language pair — CHS at page_num, ENG at page_num+120
    return {page_num, page_num + 120}

# ── 7. Checks ─────────────────────────────────────────────────────────────────

print("=" * 60)
print("DWIN Display Consistency Validation")
print("=" * 60)

# Check A: Every navigated page has a BMP
print("\n[A] BMP coverage for navigated pages")
all_display_pages = set()
for pg in navigate_pages:
    all_display_pages.update(translate_chs_arg(pg))

missing_bmp = []
for pg in sorted(all_display_pages):
    if pg not in bmp_pages:
        missing_bmp.append(pg)
        fail(f"  BMP MISSING: page {pg} navigated to but no {pg:03d}.bmp")

if not missing_bmp:
    print(f"  OK — all {len(all_display_pages)} navigated pages have BMPs")

# Check B: Every navigated page has a 14ShowFile.bin entry
print("\n[B] 14ShowFile.bin coverage for navigated pages")
missing_show = []
for pg in sorted(all_display_pages):
    if pg not in show_vps:
        missing_show.append(pg)
        fail(f"  SHOW MISSING: page {pg} has no 14ShowFile.bin entry")

if not missing_show:
    print(f"  OK — all {len(all_display_pages)} navigated pages have 14ShowFile entries")

# Check C: VP written by handler exists in 14ShowFile.bin for that page
print("\n[C] VP display records vs firmware writes")

# Status bar VPs (written globally every 1500ms, not inside handlers)
STATUS_VPS = {0x2030, 0x2880}  # TXT_MAIN_HOTEND, TXT_MAIN_BED (relocated 2026-07-26)

missing_vp_records = []
for page_num in sorted(handler_vp_writes):
    display_pages = translate_chs_arg(page_num)
    for vp in sorted(handler_vp_writes[page_num]):
        if vp in STATUS_VPS:
            continue  # checked separately via status_bar records
        for dpg in display_pages:
            if dpg in show_vps and vp not in show_vps[dpg]:
                missing_vp_records.append((dpg, vp))
                fail(f"  VP RECORD MISSING: page {dpg}: VP 0x{vp:04X} written by firmware but no display record")

if not missing_vp_records:
    print(f"  OK — all firmware VP writes have matching display records")

# Check D: Status bar VPs present on all content pages that have handlers
print("\n[D] Status bar VP records on all handler pages")
missing_sb = []
for page_num in sorted(handler_blocks):
    for dpg in sorted(translate_chs_arg(page_num)):
        if dpg in show_vps:
            for sv in STATUS_VPS:
                if sv not in show_vps[dpg]:
                    missing_sb.append((dpg, sv))
                    fail(f"  STATUS BAR MISSING: page {dpg}: status bar VP 0x{sv:04X} not in 14ShowFile")

if not missing_sb:
    print(f"  OK — status bar VPs present on all handler pages")

# Check E: Every key code the handler responds to has a touch zone on that page
print("\n[E] Touch zone coverage for handler key codes")
missing_touch = []
for page_num in sorted(handler_keys):
    if not handler_keys[page_num]:
        continue
    for dpg in sorted(translate_chs_arg(page_num)):
        page_zones = touch_pages.get(dpg, set())
        for key in sorted(handler_keys[page_num]):
            if key == 0:
                continue
            if key not in page_zones:
                missing_touch.append((dpg, key))
                fail(f"  TOUCH MISSING: page {dpg}: key {key} handled in firmware but no touch zone")

if not missing_touch:
    print(f"  OK — all firmware key cases have touch zones")

# Check F: Every touch zone fires a key that a handler responds to
print("\n[F] Handler coverage for touch zone key codes")

# Map ENG display pages → their CHS handler page number
_ENG_TO_CHS: dict[int, int] = {}
_ENG_TO_CHS.update({p: p - 120 for p in range(121, 156)})    # standard ENG offset range
_ENG_TO_CHS.update({170: 117, 173: 171, 175: 176, 209: 207, 212: 211}) # one-off pairs
_ENG_TO_CHS.update({p: p - 12 for p in range(189, 201)})     # ENG homing/error pages
_ENG_TO_CHS.update({p: p - 3  for p in range(204, 207)})     # ENG probe-precheck pages

unhandled_touch = []
for pg in sorted(touch_pages):
    chs = _ENG_TO_CHS.get(pg, pg)
    if chs not in handler_keys:
        continue
    for key in sorted(touch_pages[pg]):
        if key not in handler_keys[chs] and key not in handler_keys.get(pg, set()):
            unhandled_touch.append((pg, key))
            warn(f"  TOUCH UNHANDLED: page {pg}: touch zone key {key} has no firmware case")

if not unhandled_touch:
    print(f"  OK — all touch zone keys have firmware handlers")

# ── 8. Summary ────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
if errors:
    print(f"FAILED — {len(errors)} error(s), {len(warnings)} warning(s)")
    for e in errors:
        print(e)
    for w in warnings:
        print("WARN:", w)
    sys.exit(1)
elif warnings:
    print(f"PASSED with {len(warnings)} warning(s)")
    for w in warnings:
        print("WARN:", w)
else:
    print("ALL CHECKS PASSED")
