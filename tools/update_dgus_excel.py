#!/usr/bin/env python3
"""
Update DGUS/DisplayConfig.xls and DGUS/TouchConfig.xls to reflect the
KobraMax-HC32 custom pages (6, 214, 215, 217).

NOTE ON WORKFLOW:
  The DGUS Tool (DGUS_V7649.exe) would normally read these Excel files and
  regenerate 14ShowFile.bin / 13TouchFile.bin.  For the KobraMax-HC32 custom
  pages we bypass the GUI tool:
    - 13TouchFile.bin  →  regenerated entirely by tools/generate_dwin_controls.py
    - 14ShowFile.bin   →  original patched by tools/patch_14showfile.py
  These Excel files are kept in sync as human-readable documentation and as a
  starting point if someone wants to re-run the DGUS Tool in the future.
  After editing these files in the DGUS Tool, re-run the two scripts above to
  bring the .bin files up to date with any changes.

Run from project root:
    python tools/update_dgus_excel.py
"""

import shutil
import xlrd
from xlutils.copy import copy as xl_copy

DISPLAY_IN  = "DGUS/DisplayConfig.xls"
TOUCH_IN    = "DGUS/TouchConfig.xls"

# ── Replacement data ──────────────────────────────────────────────────────────
#
# Image ID is 0-based: page N in DGUS = Image ID (N-1).
#   Page  6 → Image ID 5
#   Page 214 → Image ID 213
#   Page 215 → Image ID 214

# DisplayConfig columns: Image ID, Name, Var Pointer, Desc Pointer, Var type, description
DISPLAY_NEW = {
    5: [  # Page 6 — Input Shaping (replaces original keyboard page)
        ['5', 'Text', '0x2860', '0xFFFF', 'Text', 'IS X Frequency (Hz)'],
        ['5', 'Text', '0x2890', '0xFFFF', 'Text', 'IS Y Frequency (Hz)'],
        ['5', 'Text', '0x28C0', '0xFFFF', 'Text', 'IS X Damping zeta'],
        ['5', 'Text', '0x28F0', '0xFFFF', 'Text', 'IS Y Damping zeta'],
    ],
    213: [  # Page 214 — Thumbnail preview (replaces original stats/QR page)
        ['213', 'Text', '0x2180', '0xFFFF', 'Text', 'Selected filename'],
    ],
    214: [  # Page 215 — Terminal (new)
        ['214', 'Text', '0x2A10', '0xFFFF', 'Text', 'Terminal keyboard input'],
        ['214', 'Text', '0x2920', '0xFFFF', 'Text', 'Terminal log line 0'],
        ['214', 'Text', '0x2950', '0xFFFF', 'Text', 'Terminal log line 1'],
        ['214', 'Text', '0x2980', '0xFFFF', 'Text', 'Terminal log line 2'],
        ['214', 'Text', '0x29B0', '0xFFFF', 'Text', 'Terminal log line 3'],
        ['214', 'Text', '0x29E0', '0xFFFF', 'Text', 'Terminal log line 4'],
    ],
    # Page 216 (Thermal Tuning) and 217 (Factory Reset confirm) have no VP
    # display controls — no rows needed in DisplayConfig.
}

# TouchConfig columns: Image ID, Name, Var Pointer, Var Type, Pls Close Excel
_RKC = 'Return Key Code'
_AI  = 'ASCII Input'
TOUCH_NEW = {
    5: [  # Page 6 — Input Shaping: 9 buttons (BACK + 8 ±1 IS controls) + SAVE
        # BACK, -FreqX, +FreqX, -FreqY, +FreqY, -ZetaX, +ZetaX, -ZetaY, +ZetaY, SAVE
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
        ['5', _RKC, '0x1000', _RKC, _RKC],
    ],
    213: [  # Page 214 — Thumbnail: BACK + PRINT
        ['213', _RKC, '0x1000', _RKC, _RKC],
        ['213', _RKC, '0x1000', _RKC, _RKC],
    ],
    214: [  # Page 215 — Terminal: BACK + SEND + keyboard input
        ['214', _RKC, '0x1000', _RKC, _RKC],
        ['214', _RKC, '0x1000', _RKC, _RKC],
        ['214', _AI,  '0x2A10', _AI,  _AI],
    ],
    216: [  # Page 217 — Factory Reset confirm: CANCEL + RESET
        ['216', _RKC, '0x1000', _RKC, _RKC],
        ['216', _RKC, '0x1000', _RKC, _RKC],
    ],
}

