#!/usr/bin/env python3
"""
Generate DWIN_SET/14ShowFile.bin from DWIN_SET/14ShowFile.base.bin.

Always reads the unpatched base file and applies all patches from scratch,
so this script is idempotent — safe to re-run at any time.

Every page that the firmware can navigate to is patched explicitly so that
the base.bin VP layout (different icon positions, shifted page numbers) is
never used.  Pages not in the firmware page map are left untouched.

Pages patched:
  Status-bar-only (hotend + bed live temps, no other dynamic content):
    CHS:  1, 7-8, 11-12, 15-16, 20-21, 23-34, 93*, 115, 117, 175-217*
    ENG:  121, 127-128, 131-132, 135-136, 140-141, 143-154
    *93/213 and 177-217 entries appear in both groups below

  Status-bar + content VPs:
    CHS:  2, 3, 4, 5, 6, 9, 10, 13, 14, 17, 18, 19, 22, 93, 171, 211, 213
    ENG:  122-126, 129-130, 133-134, 137-139, 142, 173, 212
    Custom (language-neutral): 214, 215, 216, 217

Count extended 215 → 218 (page IDs 0..217; the page table is 0-based, see the "Update page table" comment).

Run from project root:
    python tools/patch_14showfile.py
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_features as uf

BASE_PATH = "DWIN_SET/14ShowFile.base.bin"
OUT_PATH  = "DWIN_SET/14ShowFile.bin"

# ── Record builders ────────────────────────────────────────────────────────────

def make_text_record(vp_addr, x, y, w, h, color=0xFFFF, font=0x001E,
                     unk=0x0000, cw=12, ch=12, flags=0x42000000):
    """Build a 32-byte 0x5A11 VP variable-length text display record.

    x/y/w/h here are position + size, as every call site expects. The two
    fields after the second (x,y) pair are NOT a raw w/h — they're the
    absolute bottom-right corner (x2 = x+w, y2 = y+h). Confirmed 2026-08-02
    against a real, shipped, working reference build (wabbitguy's
    anycubic-kobra-dark-ui V1.5): e.g. its right-side status VP has
    x=193, "field"=243 — impossible as a width (193+243 exceeds the 272px
    screen) but exactly right as an absolute x2 (a 50px-wide box ending at
    243). Packing raw w/h there (as this function did before) silently
    produces a degenerate/negative-width box whenever x >= w — which was
    the actual root cause of the bed-temp-never-renders bug (any box placed
    right of screen center had x > w for reasonable widths).
    """
    x2, y2 = x + w, y + h
    return struct.pack(
        '>HHHHHHHHHHHH',
        0x5A11, 0xFFFF, 0x000D, vp_addr,
        x, y, color, x, y, x2, y2, font,
    ) + struct.pack('>H', unk) + bytes([cw, ch]) + struct.pack('>I', flags)


def make_integer_record(vp_addr, x, y, digits=3):
    """Build a 32-byte 0x5A10 VP integer display record.

    Format (reverse-engineered from base.bin):
      5A10 FFFF 000D [vp] [x] [y] FFFF 000A 02 [digits] 00×14
    """
    hdr  = struct.pack('>HHHHHH', 0x5A10, 0xFFFF, 0x000D, vp_addr, x, y)
    tail = struct.pack('>HH', 0xFFFF, 0x000A) + bytes([0x02, digits])
    return hdr + tail + b'\x00' * 14


def make_image_animation_record(pic_begin, pic_end, frame_time, icl_lib_id=0):
    """Build a 32-byte 0x5A04 Image Animation record.

    Format confirmed against a real, shipped, working build (wabbitguy's
    anycubic-kobra-dark-ui V1.5 release, DWIN_SET/14ShowFile.bin page 51:
    5a04ffff0005000000320072050000...  ->  Pic_Begin=50 Pic_End=114
    Frame_Time=5 ICL_LIB_ID=0):
      5A04 FFFF 0005 0000 [pic_begin] [pic_end] [frame_time] 00 [icl_lib_id] 00×16
    ICL_LIB_ID=0 addresses the project's single/main picture library (our
    16_68_.icl). An earlier attempt used icl_lib_id=1 (from a throwaway test
    project, not a real deployment) — that pointed at a nonexistent library
    and corrupted display rendering on hardware. frame_time is in units of 8ms.
    """
    hdr = struct.pack('>HHHH', 0x5A04, 0xFFFF, 0x0005, 0x0000)
    rng = struct.pack('>HH', pic_begin, pic_end)
    tail = bytes([frame_time, 0x00]) + struct.pack('>H', icl_lib_id)
    return hdr + rng + tail + b'\x00' * 16


def make_icon_animation_record(x, y, start_icon, end_icon, icon_lib,
                                frame_time=12, stop_icon=None, vp_addr=0x0000,
                                v_start=1, v_stop=0, opaque=False):
    """Build a 32-byte 0x5A01 Animation Icon record.

    Field order confirmed two ways: byte-diffing real DGUS IDE output (2026-08-02) and DWIN's own
    "T5L DGUSII Application Development Guide" section 7.3.1 (v2.8 PDF, p.126):

      5A01 FFFF 000D [vp] [x] [y] [Reset_ICON_En] [V_Stop] [V_Start] [ICON_Stop] [ICON_Start]
      [ICON_End] [ICON_Lib:1B] [Mode:1B] [Layer_Mode:1B] [ICON_Gamma:1B] [PIC_Gamma:1B] [Time:1B]
      [Display_mode:1B] [Filter_Set:1B]

    HOW IT RUNS (guide 7.3.3 — this is what the earlier attempts missed): the control is NOT free-
    running. It plays only while the variable at `vp_addr` equals V_Start (loop mode), and shows
    ICON_Stop for any other value. V_Start and V_Stop must therefore differ, and the firmware has to
    WRITE V_Start to the VP (5A A5 05 82 <vp> <V_Start>) to start it and V_Stop to stop it. The old
    defaults (v_start = v_stop = 0, nothing ever written) left it permanently stopped.

    icon_lib is the leading number of the icon library file name (23 for 23_ICO.icl). `Time` is in
    DGUS cycles (guide: 0x01-0xFF). Mode 0x00 = transparent background (colour-key filtered), any other
    value = opaque. Display_mode 0 = loop (used here); 1 = single play, driven forward/backward by
    V_Start / V_Stop.
    """
    if stop_icon is None:
        stop_icon = start_icon
    hdr = struct.pack('>HHHHHH', 0x5A01, 0xFFFF, 0x000D, vp_addr, x, y)
    reset_icon_en = struct.pack('>H', 0x0000)
    vrange = struct.pack('>HH', v_stop, v_start)
    icons = struct.pack('>HHH', stop_icon, start_icon, end_icon)
    tail = bytes([icon_lib & 0xFF, 0x01 if opaque else 0x00, 0x00, 0x00, 0x00, frame_time & 0xFF])
    return hdr + reset_icon_en + vrange + icons + tail + b'\x00' * 2


def make_process_bar_record(vp_addr, x0, y0, x1, y1, border, fg, bg, vmax=100, vmin=0):
    """Build a 32-byte 0x5A23 Process Bar record (DWIN T5L DGUS II guide 7.23.1).

      5A23 FFFF 000D [vp] [Xs] [Ys] [Xe] [Ye] [border] [foreground] [background] [max] [min]
      [Mode:1B][Direction:1B] [Type:1B][reserved:1B] [VP_RT]

    The bar shows (value - min) / (max - min) of the integer at `vp_addr`, filled left to right.
    Mode 0x00 = draw the border and fill the background; Direction 0x00 = rightwards; Type 0x00 =
    integer; VP_RT 0 = do not return the percentage."""
    rec = struct.pack('>13H', 0x5A23, 0xFFFF, 0x000D, vp_addr, x0, y0, x1, y1,
                      border, fg, bg, vmax & 0xFFFF, vmin & 0xFFFF)
    rec += bytes([0x00, 0x00])            # Mode, Direction
    rec += bytes([0x00, 0x00])            # data type (integer), reserved
    rec += struct.pack('>H', 0x0000)      # VP_RT: no percentage returned
    assert len(rec) == 32
    return rec


# ── VP addresses (from dgus_tft.h) ────────────────────────────────────────────

# Status bar — every content page
TXT_MAIN_HOTEND  = 0x2030   # SendTxtToTFT — flame icon side (LEFT, x=40)
# Relocated from 0x2000 2026-07-26 — that address never rendered on hardware;
# must match dgus_tft.h's TXT_MAIN_BED exactly.
TXT_MAIN_BED     = 0x2880   # SendTxtToTFT — bed   icon side (RIGHT, x=176)

# File browser
TXT_FILE_0 = 0x2000 + 3 * 0x30   # 0x2090
TXT_FILE_1 = 0x2000 + 4 * 0x30   # 0x20C0
TXT_FILE_2 = 0x2000 + 5 * 0x30   # 0x20F0
TXT_FILE_3 = 0x2000 + 6 * 0x30   # 0x2120
TXT_FILE_4 = 0x2000 + 7 * 0x30   # 0x2150

# Print status (pages 3/4)
TXT_PRINT_NAME     = 0x2000 + 8  * 0x30   # 0x2180 — also TXT_OUTAGE_RECOVERY_FILE
TXT_PRINT_SPEED    = 0x2000 + 9  * 0x30   # 0x21B0
TXT_PRINT_TIME     = 0x2000 + 10 * 0x30   # 0x21E0
TXT_PRINT_PROGRESS = 0x2000 + 11 * 0x30   # 0x2210 — also TXT_OUTAGE_RECOVERY_PROGRESS
TXT_PRINT_COMMENT  = 0x2000 + 12 * 0x30   # 0x2240
TXT_PRINT_FULLNAME = 0x2000 + 13 * 0x30   # 0x2270 — thumbnail full-width filename (page 214)

# Print adjust / print-settings-light (pages 5, 211/212)
TXT_ADJUST_HOTEND = 0x2000 + 14 * 0x30   # 0x22A0 — SendValueToTFT
TXT_ADJUST_BED    = 0x2000 + 15 * 0x30   # 0x22D0 — SendValueToTFT
TXT_ADJUST_SPEED  = 0x2000 + 16 * 0x30   # 0x2300 — SendValueToTFT

# Temperature page (9)
TXT_BED_NOW       = 0x2000 + 17 * 0x30   # 0x2330 — SendValueToTFT
TXT_BED_TARGET    = 0x2000 + 18 * 0x30   # 0x2360 — SendValueToTFT
TXT_HOTEND_NOW    = 0x2000 + 19 * 0x30   # 0x2390 — SendValueToTFT
TXT_HOTEND_TARGET = 0x2000 + 20 * 0x30   # 0x23C0 — SendValueToTFT

# Speed page (10)
TXT_FAN_SPEED_NOW      = 0x2000 + 21 * 0x30   # 0x23F0 — SendValueToTFT
TXT_FAN_SPEED_TARGET   = 0x2000 + 22 * 0x30   # 0x2420 — SendValueToTFT
TXT_PRINT_SPEED_NOW    = 0x2000 + 23 * 0x30   # 0x2450 — SendValueToTFT
TXT_PRINT_SPEED_TARGET = 0x2000 + 24 * 0x30   # 0x2480 — SendValueToTFT

# About page (13/133)
# NOTE: TXT_ABOUT_* and TXT_STATS_* share VP addresses — same display RAM, different page contexts.
#   0x2690 = TXT_ABOUT_FW_VERSION  = TXT_STATS_PRINTS_TOTAL
#   0x2750 = TXT_ABOUT_DEVICE_NAME = TXT_STATS_PRINTS_FINISHED
#   0x2770 = TXT_ABOUT_PRINT_VOLUMN= TXT_STATS_PRINTS_FAILED
#   0x2790 = TXT_ABOUT_TECH_SUPPORT= TXT_STATS_PRINTS_TIME
# Do NOT allocate new VPs in this range without checking both pages.
TXT_ABOUT_FW_VERSION  = 0x2690
TXT_ABOUT_DEVICE_NAME = 0x2750
TXT_ABOUT_PRINT_VOLUMN = 0x2770
TXT_ABOUT_TECH_SUPPORT = 0x2790

# Print finish (22)
TXT_FINISH_TIME = 0x2000 + 34 * 0x30   # 0x2660 — SendTxtToTFT

# Z offset / level advance (17)
TXT_LEVEL_OFFSET = 0x2000 + 32 * 0x30   # 0x2600 — SendTxtToTFT

# Filament (19)
TXT_FILAMENT_TEMP = 0x2000 + 33 * 0x30   # 0x2630 — SendTxtToTFT

# Preheat (18)
TXT_PREHEAT_HOTEND = 0x2000 + 36 * 0x30   # 0x26C0 — SendTxtToTFT
TXT_PREHEAT_BED    = 0x2000 + 37 * 0x30   # 0x26F0 — SendTxtToTFT

# Stats page (93/213)
TXT_STATS_PRINTS_TOTAL    = 0x2690
TXT_STATS_PRINTS_FINISHED = 0x2750
TXT_STATS_PRINTS_FAILED   = 0x2770
TXT_STATS_PRINTS_TIME     = 0x2790
TXT_STATS_PRINTS_LONGEST  = 0x2810
TXT_STATS_PRINTS_FILAMENT = 0x2830

# Enforce that About and Stats share the same display-RAM addresses.
assert TXT_ABOUT_FW_VERSION   == TXT_STATS_PRINTS_TOTAL,    "VP alias broken"
assert TXT_ABOUT_DEVICE_NAME  == TXT_STATS_PRINTS_FINISHED, "VP alias broken"
assert TXT_ABOUT_PRINT_VOLUMN == TXT_STATS_PRINTS_FAILED,   "VP alias broken"
assert TXT_ABOUT_TECH_SUPPORT == TXT_STATS_PRINTS_TIME,     "VP alias broken"

# Input shaping (6/126)
TXT_IS_FREQ_X = 0x2860
TXT_IS_FREQ_Y = 0x2890
TXT_IS_ZETA_X = 0x28C0
TXT_IS_ZETA_Y = 0x28F0

# Live status line on the 'please wait' pages (homing, leveling, pausing, ...). The baked-in
# spinner cannot be animated by the firmware, so progress is written here as text instead.
TXT_WAIT_STATUS = 0x2A80

# Start/stop value of the spinner Animation Icon on the wait pages (a plain 16-bit value, not text):
# the display plays the animation while this VP holds 1. Kept clear of the 0x30-word windows of the
# text VPs around it.
TXT_WAIT_ANIM = 0x2B00

# Integer values that drive Process Bar controls (0-100 %). Written by the firmware.
TXT_PRINT_BAR = 0x2B20      # print progress, pages 3/4
TXT_WAIT_BAR  = 0x2B30      # leveling progress, pages 34/154

# Move Axes: selected step size shown as text (buttons carry no state)
TXT_MOVE_STEP = 0x2AB0

# Terminal (215)
TXT_TERM_INPUT = 0x2A10
TXT_TERM_L0    = 0x2920
TXT_TERM_L1    = 0x2950
TXT_TERM_L2    = 0x2980
TXT_TERM_L3    = 0x29B0
TXT_TERM_L4    = 0x29E0

# ── Shared record sets ─────────────────────────────────────────────────────────
# W=272, H=480, CONTENT_Y1=92, MARGIN=8, STATUS_Y2=54
#
# Status bar layout (generate_screens.py status_bar()):
#   flame icon at x=4 → hotend VP at (40,13,92,28) → TXT_MAIN_HOTEND (0x2030)
#   bed   icon at x=140 → bed VP at (176,13,92,28) → TXT_MAIN_BED   (0x2880)

STATUS_BAR = [
    make_text_record(TXT_MAIN_HOTEND, 40,  13, 92, 28),
    make_text_record(TXT_MAIN_BED,   176,  13, 92, 28),
]

# RGB565 colours for Process Bar controls (match generate_screens: DIVIDER, ORANGE, BG_ELEVATED)
def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

COLOR_BAR_BORDER = rgb565(50, 50, 55)
COLOR_BAR_BG     = rgb565(42, 42, 42)
COLOR_ORANGE     = rgb565(255, 107, 53)   # 0xFB46

# ── Page record sets (coordinates from generate_screens.py vp_area() calls) ───

# Pages 2/122 — File Browser
# page_file_browser(): ROW_H=54; row i: y1=CONTENT_Y1+i*54=92+i*54, y2=y1+52
# VP: (MARGIN+28=36, y1+8, W-MARGIN=264, y2-8) → w=228, h=36
PAGE2 = STATUS_BAR + [
    make_text_record(TXT_FILE_0, 36, 100, 228, 36),   # row 0: y1=92
    make_text_record(TXT_FILE_1, 36, 154, 228, 36),   # row 1: y1=146
    make_text_record(TXT_FILE_2, 36, 208, 228, 36),   # row 2: y1=200
    make_text_record(TXT_FILE_3, 36, 262, 228, 36),   # row 3: y1=254
    make_text_record(TXT_FILE_4, 36, 316, 228, 36),   # row 4: y1=308
]

# Pages 3/4/123/124 — Print Status (printing / paused — identical VP layout)
# _page_status(): y starts at CONTENT_Y1+8=100
#   FILE label (+14→114): vp(8,114,264,144) w=256 h=30 ; +40→154
#   PROGRESS label (+14→168): vp(222,168,264,192) w=42 h=24 ; +34→202
#   ELAPSED/SPEED at y=212: vp(8,212,138,240) w=130 h=28 ; vp(142,212,264,240) w=122 h=28 ; +38→250
#   STATUS label (+14→264): vp(8,264,264,294) w=256 h=30
#   (verified against the art by tools/cross_check_display.py)
#   Progress track (8,168)-(218,192): a Process Bar control driven by TXT_PRINT_BAR (0-100)
PAGE3 = STATUS_BAR + [
    make_text_record(TXT_PRINT_NAME,     8,   114, 256, 30),
    make_text_record(TXT_PRINT_PROGRESS, 222, 168,  42, 24),
    make_text_record(TXT_PRINT_TIME,     8,   212, 130, 28),
    make_text_record(TXT_PRINT_SPEED,    142, 212, 122, 28),
    make_text_record(TXT_PRINT_COMMENT,  8,   264, 256, 30),
] + ([make_process_bar_record(TXT_PRINT_BAR, 8, 168, 218, 192,
                              COLOR_BAR_BORDER, COLOR_ORANGE, COLOR_BAR_BG)] if uf.PROGRESS_BARS else [])
PAGE4 = PAGE3   # paused vs printing — identical VP layout

# Pages 5/125 — Print Adjust
# page_print_adjust(): y starts at CONTENT_Y1+10=102
#   Z-OFFSET label (+18→120): vp(68,120,204,156) w=136 h=36 ; +50→170
#   HOTEND  label (+18→188): vp(8,188,264,222) w=256 h=34 ; +46→234
#   BED     label (+18→252): vp(8,252,264,286) w=256 h=34 ; +46→298
#   SPEED   label (+18→316): vp(8,316,264,350) w=256 h=34
# Pages 5/125, 211/212 — Print Settings: rows come from ui_features.PRINT_SETTINGS_ROWS, value box
# (68,y)-(204,y+36). Z offset is text; hotend / bed / speed / fan are integer values the firmware
# writes (and updates itself when a - / + button is pressed).
_PS_VPS = (None, TXT_ADJUST_HOTEND, TXT_ADJUST_BED, TXT_ADJUST_SPEED, TXT_FAN_SPEED_TARGET)
PAGE5 = STATUS_BAR + [make_text_record(TXT_LEVEL_OFFSET, 68, uf.PRINT_SETTINGS_ROWS[0][1], 136, 36)] + [
    make_integer_record(vp, 76, row[1] + 8)
    for row, vp in zip(uf.PRINT_SETTINGS_ROWS, _PS_VPS) if vp is not None
]

# Pages 6/126 — Input Shaping
# page_input_shaping(): y starts at CONTENT_Y1+10=102; per row: label(+18), vp(66,y,206,y+34)(+48)
# Row 0 X_FREQ: y=120; Row 1 Y_FREQ: y=186; Row 2 X_ZETA: y=252; Row 3 Y_ZETA: y=318
PAGE6 = STATUS_BAR + [
    make_text_record(TXT_IS_FREQ_X, 66, 120, 140, 34),
    make_text_record(TXT_IS_FREQ_Y, 66, 186, 140, 34),
    make_text_record(TXT_IS_ZETA_X, 66, 252, 140, 34),
    make_text_record(TXT_IS_ZETA_Y, 66, 318, 140, 34),
]

# Pages 8/128 — Move Axes: selected step size, right of the 'STEP SIZE' label
# 10x20 dot ASCII font (the guide: 0# font has every ASCII glyph from 4x8 to 64x128), orange so the
# selection stands out next to the grey step buttons.
PAGE8 = STATUS_BAR + [
    make_text_record(TXT_MOVE_STEP, 96, 94, 168, 20, color=COLOR_ORANGE, cw=10, ch=20),
]

# 'Please wait' pages — homing 177/189, leveling 34/154, probe preheat 175/176, pausing 32/152,
# stopping 23/143, probe test 201/204 (no status line). One entry per badge in ui_features.WAIT_BADGES:
#   - status line: art box (8,340)-(264,364), written by DgusTFT::WaitStatus
#   - leveling also gets a Process Bar (art track (8,312)-(264,332)) showing probe points done
#   - with SPINNER_ANIMATION, an Animation Icon laid exactly over the static badge
def _spinner_record(b):
    s = uf.SPINNER_SIZE
    return make_icon_animation_record(
        x=136 - s // 2, y=b['cy'] - s // 2,
        start_icon=b['first'], end_icon=b['first'] + uf.SPINNER_FRAMES - 1,
        stop_icon=b['first'] + uf.SPINNER_FRAMES,
        icon_lib=uf.SPINNER_ICON_LIB, frame_time=uf.SPINNER_FRAME_TIME,
        vp_addr=TXT_WAIT_ANIM, v_start=1, v_stop=0, opaque=True)


def _wait_records(name, b):
    recs = list(STATUS_BAR)
    if name != 'probe':
        recs.append(make_text_record(TXT_WAIT_STATUS, 8, 342, 256, 20, cw=10, ch=20))
    if name == 'leveling' and uf.PROGRESS_BARS:
        recs.append(make_process_bar_record(TXT_WAIT_BAR, 8, 312, 264, 332,
                                            COLOR_BAR_BORDER, COLOR_ORANGE, COLOR_BAR_BG))
    if uf.SPINNER_ANIMATION:
        recs.append(_spinner_record(b))
    return recs


WAIT_PAGES = [(pg, _wait_records(name, b)) for name, b in uf.WAIT_BADGES.items() for pg in b['pages']]

# Pages 9/129 — Temperature
# _temp_speed_page(): y starts at CONTENT_Y1+12=104
#   HOTEND row: label(+22→126), NOW/TGT labels(+14→140)
#     NOW (8,140,122,174) w=114 h=34 ; TARGET (130,140,264,174) w=134 h=34 ; +44+46+10→240
#   BED row: label(+22→262), NOW/TGT labels(+14→276)
#     NOW (8,276,122,310) w=114 h=34 ; TARGET (130,276,264,310) w=134 h=34
PAGE9 = STATUS_BAR + [
    make_integer_record(TXT_HOTEND_NOW,    8,   140),
    make_integer_record(TXT_HOTEND_TARGET, 130, 140),
    make_integer_record(TXT_BED_NOW,       8,   276),
    make_integer_record(TXT_BED_TARGET,    130, 276),
]

# Pages 10/130 — Speed & Fan  (same pixel layout as page 9)
PAGE10 = STATUS_BAR + [
    make_integer_record(TXT_FAN_SPEED_NOW,      8,   140),
    make_integer_record(TXT_FAN_SPEED_TARGET,   130, 140),
    make_integer_record(TXT_PRINT_SPEED_NOW,    8,   276),
    make_integer_record(TXT_PRINT_SPEED_TARGET, 130, 276),
]

# Pages 13/133 — About
# page_about(): y starts at CONTENT_Y1+16=108; per row: label(+14), vp(8,y,264,y+34)(+46)
#   Row 1 MACHINE:   VP (8,122,256,34) — TXT_ABOUT_DEVICE_NAME
#   Row 2 FIRMWARE:  VP (8,182,256,34) — TXT_ABOUT_FW_VERSION
#   Row 3 VOLUME:    VP (8,242,256,34) — TXT_ABOUT_PRINT_VOLUMN
#   Row 4 SUPPORT:   VP (8,302,256,34) — TXT_ABOUT_TECH_SUPPORT
PAGE13 = STATUS_BAR + [
    make_text_record(TXT_ABOUT_DEVICE_NAME,  8, 122, 256, 34),
    make_text_record(TXT_ABOUT_FW_VERSION,   8, 182, 256, 34),
    make_text_record(TXT_ABOUT_PRINT_VOLUMN, 8, 242, 256, 34),
    make_text_record(TXT_ABOUT_TECH_SUPPORT, 8, 302, 256, 34),
]

# Pages 14/134 — Print History — assigned after PAGE93 is defined below

# Pages 17/137 — Z Offset Adjust
# page_level_advance(): y starts at CONTENT_Y1+24=116; label(+18→134)
#   vp(8,134,264,188) w=256 h=54
PAGE17 = STATUS_BAR + [
    make_text_record(TXT_LEVEL_OFFSET, 8, 134, 256, 54),
]

# Pages 18/138 — Preheat
# page_preheat(): y starts at CONTENT_Y1+14=106
#   HOTEND row: label(+22→128), NOW/TGT labels(+14→142)
#     Firmware writes TXT_PREHEAT_HOTEND to NOW box at (8,142,122,174) w=114 h=32
#   separator+gap → y=196; BED row: label(+22→218), NOW/TGT labels(+14→232)
#     Firmware writes TXT_PREHEAT_BED to NOW box at (8,232,122,264) w=114 h=32
#   The firmware writes "actual/target" into one full-width box per heater (the old separate,
#   never-filled TARGET boxes were removed from the art).
PAGE18 = STATUS_BAR + [
    make_text_record(TXT_PREHEAT_HOTEND, 8, 142, 256, 34),
    make_text_record(TXT_PREHEAT_BED,    8, 234, 256, 34),
]

# Pages 19/139 — Filament
# page_filament(): y starts at CONTENT_Y1+16=108; label(+16→124)
#   vp(8,124,264,158) w=256 h=34
PAGE19 = STATUS_BAR + [
    make_text_record(TXT_FILAMENT_TEMP, 8, 124, 256, 34),
]

# Pages 22/142 — Print Finish
# page_print_finish(): y starts at CONTENT_Y1+80=172; label(+14→186)
#   vp(8,186,264,222) w=256 h=36
PAGE22 = STATUS_BAR + [
    make_text_record(TXT_FINISH_TIME, 8, 186, 256, 36),
]

# Pages 93/213/14/134 — Printer Statistics
# page_stats() compact layout: h=24 rows, step=38; fits BACK footer.
#   y = CONTENT_Y1+8=100; per row: label(+14), vp(8,y,264,y+24)(+38)
#   Row 1 TOTAL PRINTS:    VP (8,114,256,24)  last row ends at 374+24=398 < FOOTER_Y1=422 ✓
#   Row 2 FINISHED:        VP (8,166,256,24)
#   Row 3 FAILED:          VP (8,218,256,24)
#   Row 4 TOTAL TIME:      VP (8,270,256,24)
#   Row 5 LONGEST PRINT:   VP (8,322,256,24)
#   Row 6 FILAMENT USED:   VP (8,374,256,24)
PAGE93 = STATUS_BAR + [
    make_text_record(TXT_STATS_PRINTS_TOTAL,    8, 114, 256, 24),
    make_text_record(TXT_STATS_PRINTS_FINISHED, 8, 166, 256, 24),
    make_text_record(TXT_STATS_PRINTS_FAILED,   8, 218, 256, 24),
    make_text_record(TXT_STATS_PRINTS_TIME,     8, 270, 256, 24),
    make_text_record(TXT_STATS_PRINTS_LONGEST,  8, 322, 256, 24),
    make_text_record(TXT_STATS_PRINTS_FILAMENT, 8, 374, 256, 24),
]
# Pages 14/134 — Print History uses the same stats layout as pages 93/213.
# firmware page14_handle calls printerStatsToTFT() which writes to TXT_STATS_* addresses.
PAGE14 = PAGE93

# Pages 171/173 — Power Loss Recovery  (TXT_OUTAGE_RECOVERY_FILE = TXT_PRINT_NAME = 0x2180)
# page_outage_recovery(): y starts at CONTENT_Y1+72=164
#   FILE label (+14→178): vp(8,178,264,212) w=256 h=34 ; +46→224
#   PROGRESS label (+14→238): vp(8,238,264,272) w=256 h=34
PAGE171 = STATUS_BAR + [
    make_text_record(TXT_PRINT_NAME,     8, 178, 256, 34),   # TXT_OUTAGE_RECOVERY_FILE
    make_text_record(TXT_PRINT_PROGRESS, 8, 238, 256, 34),   # TXT_OUTAGE_RECOVERY_PROGRESS
]

# Pages 211/212 — Print Settings with Light
# page_print_settings_light(): y starts at CONTENT_Y1+10=102
#   Z-OFFSET label(+18→120): vp(68,120,204,154) w=136 h=34 ; +48→168
#   HOTEND label(+18→186): vp(8,186,264,218) w=256 h=32 ; +44→230
#   BED    label(+18→248): vp(8,248,264,280) w=256 h=32 ; +44→292
#   SPEED  label(+18→310): vp(8,310,264,342) w=256 h=32
PAGE211 = PAGE5   # same layout; 211/212 differ only in the art (the title-bar bulb)
PAGE212 = PAGE211   # ENG variant — identical pixel layout

# Page 214 — Thumbnail: filename right panel + full-width row below thumbnail + status bar
# page_thumbnail(): tw=160, ix=174; right-panel vp(174,118,90,28); full-width vp(8,310,256,30)
PAGE214 = STATUS_BAR + [
    make_text_record(TXT_PRINT_NAME,    174, 118,  90, 28),  # right-panel (short area next to thumbnail)
    make_text_record(TXT_PRINT_FULLNAME,  8, 310, 256, 30),  # full-width below thumbnail
]

# Page 215 — Terminal: 5 log lines + preset command buttons + status bar
# page_terminal(): 5 rows starting at y=CONTENT_Y1=92, each row 38px tall.
#   Row i: draw at y=92+i*38; vp(MARGIN+14=22, y+4, W-MARGIN=264, y+32) w=242 h=28
#   Row 0: vp(22,  96, 242, 28)  Row 4: vp(22, 248, 242, 28)
# Command buttons have no VP records (they enqueue G-code directly via key press).
PAGE215 = STATUS_BAR + [
    make_text_record(TXT_TERM_L0,   22,  98, 242, 20, cw=10, ch=20),
    make_text_record(TXT_TERM_L1,   22, 136, 242, 20, cw=10, ch=20),
    make_text_record(TXT_TERM_L2,   22, 174, 242, 20, cw=10, ch=20),
    make_text_record(TXT_TERM_L3,   22, 212, 242, 20, cw=10, ch=20),
    make_text_record(TXT_TERM_L4,   22, 250, 242, 20, cw=10, ch=20),
]

# Pages 216/217 — Thermal Tuning / Factory Reset confirm
# Both call status_bar() but have no VP content areas — status bar only.
PAGE216 = STATUS_BAR
PAGE217 = STATUS_BAR

# ── Build complete patches list ────────────────────────────────────────────────

# Pages that need only the status-bar VP records (static content, no live data).
# This covers every page in the firmware's navigation flow that has a status bar
# but no other dynamic VP overlays.
_STATUS_ONLY = [
    # CHS core pages with no content VPs
    1, 7, 11, 12, 15, 16,
    20, 21, 24, 25, 26, 27, 28, 29, 30, 31, 33,
    # ENG mirrors of the above (all +120)
    121, 127, 131, 132, 135, 136,
    140, 141, 144, 145, 146, 147, 148, 149, 150, 151, 153,
    # Standalone system/utility pages
    115,   # auto Z offset
    117,   # system CHS audio-off
    170,   # system ENG audio-off
    # CHS error/status pages (177-188: homing, heater/therm/endstop faults)
    *range(178, 189),
    # ENG error/status pages (189-200: same pages +12)
    *range(190, 201),
    # Probe precheck / probe ok / probe failed (CHS 201-203, ENG 204-206)
    202, 203, 205, 206,    # 201/204 (probe test) are in WAIT_PAGES
    # Tools + case light variants
    207, 209,
]

# Content-VP pages: (page_number, records_list)
_CONTENT = [
    # CHS
    (2,   PAGE2),
    (3,   PAGE3),
    (4,   PAGE4),
    (5,   PAGE5),
    (6,   PAGE6),
    (9,   PAGE9),
    (10,  PAGE10),
    (13,  PAGE13),
    (17,  PAGE17),
    (18,  PAGE18),
    (19,  PAGE19),
    (22,  PAGE22),
    (93,  PAGE93),
    (171, PAGE171),
    (211, PAGE211),
    # Boot splash: the stock page-0 records (a message line and a temperature) would print over it
    (0,   []),
    # ENG mirrors
    (122, PAGE2),
    (123, PAGE3),
    (124, PAGE4),
    (125, PAGE5),
    (126, PAGE6),
    (129, PAGE9),
    (130, PAGE10),
    (133, PAGE13),
    (137, PAGE17),
    (138, PAGE18),
    (139, PAGE19),
    (142, PAGE22),
    (173, PAGE171),
    (212, PAGE212),
    (213, PAGE93),
    # Move Axes + wait pages (live status text)
    (8, PAGE8), (128, PAGE8),
    *WAIT_PAGES,
    # Language-neutral custom pages
    (214, PAGE214),
    (215, PAGE215),
    (216, PAGE216),
    (217, PAGE217),
]

patches = [(pg, STATUS_BAR) for pg in _STATUS_ONLY] + _CONTENT

# ── Load base ──────────────────────────────────────────────────────────────────

with open(BASE_PATH, 'rb') as f:
    data = bytearray(f.read())

base_count = int.from_bytes(data[8:10], 'big')
print(f"Base: {len(data)} bytes, {base_count} pages")
assert base_count == 215, f"Unexpected base page count {base_count} — wrong base file?"

# ── Find end of existing data section ─────────────────────────────────────────

max_end = 0
for i in range(base_count):
    tbl = 16 + i * 4
    n   = int.from_bytes(data[tbl:tbl+2], 'little')
    off = int.from_bytes(data[tbl+2:tbl+4], 'big')
    if n > 0:
        end = off + n * 32
        if end > max_end:
            max_end = end

print(f"Base data end: 0x{max_end:04X} ({max_end})")

# ── Build records to append ────────────────────────────────────────────────────

append_buf = bytearray()
updates    = {}   # page_num -> (n, file_offset)

for page_num, records in patches:
    file_off = max_end + len(append_buf)
    for rec in records:
        assert len(rec) == 32, f"Record for page {page_num} is {len(rec)} bytes, expected 32"
        append_buf += rec
    updates[page_num] = (len(records), file_off)

# ── Extend file and rewrite page-table entries ─────────────────────────────────

new_end = max_end + len(append_buf)
assert new_end <= 0xFFFF, (
    f"14ShowFile.bin data section too large ({new_end:#x}); "
    "page-table offsets are 2-byte BE — split or reduce records"
)
if new_end > len(data):
    data.extend(b'\xFF' * (new_end - len(data)))
data[max_end:max_end + len(append_buf)] = append_buf

# Update page table.  The table is indexed by DGUS PAGE ID starting at 0 (page 0 is the boot page):
# entry for page N is at 16 + 4*N. Verified against the stock base file, where the file-list page
# (ID 2) is at table index 2 and the Temperature page (ID 9) at index 9 — the previous
# "(page_num - 1)" put every page's records on the page BEFORE it (e.g. the Temperature page's four
# number boxes appeared on Move Axes, and the homing page's records on page 176/188).
# Pages 215-217 are beyond the base count (215 entries: IDs 0-214), but the base.bin has ~15 KB of
# zero-padding between the table end (byte 876) and the data section start (0x4000), so writing
# entries at offsets 876/880/884 is safe.
for page_num, (n, off) in updates.items():
    tbl = 16 + page_num * 4
    while tbl + 4 > len(data):
        data.extend(b'\x00' * 16)
    data[tbl:tbl+2]   = n.to_bytes(2, 'little')
    data[tbl+2:tbl+4] = off.to_bytes(2, 'big')

# ── Extend count field 215 → 218 (page IDs 0..217) ────────────────────────────

NEW_COUNT = 218
data[8:10] = NEW_COUNT.to_bytes(2, 'big')

# ── Write output ───────────────────────────────────────────────────────────────

with open(OUT_PATH, 'wb') as f:
    f.write(data)

print(f"Wrote {len(data)} bytes to {OUT_PATH}")
print(f"Pages patched: {len(patches)}")

# ── Verify ─────────────────────────────────────────────────────────────────────

with open(OUT_PATH, 'rb') as f:
    check = f.read()

got_count = int.from_bytes(check[8:10], 'big')
print(f"Count field: {got_count}  {'OK' if got_count == NEW_COUNT else 'WRONG'}")

ok_all = True
for page_num, (n, expected_off) in sorted(updates.items()):
    tbl     = 16 + page_num * 4
    got_n   = int.from_bytes(check[tbl:tbl+2], 'little')
    got_off = int.from_bytes(check[tbl+2:tbl+4], 'big')
    ok = got_n == n and got_off == expected_off
    ok_all = ok_all and ok
    if not ok:
        print(f"  [FAIL] Page {page_num:3d}: n={got_n} (exp {n}), off=0x{got_off:04X} (exp 0x{expected_off:04X})")

if ok_all:
    print(f"All {len(patches)} page checks OK")
else:
    print("*** SOME CHECKS FAILED ***")
