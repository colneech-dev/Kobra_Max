#!/usr/bin/env python3
"""
DWIN Touch-Zone Generator for KobraMax-HC32 UI
Generates DWIN_SET/13TouchFile.bin from scratch.

Binary format (per 13TouchFile.bin spec):
  N × 32-byte records, followed by 2-byte terminator FF FF.
  Each record:
    [page  : 2B BE]
    [x0    : 2B BE]
    [y0    : 2B BE]
    [x1    : 2B BE]
    [y1    : 2B BE]
    FF 00 00 23 FE 05 FE
    [VP_hi : 1B]  [VP_lo : 1B]   # KEY_ADDRESS = 0x1000
    00 00
    [key   : 1B]
    00 × 10

KEY_ADDRESS = 0x1000 (firmware polls this; key_value is reset to 0 after handling).
Key codes match the case labels in dgus_tft.cpp page*_handle() functions.

Run from project root:
    python tools/generate_dwin_controls.py
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_features as uf
import press_effect as pe

OUT_DIR = "DWIN_SET"
OUT_FILE = os.path.join(OUT_DIR, "13TouchFile.bin")

KEY_ADDRESS = 0x1000
# After the press-effect field: touch-control code 0xFE05 (return key code) + 0xFE, then the
# variable pointer (KEY_ADDRESS) and the mode word. See DWIN T5L DGUS II guide 6.6.
_FIXED_TAIL = bytes([0xFE, 0x05, 0xFE,
                     (KEY_ADDRESS >> 8) & 0xFF, KEY_ADDRESS & 0xFF,
                     0x00, 0x00])


def make_record(page, x0, y0, x1, y1, key, press=None):
    """32-byte return-key-code record. `press` = ID of the picture whose pixels are shown over the
    button while it is held (None = no press effect). It used to be a hard-coded 0x0023 copied from
    one stock record, i.e. every button pointed at a picture that does not exist in our library."""
    pic_on = pe.NO_EFFECT if press is None else press
    coords = struct.pack(">HHHHH", page, x0, y0, x1, y1)
    # Pic_Next 0xFF00 = no page switch; Pic_On = press-effect picture
    return coords + b'\xFF\x00' + struct.pack(">H", pic_on) + _FIXED_TAIL + bytes([key & 0xFF]) + b'\x00' * 10


# ---------------------------------------------------------------------------
# Touch zone definitions
#   (pages, x0, y0, x1, y1, key)
#   pages: int or list of ints
# ---------------------------------------------------------------------------

_ZONES = [
    # ── PAGE 1 / 121  Main Menu ──────────────────────────────────────────────
    ([1, 121], 8,   138, 132, 200, 1),  # PRINT → file browser
    ([1, 121], 140, 138, 264, 200, 2),  # TOOLS
    ([1, 121], 8,   212, 132, 274, 3),  # PREPARE
    ([1, 121], 140, 212, 264, 274, 4),  # SETTINGS

    # ── PAGE 2 / 122  File Browser ───────────────────────────────────────────
    ([2, 122], 228,  58, 264,  88, 4),  # REFRESH (in title bar)
    ([2, 122],   0,  93, 271, 144, 7),  # File row 1
    ([2, 122],   0, 146, 271, 198, 8),  # File row 2
    ([2, 122],   0, 200, 271, 252, 9),  # File row 3
    ([2, 122],   0, 254, 271, 306, 10), # File row 4
    ([2, 122],   0, 308, 271, 360, 11), # File row 5
    ([2, 122],   8, 366, 132, 406, 2),  # PREV PAGE
    ([2, 122], 140, 366, 264, 406, 3),  # NEXT PAGE
    ([2, 122],   8, 429,  90, 473, 1),  # BACK   (footer btn 0)
    ([2, 122],  94, 429, 176, 473, 5),  # RESUME (footer btn 1)
    ([2, 122], 180, 429, 262, 473, 6),  # PRINT  (footer btn 2)

    # ── PAGE 3 / 123  Paused, PAGE 4 / 124  Printing ─────────────────────────────────────────
    # footer_2btn: STOP left, RESUME / PAUSE right (the old BACK button did nothing during a print)
    ([3, 123, 4, 124],   8, 304, 264, 340, 4),  # PRINT SETTINGS
    ([3, 123, 4, 124],   8, 429, 132, 473, 3),  # STOP
    ([3, 123, 4, 124], 140, 429, 264, 473, 2),  # RESUME (3) / PAUSE (4)

    # ── PAGE 5 / 125 and 211 / 212  Print Settings (rows come from ui_features.PRINT_SETTINGS_ROWS) ──
    *[z for _lbl, _y, _ph, _km, _kp in uf.PRINT_SETTINGS_ROWS for z in (
        ([5, 125, 211, 212],   8, _y,  60, _y + 36, _km),   # -
        ([5, 125, 211, 212], 212, _y, 264, _y + 36, _kp))], # +
    ([211, 212], 226, 59, 264, 87, uf.PRINT_SETTINGS_LIGHT_KEY),   # case-light bulb (title bar)
    ([5, 125, 211, 212],   8, 429, 132, 473, 1),   # BACK (not saved)
    ([5, 125, 211, 212], 140, 429, 264, 473, 7),   # SAVE

    # ── PAGE 6  On-screen keyboard (Terminal) — one zone per key, codes from ui_features.keyboard_keys() ──
    *[([uf.KEYBOARD_PAGE], _x1, _y1, _x2, _y2, _code) for _x1, _y1, _x2, _y2, _l, _code, _s in uf.keyboard_keys()],

    # ── PAGE 7 / 127 / 207 / 209  Tools (with or without case-light) ─────────
    ([7, 127, 207, 209],   8, 106, 132, 168, 2), # MOVE AXES
    ([7, 127, 207, 209], 140, 106, 264, 168, 3), # TEMPERATURE
    ([7, 127, 207, 209],   8, 180, 132, 242, 4), # SPEED / FAN
    ([7, 127, 207, 209], 140, 180, 264, 242, 6), # LIGHT toggle
    ([7, 127, 207, 209],   8, 258, 264, 316, 5), # MOTORS OFF
    ([7, 127, 207, 209],   8, 429, 264, 473, 1), # BACK

    # ── PAGE 8 / 128  Move Axes ───────────────────────────────────────────────
    ([8, 128],   8, 114,  90, 144,  3), # Step 0.1
    ([8, 128],  94, 114, 176, 144,  7), # Step 1.0
    ([8, 128], 180, 114, 264, 144, 11), # Step 10
    ([8, 128],  34, 156, 110, 198,  2), # X−
    ([8, 128], 116, 156, 158, 198,  5), # HOME X
    ([8, 128], 164, 156, 264, 198,  4), # X+
    ([8, 128],  34, 210, 110, 252,  8), # Y−
    ([8, 128], 116, 210, 158, 252,  9), # HOME Y
    ([8, 128], 164, 210, 264, 252,  6), # Y+
    ([8, 128],  34, 264, 110, 306, 10), # Z−
    ([8, 128], 116, 264, 158, 306, 13), # HOME Z
    ([8, 128], 164, 264, 264, 306, 12), # Z+
    ([8, 128],   8, 318, 264, 358, 17), # HOME ALL
    ([8, 128],   8, 429, 264, 473,  1), # BACK

    # ── PAGE 9 / 129  Temperature ─────────────────────────────────────────────
    # Button y-coords: HOTEND row DEC/INC at y=184; BED row at y=320
    # (from _temp_speed_page: y=CONTENT_Y1+12, each row = 22+14+44+46+10 = 136px)
    ([9, 129],   8, 184,  64, 218, 2), # HOTEND −5°C
    ([9, 129], 200, 184, 264, 218, 3), # HOTEND +5°C
    ([9, 129],   8, 320,  64, 354, 4), # BED    −5°C
    ([9, 129], 200, 320, 264, 354, 5), # BED    +5°C
    ([9, 129],   8, 429,  90, 473, 1), # BACK
    ([9, 129],  94, 429, 176, 473, 6), # COOL (zero both heaters)
    ([9, 129], 180, 429, 262, 473, 7), # SET (read VP and apply)

    # ── PAGE 10 / 130  Speed & Fan ────────────────────────────────────────────
    ([10, 130],   8, 184,  64, 218, 2), # FAN   −5%
    ([10, 130], 200, 184, 264, 218, 3), # FAN   +5%
    ([10, 130],   8, 320,  64, 354, 4), # SPEED −5%
    ([10, 130], 200, 320, 264, 354, 5), # SPEED +5%
    ([10, 130],   8, 429, 132, 473, 1), # BACK
    ([10, 130], 140, 429, 264, 473, 6), # SET (read VP and apply)

    # ── PAGE 11 / 131  System (audio ON)  +
    #    PAGE 117 / 170  System (audio OFF — same layout) ─────────────────────
    ([11, 131, 117, 170],   8, 106, 132, 168, 2), # STATISTICS
    ([11, 131, 117, 170], 140, 106, 264, 168, 4), # AUDIO toggle
    ([11, 131, 117, 170],   8, 180, 132, 242, 5), # ABOUT
    ([11, 131, 117, 170], 140, 180, 264, 242, 3), # TERMINAL
    ([11, 131, 117, 170],   8, 254, 264, 314, 6), # FACTORY RESET
    ([11, 131, 117, 170],   8, 429, 264, 473, 1), # BACK

    # ── PAGE 13 / 133  About ─────────────────────────────────────────────────
    ([13, 133], 8, 429, 264, 473, 1), # BACK

    # ── PAGE 15 / 135  Prepare ────────────────────────────────────────────────
    ([15, 135],   8, 106, 132, 168, 2), # LEVELING
    ([15, 135], 140, 106, 264, 168, 3), # PREHEAT
    ([15, 135],   8, 180, 132, 242, 4), # FILAMENT
    ([15, 135], 140, 180, 264, 242, 5), # SHAPING / COOL DOWN (key 5)
    ([15, 135],   8, 254, 264, 314, 6), # THERMAL TUNING
    ([15, 135],   8, 429, 264, 473, 1), # BACK

    # ── PAGE 16 / 136  Pre-Level menu ────────────────────────────────────────
    ([16, 136],   8, 112, 264, 156, 2), # AUTO BED LEVEL G29
    ([16, 136],   8, 168, 264, 212, 3), # MANUAL Z ADJUST
    *([] if not uf.HAS_M1024 else [
        ([16, 136],   8, 224, 264, 268, 5), # Z OFFSET WIZARD
        ([16, 136],   8, 280, 264, 324, 4), # AUTO Z OFFSET
    ]),
    ([16, 136],   8, 429, 264, 473, 1), # BACK

    # ── PAGE 17 / 137  Z-Offset Adjust ───────────────────────────────────────
    ([17, 137],   8, 196, 132, 236, 5), # -0.1 mm
    ([17, 137], 140, 196, 264, 236, 6), # +0.1 mm
    ([17, 137],   8, 244, 132, 284, 2), # -0.01 mm
    ([17, 137], 140, 244, 264, 284, 3), # +0.01 mm
    ([17, 137],   8, 429, 132, 473, 1), # BACK
    ([17, 137], 140, 429, 264, 473, 4), # SAVE

    # ── PAGE 18 / 138  Preheat ────────────────────────────────────────────────
    ([18, 138],   8, 290, 132, 336, 2), # preheat 1 (label/temps from Configuration.h)
    ([18, 138], 140, 290, 264, 336, 3), # preheat 2
    ([18, 138],   8, 429, 264, 473, 1), # BACK

    # ── PAGE 19 / 139  Filament ───────────────────────────────────────────────
    ([19, 139],   8, 196, 264, 236, 2), # LOAD
    ([19, 139],   8, 244, 264, 284, 5), # EXTRUDE 10 mm
    ([19, 139],   8, 292, 264, 332, 3), # UNLOAD
    ([19, 139],   8, 340, 264, 380, 4), # STOP
    ([19, 139],   8, 429, 264, 473, 1), # BACK

    # ── PAGES 20-31 / 140-151  Simple confirm / info pages ───────────────────
    # All use footer_1btn → key 1
    ([20, 140], 8, 429, 264, 473, 1),   # Done – confirm
    ([21, 141], 8, 429, 264, 473, 1),   # Abnormal – BACK
    ([22, 142], 8, 429, 264, 473, 1),   # Print Finish – OK → Main Menu
    # 23/143 wait_stop: no interactive buttons
    ([25, 145], 8, 429, 264, 473, 1),   # Filament Lack – BACK TO PRINT
    ([26, 146], 8, 429, 264, 473, 1),   # Forbidden – OK
    # 27/147 Stop Confirm: CANCEL=left(key2), STOP=right(key1)
    ([27, 147],   8, 429, 132, 473, 2), # CANCEL
    ([27, 147], 140, 429, 264, 473, 1), # STOP PRINT
    ([29, 149], 8, 429, 264, 473, 1),   # No SD – OK
    ([30, 150], 8, 429, 264, 473, 1),   # Filament Heat – OK START HEATING
    # 32/152 wait_pause: no interactive buttons
    # 33/153 Level Ensure: BACK=left(key2), START G29=right(key1)
    ([33, 153],   8, 429, 132, 473, 2), # BACK
    ([33, 153], 140, 429, 264, 473, 1), # START G29
    # 34/154 leveling: no interactive buttons

    # ── PAGE 93 / 213  Printer Stats ─────────────────────────────────────────
    ([93, 213], 8, 429, 264, 473, 1),  # BACK

    # ── PAGE 115  Auto Z-Offset — only when M1024 exists (see ui_features) ──
    *([] if not uf.HAS_M1024 else [
        ([115],   8, 110, 264, 152, 6), # PREPARE (move to centre)
        ([115],   8, 164, 132, 206, 2), # −1.0 mm
        ([115], 140, 164, 264, 206, 3), # +1.0 mm
        ([115],   8, 218, 132, 260, 4), # −0.1 mm
        ([115], 140, 218, 264, 260, 5), # +0.1 mm
        ([115],   8, 272, 264, 314, 7), # FINE +0.1 mm (fine-step command)
        ([115],   8, 429, 264, 473, 1), # BACK
    ]),

    # ── PAGES 171 / 173  Power-Loss Recovery ─────────────────────────────────
    # CANCEL=left(key2), RESUME=right(key1)
    ([171, 173],   8, 429, 132, 473, 2), # CANCEL
    ([171, 173], 140, 429, 264, 473, 1), # RESUME

    # ── PAGES 175 / 176  Probe Preheating ────────────────────────────────────
    # Pure wait/spinner page — no interactive buttons.

    # ── PAGES 177-198  Error / Status pages ──────────────────────────────────
    # 177-186 / 189-198 are homing and fatal-fault pages: no button (homing cannot be
    # cancelled, and Marlin has halted after a fault). 187/188 (CHS leveling errors) are handled
    # by page199_to_200_handle, like their ENG mirrors 199/200 below.
    ([187, 188], 8, 429, 264, 473, 1),  # BACK -> Leveling menu

    # ── PAGES 199 / 200  Leveling error pages (handled) ──────────────────────
    ([199, 200], 8, 429, 264, 473, 1), # BACK → PreLevel

    # ── PAGES 201 / 204  Probe Precheck ──────────────────────────────────────
    ([201, 204], 8, 429, 264, 473, 1), # CANCEL

    # 202/205 probe_ok   — auto-transitions, no buttons
    ([203, 206], 8, 429, 264, 473, 1),  # BACK -> Leveling menu (page203_handle also times out)

    # ── PAGE 214  Thumbnail / Print Preview ───────────────────────────────────
    ([214],   8, 429, 132, 473, 1), # BACK  (KEY_THUMB_BACK  = 1)
    ([214], 140, 429, 264, 473, 2), # PRINT (KEY_THUMB_PRINT = 2)

    # ── PAGE 215  Terminal ────────────────────────────────────────────────────
    # Preset command buttons — 3-col row then 2-col row; bw = (272-16-8)//3 = 82
    # y=306 matches generate_screens.py: after loop y=282, y+=24 → y=306 (buttons at 306-350)
    ([215],   8, 306,  90, 350, 3), # G28 HOME  (KEY_TERM_G28  = 3)
    ([215],  94, 306, 176, 350, 4), # G29 LEVEL (KEY_TERM_G29  = 4)
    ([215], 180, 306, 262, 350, 5), # M105 TEMPS(KEY_TERM_M105 = 5)
    ([215],   8, 358,  90, 402, 6), # M502 RESET(KEY_TERM_M502 = 6)  (306+52=358)
    ([215],  94, 358, 176, 402, 7), # M500 SAVE (KEY_TERM_M500 = 7)
    ([215], 180, 358, 262, 402, 8), # KEYBOARD  (opens page 6)
    ([215],   8, 429, 264, 473, 1), # BACK      (KEY_TERM_BACK = 1)

    # ── PAGE 216  Thermal Tuning ──────────────────────────────────────────────
    ([216],   8, 122, 264, 200, 2), # MPC AUTOTUNE HOTEND  (KEY_TUNE_HOTEND = 2)
    ([216],   8, 230, 264, 308, 3), # PID AUTOTUNE BED 60C (KEY_TUNE_BED   = 3)
    ([216],   8, 429, 264, 473, 1), # BACK                 (KEY_TUNE_BACK  = 1)

    # ── PAGE 217  Factory Reset confirmation ──────────────────────────────────
    ([217],   8, 429, 132, 473, 1), # CANCEL  (key=1)
    ([217], 140, 429, 264, 473, 2), # RESET   (key=2)
]


def _expand_zones(raw):
    """Expand multi-page tuples into individual (page, x0, y0, x1, y1, key) tuples."""
    for entry in raw:
        pages, x0, y0, x1, y1, key = entry
        if isinstance(pages, int):
            pages = [pages]
        for p in pages:
            yield (p, x0, y0, x1, y1, key)


def build_bin():
    records = []
    for page, x0, y0, x1, y1, key in _expand_zones(_ZONES):
        press = pe.pressed_id(page, key) if uf.PRESS_EFFECT else None
        records.append(make_record(page, x0, y0, x1, y1, key, press))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, 'wb') as f:
        for r in records:
            f.write(r)
        f.write(b'\xFF\xFF')  # terminator

    total = len(records)
    size  = total * 32 + 2
    print(f"Written {OUT_FILE}  ({total} zones, {size} bytes)")
    return total, size


DOC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DWIN_CONTROLS_README.md")
_DOC_MARKER = "## Page-by-Page Touch Zone Mapping"


def write_doc():
    """Regenerate the per-page tables of tools/DWIN_CONTROLS_README.md from _ZONES, so the document
    cannot drift from the generator. Everything above the marker heading is hand-written and kept."""
    import re
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    # trailing '# comment' of each zone line, keyed by its coordinates + key
    notes = {}
    for m in re.finditer(r"\(\[?[\d, ]+\]?,\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\),?\s*#\s*(.*)$", src, re.M):
        notes[tuple(int(g) for g in m.groups()[:5])] = m.group(6).strip()

    # group pages that have identical zone lists (CHS page + ENG mirror etc.)
    by_page = {}
    for page, *rest in _expand_zones(_ZONES):
        by_page.setdefault(page, []).append(tuple(rest))
    merged = {}
    for page, zones in sorted(by_page.items()):
        merged.setdefault(tuple(zones), []).append(page)

    out = [_DOC_MARKER, "",
           "Generated by `python tools/generate_dwin_controls.py --doc` from the zone list in that script —",
           "do not edit this section by hand. Key codes are the `case` labels in the matching `page*_handle()`",
           "in `dgus_tft.cpp`. Pages hidden because the firmware lacks the feature (see `tools/ui_features.py`)",
           "have no zones and are absent here.", ""]
    for zones, pages in sorted(merged.items(), key=lambda kv: kv[1][0]):
        out.append(f"### Page {' / '.join(str(p) for p in pages)}  *({len(zones)} zone{'s' if len(zones) != 1 else ''})*")
        out += ["", "| Zone | x0 | y0 | x1 | y1 | Key |", "|------|----|----|----|----|-----|"]
        for x0, y0, x1, y1, key in zones:
            label = notes.get((x0, y0, x1, y1, key), '')
            if not label and uf.KEYBOARD_PAGE in pages:   # the 40+ keyboard zones come from one generated table, not hand-written lines
                label = next((f"key {l}" for _x1, _y1, _x2, _y2, l, code, _s in uf.keyboard_keys() if code == key), '')
            out.append(f"| {label} | {x0} | {y0} | {x1} | {y1} | {key} |")
        out.append("")

    head = open(DOC_PATH, encoding="utf-8").read()
    head = head.split(_DOC_MARKER)[0].rstrip() + "\n\n"
    with open(DOC_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + "\n".join(out) + "\n")
    print(f"Wrote {DOC_PATH}  ({len(merged)} page groups)")


if __name__ == '__main__':
    if "--doc" in sys.argv:
        write_doc()
    else:
        build_bin()