# ── Helper ────────────────────────────────────────────────────────────────────

def patch_xls(in_path, replacements, label):
    """
    Read an .xls file, drop all rows whose Image ID (col 0) is in `replacements`,
    insert the replacement rows at the same position, write back in place.
    """
    shutil.copy(in_path, in_path + ".bak")
    rb = xlrd.open_workbook(in_path, formatting_info=True)
    wb = xl_copy(rb)
    ws_r = rb.sheet_by_index(0)
    ws_w = wb.get_sheet(0)

    # Collect all rows from the original, rebuilding with replacements
    # We'll re-write the entire sheet row by row
    # xlutils copy gives us a writable sheet with styles preserved

    # First pass: identify which rows to keep/replace and where to insert new rows
    all_rows = []
    inserted = set()
    for r in range(ws_r.nrows):
        img_val = ws_r.cell(r, 0).value
        try:
            img_id = int(float(img_val))
        except (ValueError, TypeError):
            # header row or empty
            all_rows.append(('keep', r))
            continue

        if img_id in replacements:
            if img_id not in inserted:
                inserted.add(img_id)
                # Insert replacement rows at this position
                for new_row in replacements[img_id]:
                    all_rows.append(('new', new_row))
            # Skip all original rows for this img_id
        else:
            all_rows.append(('keep', r))

    # Add any image IDs that weren't found in the original (new pages)
    for img_id, rows in replacements.items():
        if img_id not in inserted:
            for new_row in rows:
                all_rows.append(('new', new_row))

    # Re-write the sheet (xlutils copy preserves per-cell styles)
    # We clear and rewrite from row 1 onwards (leave header)
    # Since we can't delete rows in xlwt, we overwrite in place and pad with blanks
    write_row = 1
    for kind, payload in all_rows[1:]:  # skip header (row 0)
        if kind == 'keep':
            r = payload
            for c in range(ws_r.ncols):
                ws_w.write(write_row, c, ws_r.cell(r, c).value)
        else:
            new_row_data = payload
            for c, val in enumerate(new_row_data):
                ws_w.write(write_row, c, val)
        write_row += 1

    # Blank out any remaining rows (if replacement was shorter than original)
    orig_data_rows = ws_r.nrows - 1
    while write_row <= orig_data_rows:
        for c in range(ws_r.ncols):
            ws_w.write(write_row, c, '')
        write_row += 1

    wb.save(in_path)
    print(f"  {label}: wrote {write_row - 1} data rows to {in_path}  (backup: {in_path}.bak)")

# ── Main ──────────────────────────────────────────────────────────────────────

print("Updating DisplayConfig.xls ...")
patch_xls(DISPLAY_IN, DISPLAY_NEW, "DisplayConfig")

print("Updating TouchConfig.xls ...")
patch_xls(TOUCH_IN, TOUCH_NEW, "TouchConfig")

print()
print("NOTE: These Excel files are documentation / DGUS Tool source.")
print("The .bin files are generated by separate Python scripts:")
print("  13TouchFile.bin  <-  tools/generate_dwin_controls.py")
print("  14ShowFile.bin   <-  tools/patch_14showfile.py  (patches original)")
print("After editing these .xls files via the DGUS Tool, re-run those scripts")
print("to bring the .bin files up to date.")

# ── Verify ────────────────────────────────────────────────────────────────────
print()
print("Verifying DisplayConfig.xls ...")
wb_check = xlrd.open_workbook(DISPLAY_IN)
ws_check = wb_check.sheet_by_index(0)
for img_id, rows in DISPLAY_NEW.items():
    found = []
    for r in range(1, ws_check.nrows):
        v = ws_check.cell(r, 0).value
        try:
            if int(float(v)) == img_id:
                found.append([ws_check.cell(r, c).value for c in range(ws_check.ncols)])
        except (ValueError, TypeError):
            pass
    expected_vps = set(row[2] for row in rows)
    got_vps = set(row[2] for row in found)
    status = "OK" if expected_vps == got_vps else "MISMATCH"
    print(f"  [{status}] Image ID {img_id}: expected {sorted(expected_vps)}, got {sorted(got_vps)}")
