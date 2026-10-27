#!/usr/bin/env python3
"""
KobraMax-HC32 DGUS Screen Generator
Generates 24-bit BMP background images for the Kobra Max DWIN display (272x480).

Run from the project root:
    python tools/generate_screens.py

Output: DWIN_SET/ folder with all .bmp files ready to copy to SD card.
"""

import os
import sys
import functools
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_features as uf   # feature flags + values read from the firmware sources
import press_effect as pe  # which picture shows while a button is held
import generate_dwin_controls as gc   # touch zones (pressed pictures are cut out along them)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

W, H     = 272, 480
OUT_DIR  = "DWIN_SET"

# Colours (R, G, B)
BG_DARK      = (18,  18,  18)
BG_SURFACE   = (30,  30,  30)
BG_ELEVATED  = (42,  42,  42)
ORANGE       = (255, 107,  53)
TEAL         = ( 78, 205, 196)
WHITE        = (255, 255, 255)
GRAY         = (170, 170, 170)
DGRAY        = ( 70,  70,  80)
SUCCESS      = ( 69, 182,  73)
WARNING      = (255, 165,   0)
ERROR        = (255,  68,  68)
DIVIDER      = ( 50,  50,  55)

# Layout zones
STATUS_Y2  = 54
TITLE_Y2   = 92
CONTENT_Y1 = 92
CONTENT_Y2 = 422
FOOTER_Y1  = 422
FOOTER_Y2  = 480
MARGIN     = 8

# ─────────────────────────────────────────────────────────────────────────────
# FONTS
# ─────────────────────────────────────────────────────────────────────────────

_FONT_REG = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
]
_FONT_BOLD = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
]

def _first(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None

_REG_PATH  = _first(_FONT_REG)
_BOLD_PATH = _first(_FONT_BOLD) or _REG_PATH

def font(size, bold=False):
    path = _BOLD_PATH if bold else _REG_PATH
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()

F_TINY  = font(11)
F_SMALL = font(13)
F_BODY  = font(15)
F_LABEL = font(17, bold=True)
F_TITLE = font(20, bold=True)
F_BIG   = font(28, bold=True)
F_HUGE  = font(40, bold=True)

# Font Awesome 6 Free Solid — downloaded to tools/fonts/
_FA_PATH = os.path.join(os.path.dirname(__file__), 'fonts', 'fa-solid-900.ttf')

@functools.lru_cache(maxsize=32)
def _fa(size):
    if os.path.exists(_FA_PATH):
        return ImageFont.truetype(_FA_PATH, size)
    return None

_FA_BTN = _fa(15)   # button icons (matches F_BODY)
_FA_ROW = _fa(20)   # row label icons — slightly larger than F_LABEL for legibility

# Common button label → FA codepoint (used by footer helpers)
_BTN_ICONS = {
    'BACK':              0xf060,   # arrow-left
    'PRINT':             0xf02f,   # print
    'RESUME':            0xf04b,   # play
    'STOP':              0xf04d,   # stop
    'PAUSE':             0xf04c,   # pause
    'SET':               0xf00c,   # check
    'SAVE':              0xf0c7,   # floppy-disk
    'SAVE  M500':        0xf0c7,
    'START  G29':        0xf05b,   # crosshairs
    'OK':                0xf058,   # circle-check
    'COOL':              0xf2dc,   # snowflake
    'CANCEL':            0xf00d,   # xmark
    'RESET':             0xf1f8,   # trash
    'OK - START HEATING': 0xf06d,  # fire
    'STOP PRINT':        0xf04d,   # stop
    'BACK TO PRINT':     0xf04b,   # play
    'OK  ->  MAIN MENU': 0xf015,   # house
}

# ─────────────────────────────────────────────────────────────────────────────
# DRAWING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def new_page():
    img  = Image.new('RGB', (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)
    return img, draw


def _bbox(draw, text, fnt):
    bb = draw.textbbox((0, 0), text, font=fnt)
    return bb[2] - bb[0], bb[3] - bb[1]


def text_center(draw, rect, text, fnt, color=WHITE):
    x1, y1, x2, y2 = rect
    tw, th = _bbox(draw, text, fnt)
    tx = x1 + (x2 - x1 - tw) // 2
    ty = y1 + (y2 - y1 - th) // 2
    draw.text((tx, ty), text, font=fnt, fill=color)


def text_left(draw, x, y, text, fnt, color=WHITE):
    draw.text((x, y), text, font=fnt, fill=color)


def separator(draw, y, color=DIVIDER):
    draw.line([(0, y), (W, y)], fill=color, width=1)


def vp_area(draw, x1, y1, x2, y2, placeholder='', visible=True):
    """Area where DGUS will overlay dynamic text from a VP. visible=False draws nothing: the text
    is laid straight over other art (the Move Axes step buttons)."""
    if not visible:
        return
    draw.rectangle([(x1, y1), (x2, y2)], fill=BG_DARK)
    draw.rectangle([(x1, y1), (x2, y2)], outline=(45, 45, 58), width=1)
    if placeholder:
        _, th = _bbox(draw, placeholder, F_BODY)
        draw.text((x1 + 4, y1 + (y2 - y1 - th) // 2),
                  placeholder, font=F_BODY, fill=BG_DARK)


def wait_status_box(draw, placeholder='Working ...'):
    """Live status line for the 'please wait' screens. The firmware cannot animate the
    baked-in spinner, so it writes progress text here instead (VP TXT_WAIT_STATUS)."""
    vp_area(draw, MARGIN, 340, W - MARGIN, 364, placeholder)


# ── Buttons ──────────────────────────────────────────────────────────────────

_STYLES = {
    'normal':  (BG_ELEVATED, WHITE),
    'primary': (ORANGE,      WHITE),
    'teal':    (TEAL,        BG_DARK),
    'danger':  (ERROR,       WHITE),
    'success': (SUCCESS,     WHITE),
    'warning': (WARNING,     BG_DARK),
    'ghost':   (BG_SURFACE,  GRAY),
}

_PRESSED = False   # True while generate_pressed() renders the 'button held' look


def _lighten(c, f=0.30):
    return tuple(int(v + (255 - v) * f) for v in c)


def btn(draw, x1, y1, x2, y2, label, style='normal', fnt=None, icon=None):
    fnt = fnt or F_BODY
    bg, fg = _STYLES.get(style, _STYLES['normal'])
    outline, outline_w = DIVIDER, 1
    if _PRESSED:   # lit-up fill and an orange rim so the press is obvious
        bg, outline, outline_w = _lighten(bg), ORANGE, 2
    draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=6, fill=bg)
    draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=6, outline=outline, width=outline_w)
    if icon and _FA_BTN:
        iw = _bbox(draw, chr(icon), _FA_BTN)[0]
        tw = _bbox(draw, label,     fnt)[0]
        gap = 5
        total_w = iw + gap + tw
        if total_w <= (x2 - x1 - 8):
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            ix = cx - total_w // 2
            draw.text((ix, cy), chr(icon), font=_FA_BTN, fill=fg, anchor='lm')
            draw.text((ix + iw + gap, cy), label, font=fnt, fill=fg, anchor='lm')
        else:
            text_center(draw, (x1, y1, x2, y2), label, fnt, color=fg)
    else:
        text_center(draw, (x1, y1, x2, y2), label, fnt, color=fg)


# ── Chrome bars ──────────────────────────────────────────────────────────────

def status_bar(draw):
    draw.rectangle([(0, 0), (W - 1, STATUS_Y2 - 1)], fill=BG_SURFACE)
    _flame(draw, 4, 10)
    vp_area(draw, 40, 13, 132, 41, '220/220C')
    draw.line([(136, 4), (136, 50)], fill=DIVIDER, width=1)
    _bed(draw, 140, 10)
    vp_area(draw, 176, 13, 268, 41, '60/60C')
    draw.line([(0, STATUS_Y2 - 1), (W, STATUS_Y2 - 1)], fill=ORANGE, width=2)


def title_bar(draw, text, color=ORANGE):
    draw.rectangle([(0, STATUS_Y2), (W - 1, TITLE_Y2 - 1)], fill=BG_SURFACE)
    text_center(draw, (0, STATUS_Y2, W, TITLE_Y2), text, F_TITLE, color=color)
    draw.line([(0, TITLE_Y2 - 1), (W, TITLE_Y2 - 1)], fill=DIVIDER, width=1)


def footer_bar(draw):
    draw.rectangle([(0, FOOTER_Y1), (W - 1, H - 1)], fill=BG_SURFACE)
    draw.line([(0, FOOTER_Y1), (W, FOOTER_Y1)], fill=DIVIDER, width=1)


def footer_1btn(draw, label, style='primary'):
    footer_bar(draw)
    btn(draw, MARGIN, FOOTER_Y1 + 7, W - MARGIN, FOOTER_Y2 - 7, label,
        style=style, icon=_BTN_ICONS.get(label))


def footer_2btn(draw, l_lbl, r_lbl, l_style='ghost', r_style='primary'):
    footer_bar(draw)
    mid = W // 2
    btn(draw, MARGIN,  FOOTER_Y1 + 7, mid - 4,    FOOTER_Y2 - 7, l_lbl,
        style=l_style, icon=_BTN_ICONS.get(l_lbl))
    btn(draw, mid + 4, FOOTER_Y1 + 7, W - MARGIN, FOOTER_Y2 - 7, r_lbl,
        style=r_style, icon=_BTN_ICONS.get(r_lbl))


def footer_3btn(draw, labels, styles=None):
    styles = styles or ['ghost', 'normal', 'primary']
    footer_bar(draw)
    bw = (W - MARGIN * 2 - 8) // 3
    for i, (lbl, sty) in enumerate(zip(labels, styles)):
        x1 = MARGIN + i * (bw + 4)
        x2 = (W - MARGIN) if i == len(labels) - 1 else (x1 + bw)
        btn(draw, x1, FOOTER_Y1 + 7, x2, FOOTER_Y2 - 7, lbl,
            style=sty, icon=_BTN_ICONS.get(lbl))


# ─────────────────────────────────────────────────────────────────────────────
# ICONS
# ─────────────────────────────────────────────────────────────────────────────

def _fa_centered(draw, cx, cy, cp, fnt, color=WHITE):
    if fnt:
        draw.text((cx, cy), chr(cp), font=fnt, fill=color, anchor='mm')


def _flame(draw, x, y, size=32):
    _fa_centered(draw, x + size // 2, y + size // 2, 0xf06d, _fa(size), ORANGE)


def _bed(draw, x, y, size=32):
    _fa_centered(draw, x + size // 2, y + size // 2, 0xf236, _fa(size), TEAL)


def _warning_tri(draw, cx, y, size=44, color=WARNING):
    _fa_centered(draw, cx, y + size // 2, 0xf071, _fa(size), color)


def _error_circle(draw, cx, cy, r=22, color=ERROR):
    _fa_centered(draw, cx, cy, 0xf057, _fa(r * 2), color)


def _check_circle(draw, cx, cy, r=22, color=SUCCESS):
    _fa_centered(draw, cx, cy, 0xf058, _fa(r * 2), color)


def _badge(draw, name):
    """Static badge for a wait screen; position/glyph/colour come from ui_features.WAIT_BADGES so the
    optional spinner animation can be drawn exactly over it."""
    b = uf.WAIT_BADGES[name]
    _wait_badge(draw, W // 2, b['cy'], b['glyph'], color=b['color'])


def _wait_badge(draw, cx, cy, icon, r=40, color=TEAL):
    """Static 'busy' badge: a ring with an icon that says WHAT is happening.

    The firmware cannot animate artwork on this display, and a frozen spinner reads as a hung
    screen. A purpose-specific static icon plus the live status text underneath (TXT_WAIT_STATUS,
    updated by DgusTFT::WaitStatus) shows progress honestly instead."""
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=color, width=3)
    _fa_centered(draw, cx, cy, icon, _fa(int(r * 0.95)), color)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def page_boot():
    img, draw = new_page()
    # Subtle warm gradient
    for row in range(H):
        v = int(18 + 16 * row / H)
        draw.line([(0, row), (W, row)], fill=(v, int(v * 0.6), int(v * 0.3)))
    text_center(draw, (0, 130, W, 196), "KOBRA MAX",        F_HUGE,  ORANGE)
    text_center(draw, (0, 202, W, 246), "KobraMax-HC32",   F_TITLE, TEAL)
    text_center(draw, (0, 252, W, 278), f"Marlin {uf.MARLIN_VERSION}  HC32F460", F_SMALL, GRAY)
    # Loading bar
    draw.rounded_rectangle([(36, 340), (W - 36, 360)], radius=6, outline=DIVIDER, width=1)
    draw.rounded_rectangle([(38, 342), (W // 2, 358)],  radius=4, fill=ORANGE)
    text_center(draw, (0, 366, W, 388), "Loading...", F_SMALL, GRAY)
    return img


def page_main():
    img, draw = new_page()
    status_bar(draw)
    text_center(draw, (0, 60, W, 100),  "KOBRA MAX",        F_BIG,   ORANGE)
    text_center(draw, (0, 102, W, 126), "KobraMax-HC32",   F_SMALL, GRAY)
    separator(draw, 128)
    gx2 = W // 2 - 4;  gx3 = W // 2 + 4
    btn(draw, MARGIN, 138, gx2,      200, "PRINT",   style='primary', icon=0xf02f)
    btn(draw, gx3,    138, W-MARGIN, 200, "TOOLS",   style='normal',  icon=0xf0ad)
    btn(draw, MARGIN, 212, gx2,      274, "PREPARE", style='normal',  icon=0xf1de)
    btn(draw, gx3,    212, W-MARGIN, 274, "SYSTEM",  style='normal',  icon=0xf013)
    return img


def page_file_browser():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "FILE BROWSER")
    btn(draw, W - 44, STATUS_Y2 + 4, W - MARGIN, TITLE_Y2 - 4, chr(0xf2f1), style='ghost', fnt=_fa(15))

    ROW_H = 54
    for i in range(5):
        y1 = CONTENT_Y1 + i * ROW_H
        y2 = y1 + ROW_H - 2
        row_bg = BG_SURFACE if i % 2 == 0 else BG_DARK
        draw.rectangle([(0, y1), (W - 1, y2)], fill=row_bg)
        # file icon
        _fa_centered(draw, MARGIN + 11, (y1 + y2) // 2, 0xf15b, _fa(22), DGRAY)
        # filename VP area
        vp_area(draw, MARGIN + 28, y1 + 16, W - MARGIN, y1 + 36, f'filename_{i+1}.gcode')
        separator(draw, y2 + 1)

    page_y = CONTENT_Y1 + 5 * ROW_H + 4
    btn(draw, MARGIN, page_y, W // 2 - 4, page_y + 40, "PREV PAGE", style='ghost', icon=0xf053)
    btn(draw, W // 2 + 4, page_y, W - MARGIN, page_y + 40, "NEXT PAGE", style='ghost', icon=0xf054)

    footer_3btn(draw, ["BACK", "RESUME", "PRINT"],
                ['ghost', 'normal', 'primary'])
    return img


def _page_status(paused):
    img, draw = new_page()
    status_bar(draw)
    if paused:
        title_bar(draw, "PAUSED", color=WARNING)
    else:
        title_bar(draw, "PRINTING", color=SUCCESS)

    y = CONTENT_Y1 + 8

    text_left(draw, MARGIN, y, "FILE", F_TINY, GRAY);  y += 14
    vp_area(draw, MARGIN, y, W - MARGIN, y + 30, 'print_file.gcode');  y += 40

    text_left(draw, MARGIN, y, "PROGRESS", F_TINY, GRAY);  y += 14
    draw.rounded_rectangle([(MARGIN, y), (W - MARGIN - 46, y + 24)],
                            radius=4, fill=BG_ELEVATED)
    if not uf.PROGRESS_BARS:   # otherwise the display's Process Bar control fills this track
        draw.rounded_rectangle([(MARGIN, y), (MARGIN + 120, y + 24)],
                                radius=4, fill=ORANGE)
    vp_area(draw, W - MARGIN - 42, y, W - MARGIN, y + 24, '72%')
    y += 44

    vp_area(draw, MARGIN,   y, 138, y + 28, '1H 24M');
    vp_area(draw, 142, y, W - MARGIN, y + 28, '100%');
    text_left(draw, MARGIN, y - 16, "ELAPSED",    F_TINY, GRAY)
    text_left(draw, 142,    y - 16, "SPEED",      F_TINY, GRAY)
    y += 38

    text_left(draw, MARGIN, y, "M117 / STATUS", F_TINY, GRAY);  y += 14
    vp_area(draw, MARGIN, y, W - MARGIN, y + 30, ' Layer 143 of 210');  y += 40

    btn(draw, MARGIN, y, W - MARGIN, y + 36, "PRINT SETTINGS", style='ghost', icon=0xf013)

    # No BACK button: the firmware ignores it while an SD print runs, and a button that does nothing
    # (and now lights up when pressed) is worse than none.
    if paused:
        footer_2btn(draw, "STOP", "RESUME", l_style='danger', r_style='success')
    else:
        footer_2btn(draw, "STOP", "PAUSE", l_style='danger', r_style='warning')
    return img

page_status_paused   = lambda: _page_status(paused=True)
page_status_printing = lambda: _page_status(paused=False)


def _print_settings_page(light_on=None):
    """Print Settings. light_on None = page 5/125 (no case-light button); False/True = 211/212, which
    differ only in how the title-bar bulb button is drawn (the firmware opens the page matching the
    real light state). Every value has its own - / + buttons; layout rows live in ui_features."""
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PRINT SETTINGS")
    if light_on is not None:
        btn(draw, W - 46, STATUS_Y2 + 5, W - MARGIN, TITLE_Y2 - 5, chr(0xf0eb),
            style='warning' if light_on else 'ghost', fnt=_fa(15))
    for lbl, y, ph, _k_minus, _k_plus in uf.PRINT_SETTINGS_ROWS:
        text_left(draw, MARGIN, y - 16, lbl, F_SMALL, GRAY)
        btn(draw, MARGIN, y, 60, y + 36, chr(0xf068), style='normal', fnt=_FA_BTN)
        vp_area(draw, 68, y, 204, y + 36, ph)
        btn(draw, 212, y, W - MARGIN, y + 36, chr(0xf067), style='normal', fnt=_FA_BTN)
    footer_2btn(draw, "BACK", "SAVE", l_style='ghost', r_style='primary')
    return img


def page_print_adjust():
    return _print_settings_page(None)


def page_input_shaping():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "INPUT SHAPING  M593")
    y = CONTENT_Y1 + 10

    for lbl, ph in [("X FREQUENCY (Hz)", '40.0'), ("Y FREQUENCY (Hz)", '40.0'),
                    ("X DAMPING  zeta",  '0.150'), ("Y DAMPING  zeta",  '0.150')]:
        text_left(draw, MARGIN, y, lbl, F_SMALL, GRAY);  y += 18
        btn(draw, MARGIN, y, 58, y + 34, chr(0xf068), style='normal', fnt=_FA_BTN)
        vp_area(draw, 66, y, W - 66, y + 34, ph)
        btn(draw, W - 58, y, W - MARGIN, y + 34, chr(0xf067), style='normal', fnt=_FA_BTN)
        y += 48

    separator(draw, y + 4)
    text_center(draw, (0, y + 8, W, y + 26), "Tune with M593 after printing", F_TINY, GRAY)

    footer_2btn(draw, "BACK", "SAVE  M500", l_style='ghost', r_style='primary')
    return img


def page_tools():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "TOOLS")
    gx2 = W // 2 - 4;  gx3 = W // 2 + 4
    btn(draw, MARGIN, 106, gx2,       168, "MOVE AXES",    style='normal', icon=0xf0b2)
    btn(draw, gx3,    106, W - MARGIN, 168, "TEMPERATURE", style='normal', icon=0xf2c7)
    btn(draw, MARGIN, 180, gx2,       242, "SPEED / FAN",  style='normal', icon=0xf863)
    btn(draw, gx3,    180, W - MARGIN, 242, "CASE LIGHT",  style='normal', icon=0xf0eb)
    btn(draw, MARGIN, 258, W - MARGIN, 316, "MOTORS OFF",  style='ghost',  icon=0xf011)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_tools_light(light_on=False):
    """207/209 — Tools with case-light indicator."""
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "TOOLS")
    gx2 = W // 2 - 4;  gx3 = W // 2 + 4
    btn(draw, MARGIN, 106, gx2,       168, "MOVE AXES",   style='normal', icon=0xf0b2)
    btn(draw, gx3,    106, W - MARGIN, 168, "TEMPERATURE", style='normal', icon=0xf2c7)
    btn(draw, MARGIN, 180, gx2,       242, "SPEED / FAN", style='normal', icon=0xf863)
    light_sty = 'warning' if light_on else 'ghost'
    light_lbl = "LIGHT  ON" if light_on else "LIGHT  OFF"
    light_ico = 0xf0eb  # lightbulb
    btn(draw, gx3, 180, W - MARGIN, 242, light_lbl, style=light_sty, icon=light_ico)
    btn(draw, MARGIN, 258, W - MARGIN, 316, "MOTORS OFF", style='ghost', icon=0xf011)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_move():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "MOVE AXES")
    y = CONTENT_Y1 + 8

    # Step size
    text_left(draw, MARGIN, y, "STEP SIZE", F_TINY, GRAY)
    y += 14
    # The selected step is shown by an orange copy of its button (a Variable Icon, generate_select_icons.py)
    # laid over this one by the display; the display itself only shows a lit button while a finger is on it.
    for (bx1, by1, bx2, by2), mm in zip(uf.STEP_BUTTONS, uf.STEP_SIZES):
        assert by1 == y, "uf.STEP_BUTTONS must match the Move Axes layout"
        btn(draw, bx1, by1, bx2, by2, f"{mm} mm", style='normal')
    y += 42

    # Axis rows
    for axis, col in [("X", ORANGE), ("Y", TEAL), ("Z", WHITE)]:
        text_left(draw, MARGIN, y + 12, axis, F_LABEL, col)
        btn(draw, 34,  y, 110,        y + 42, axis + "-",  style='normal', icon=0xf068)
        btn(draw, 116, y, 158,        y + 42, chr(0xf015), style='ghost',  fnt=_fa(13))
        btn(draw, 164, y, 240,        y + 42, axis + "+",  style='normal', icon=0xf067)
        y += 54

    btn(draw, MARGIN, y, W - MARGIN, y + 40, "HOME ALL", style='primary', icon=0xf015)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def _temp_speed_page(title, rows, show_cool=False):
    """Shared layout for Temperature and Speed pages."""
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, title)
    y = CONTENT_Y1 + 12

    _ROW_ICONS = {'HOTEND': 0xf06d, 'BED': 0xf236, 'PART FAN': 0xf863, 'PRINT SPEED': 0xf625}
    for (lbl, now_ph, tgt_ph) in rows:
        ico = _ROW_ICONS.get(lbl)
        if ico and _FA_ROW:
            cy = y + 11
            iw = _bbox(draw, chr(ico), _FA_ROW)[0]
            draw.text((MARGIN, cy), chr(ico), font=_FA_ROW, fill=GRAY, anchor='lm')
            draw.text((MARGIN + iw + 5, cy), lbl, font=F_LABEL, fill=WHITE, anchor='lm')
        else:
            draw.text((MARGIN, y + 11), lbl, font=F_LABEL, fill=WHITE, anchor='lm')
        y += 22
        text_left(draw, MARGIN, y, "NOW",    F_TINY, GRAY)
        text_left(draw, 130,    y, "TARGET", F_TINY, GRAY);  y += 14
        vp_area(draw, MARGIN, y, 122, y + 34, now_ph)
        vp_area(draw, 130, y, W - MARGIN, y + 34, tgt_ph)
        y += 44
        btn(draw, MARGIN,            y, MARGIN + 56, y + 34, chr(0xf068), style='normal',  fnt=_FA_BTN)
        btn(draw, W - MARGIN - 56,  y, W - MARGIN,  y + 34, chr(0xf067), style='primary', fnt=_FA_BTN)
        y += 46
        separator(draw, y);  y += 10

    if show_cool:
        footer_3btn(draw, ["BACK", "COOL", "SET"], ['ghost', 'normal', 'primary'])
    else:
        footer_2btn(draw, "BACK", "SET", l_style='ghost', r_style='primary')
    return img

page_temp  = lambda: _temp_speed_page("TEMPERATURE",
    [("HOTEND", "220 C", "220"), ("BED", " 60 C", " 60")], show_cool=True)

page_speed = lambda: _temp_speed_page("SPEED & FAN",
    [("PART FAN", "100%", "100"), ("PRINT SPEED", "100%", "100")])


def page_system(audio_on=True):
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "SYSTEM")
    gx2 = W // 2 - 4;  gx3 = W // 2 + 4
    btn(draw, MARGIN, 106, gx2,       168, "STATISTICS",    style='normal', icon=0xf080)
    s_lbl = "SOUND  ON" if audio_on else "SOUND  OFF"
    s_ico = 0xf028 if audio_on else 0xf6a9
    s_sty = 'teal' if audio_on else 'ghost'
    btn(draw, gx3,    106, W - MARGIN, 168, s_lbl,          style=s_sty,    icon=s_ico)
    btn(draw, MARGIN, 180, gx2,       242, "ABOUT",          style='normal', icon=0xf05a)
    btn(draw, gx3,    180, W - MARGIN, 242, "TERMINAL",      style='normal', icon=0xf120)
    btn(draw, MARGIN, 254, W - MARGIN, 314, "FACTORY RESET", style='danger', icon=0xf1f8)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_factory_reset_confirm():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "FACTORY RESET", color=ERROR)
    text_center(draw, (0, 108, W, 132), "This will restore all settings to defaults",
                F_SMALL, WARNING)
    text_center(draw, (0, 136, W, 156), "and save immediately.  Cannot be undone.",
                F_SMALL, WARNING)
    _warning_tri(draw, W // 2, 172)
    text_center(draw, (0, 234, W, 258), "M502  then  M500", F_LABEL, GRAY)
    text_center(draw, (0, 262, W, 280), ("Re-calibrate after reset: M306 T, G29, M92 E" if uf.HAS_MPC
                 else "Re-calibrate after reset: PID tune, G29, M92 E"),
                F_TINY, DGRAY)
    footer_2btn(draw, "CANCEL", "RESET", l_style='ghost', r_style='danger')
    return img


def page_about():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "ABOUT")
    y = CONTENT_Y1 + 16
    _ABOUT_ICONS = {'MACHINE': 0xf1b2, 'FIRMWARE': 0xf121, 'VOLUME': 0xf545, 'SUPPORT': 0xf1cd}
    _fa11 = _fa(11)
    for lbl, ph in [("MACHINE",  "Kobra Max"),
                    ("FIRMWARE", "KobraMax-HC32"),
                    ("VOLUME",   "400x400x450 mm"),
                    ("SUPPORT",  "anycubic.com")]:
        ico = _ABOUT_ICONS.get(lbl)
        if ico and _fa11:
            iw = _bbox(draw, chr(ico), _fa11)[0]
            draw.text((MARGIN, y + 7), chr(ico), font=_fa11, fill=GRAY, anchor='lm')
            draw.text((MARGIN + iw + 3, y + 7), lbl, font=F_TINY, fill=GRAY, anchor='lm')
        else:
            draw.text((MARGIN, y + 7), lbl, font=F_TINY, fill=GRAY, anchor='lm')
        y += 14
        vp_area(draw, MARGIN, y, W - MARGIN, y + 34, ph);  y += 46
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_prepare():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PREPARE")
    gx2 = W // 2 - 4;  gx3 = W // 2 + 4
    btn(draw, MARGIN, 106, gx2,       168, "LEVELING",        style='normal',  icon=0xf7b9)
    btn(draw, gx3,    106, W - MARGIN, 168, "PREHEAT",        style='normal',  icon=0xf06d)
    btn(draw, MARGIN, 180, gx2,       242, "FILAMENT",        style='normal',  icon=0xf338)
    if uf.HAS_INPUT_SHAPING:
        btn(draw, gx3, 180, W - MARGIN, 242, "SHAPING",   style='teal',   icon=0xf201)
    else:
        # key 5 — the firmware turns both heaters off
        btn(draw, gx3, 180, W - MARGIN, 242, "COOL DOWN", style='teal',   icon=0xf2dc)
    btn(draw, MARGIN, 254, W - MARGIN, 314, "THERMAL TUNING", style='warning', icon=0xf06d)
    tune_txt = "MPC hotend + PID bed autotune" if uf.HAS_MPC else "PID autotune: hotend + bed"
    text_center(draw, (0, 322, W, 338), tune_txt, F_TINY, DGRAY)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_thermal_tune():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "THERMAL TUNING")

    text_center(draw, (0, 100, W, 116), "Not available while printing", F_TINY, WARNING)

    if uf.HAS_MPC:
        hot_lbl, hot_sub = "MPC  AUTOTUNE  HOTEND", "M306 T  |  hotend thermal model  |  ~5 min"
    else:
        hot_lbl = f"PID  TUNE  HOTEND  {uf.PID_HOTEND_TUNE_TEMP}C"
        hot_sub = f"M303 E0 S{uf.PID_HOTEND_TUNE_TEMP} C8  |  hotend PID  |  ~5 min"
    btn(draw, MARGIN, 122, W - MARGIN, 200, hot_lbl,
        style='primary', fnt=F_LABEL, icon=0xf06d)
    text_center(draw, (0, 206, W, 222), hot_sub, F_TINY, GRAY)

    btn(draw, MARGIN, 230, W - MARGIN, 308, f"PID  TUNE  BED  {uf.PID_BED_TUNE_TEMP}C",
        style='teal', fnt=F_LABEL, icon=0xf236)
    text_center(draw, (0, 314, W, 330),
                f"M303 E-1 S{uf.PID_BED_TUNE_TEMP} C8  |  bed PID  |  ~8 min", F_TINY, GRAY)

    separator(draw, 348)
    text_center(draw, (0, 354, W, 370), "Results are saved automatically (M500)", F_TINY, DGRAY)
    text_center(draw, (0, 372, W, 388), "No progress is shown  |  wait for the heater to settle",
                F_TINY, DGRAY)

    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_pre_level():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "LEVELING MENU")
    y = CONTENT_Y1 + 20
    items = [("AUTO BED LEVEL  G29", 'primary', 0xf05b),
             ("MANUAL Z ADJUST",      'normal',  0xf338)]
    if uf.HAS_M1024:   # both buttons open the M1024 page, which needs a firmware command
        items += [("Z OFFSET WIZARD", 'normal', 0xf0d0),
                  ("AUTO Z OFFSET",   'normal', 0xf063)]
    for lbl, sty, ico in items:
        btn(draw, MARGIN, y, W - MARGIN, y + 44, lbl, style=sty, icon=ico);  y += 56
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_level_advance():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "Z OFFSET ADJUST")
    y = CONTENT_Y1 + 24
    text_left(draw, MARGIN, y, "CURRENT OFFSET (mm)", F_SMALL, GRAY);  y += 18
    vp_area(draw, MARGIN, y, W - MARGIN, y + 54, '+0.050');  y += 68
    btn(draw, MARGIN, y,       W // 2 - 4, y + 48, "- 0.01 mm",  style='normal',  icon=0xf068)
    btn(draw, W // 2 + 4, y, W - MARGIN,   y + 48, "+ 0.01 mm",  style='primary', icon=0xf067)
    y += 62
    vp_area(draw, MARGIN, y + 2, W - MARGIN, y + 26, 'Homing...')   # live status line
    text_center(draw, (0, y + 32, W, y + 48), "Nozzle goes to the bed centre at Z0", F_TINY, GRAY)
    text_center(draw, (0, y + 50, W, y + 66), "Adjust until paper just drags, then SAVE", F_TINY, GRAY)
    footer_2btn(draw, "BACK", "SAVE", l_style='ghost', r_style='primary')
    return img


def page_preheat():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PREHEAT")
    y = CONTENT_Y1 + 14
    _PREHEAT_ICONS = {'HOTEND': 0xf06d, 'BED': 0xf236}
    for sensor, now_ph, tgt_ph in [("HOTEND", "210 C", "220"),
                                    ("BED",    " 55 C", " 60")]:
        ico = _PREHEAT_ICONS.get(sensor)
        if ico and _FA_ROW:
            cy = y + 11
            iw = _bbox(draw, chr(ico), _FA_ROW)[0]
            draw.text((MARGIN, cy), chr(ico), font=_FA_ROW, fill=GRAY, anchor='lm')
            draw.text((MARGIN + iw + 5, cy), sensor, font=F_LABEL, fill=WHITE, anchor='lm')
        else:
            draw.text((MARGIN, y + 11), sensor, font=F_LABEL, fill=WHITE, anchor='lm')
        y += 22
        text_left(draw, MARGIN, y, "ACTUAL / TARGET", F_TINY, GRAY);  y += 14
        vp_area(draw, MARGIN, y, W - MARGIN, y + 34, now_ph + ' / ' + tgt_ph);  y += 46
        separator(draw, y);  y += 10

    (l1, h1, b1), (l2, h2, b2) = uf.PREHEAT[1], uf.PREHEAT[2]
    btn(draw, MARGIN, y,       W // 2 - 4, y + 46, f"{l1}  {h1}/{b1} C", style='primary', icon=0xf06d)
    btn(draw, W // 2 + 4, y, W - MARGIN,   y + 46, f"{l2}  {h2}/{b2} C", style='normal',  icon=0xf06d)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_filament():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "FILAMENT")
    y = CONTENT_Y1 + 16
    text_left(draw, MARGIN, y, "HOTEND TEMPERATURE", F_SMALL, GRAY);  y += 16
    vp_area(draw, MARGIN, y, W - MARGIN, y + 34, '210/230 C');  y += 40
    vp_area(draw, MARGIN, y, W - MARGIN, y + 24, 'Heating to 230 C...');  y += 32   # live status line
    btn(draw, MARGIN, y, W - MARGIN, y + 40, "LOAD FILAMENT",   style='primary', icon=0xf063);   y += 48
    btn(draw, MARGIN, y, W - MARGIN, y + 40, "EXTRUDE 10 MM",   style='normal',  icon=0xf078);   y += 48
    btn(draw, MARGIN, y, W - MARGIN, y + 40, "UNLOAD FILAMENT", style='normal',  icon=0xf062);   y += 48
    btn(draw, MARGIN, y, W - MARGIN, y + 40, "STOP",            style='danger',  icon=0xf04d)
    text_center(draw, (0, y + 46, W, y + 62), "Heats to 230 C first. Use EXTRUDE once loaded", F_TINY, GRAY)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_print_settings_light(light_on=False):
    """211/212 - Print settings with the case-light button."""
    return _print_settings_page(light_on)


# ── Simple info / confirm / wait pages ────────────────────────────────────────

def _icon_page(title, icon_fn, lines, btns=None, title_color=None):
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, title, color=title_color or ORANGE)
    icon_fn(draw)
    y = CONTENT_Y1 + 90
    for text, color in lines:
        text_center(draw, (0, y, W, y + 26), text, F_BODY, color);  y += 30
    if btns:
        if len(btns) == 1:
            footer_1btn(draw, btns[0][0], style=btns[0][1])
        elif len(btns) == 2:
            footer_2btn(draw, btns[0][0], btns[1][0],
                        l_style=btns[0][1], r_style=btns[1][1])
    return img


def page_done():
    return _icon_page("DONE",
        lambda d: _check_circle(d, W//2, CONTENT_Y1 + 42),
        [("Operation complete", WHITE)],
        btns=[("OK", 'success')])


def page_abnormal():
    return _icon_page("WARNING", lambda d: _warning_tri(d, W//2, CONTENT_Y1 + 18),
        [("An abnormal condition was detected", GRAY)],
        btns=[("BACK", 'ghost')], title_color=WARNING)


def page_print_finish():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PRINT COMPLETE", color=SUCCESS)
    _check_circle(draw, W//2, CONTENT_Y1 + 44)
    y = CONTENT_Y1 + 80
    text_left(draw, MARGIN, y, "PRINT TIME", F_TINY, GRAY);  y += 14
    vp_area(draw, MARGIN, y, W - MARGIN, y + 36, '1H 24M 36S')
    footer_1btn(draw, "OK  ->  MAIN MENU", style='success')
    return img


def page_wait_stop():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "STOPPING...")
    _badge(draw, 'stop')
    text_center(draw, (0, CONTENT_Y1+156, W, CONTENT_Y1+180), "Please wait...", F_BODY, GRAY)
    wait_status_box(draw, 'Stopping ...')
    return img


def page_filament_lack():
    return _icon_page("FILAMENT RUNOUT",
        lambda d: _warning_tri(d, W//2, CONTENT_Y1 + 18),
        [("Filament sensor triggered", WHITE),
         ("Load filament and resume", GRAY)],
        btns=[("BACK TO PRINT", 'primary')], title_color=WARNING)


def page_forbidden():
    return _icon_page("NOT ALLOWED",
        lambda d: _error_circle(d, W//2, CONTENT_Y1 + 44),
        [("This action is not available right now", GRAY)],
        btns=[("OK", 'ghost')])


def page_stop_confirm():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "STOP PRINT?", color=ERROR)
    _warning_tri(draw, W//2, CONTENT_Y1 + 18, color=ERROR)
    text_center(draw, (0, CONTENT_Y1 + 80, W, CONTENT_Y1 + 108), "This will cancel the print.", F_BODY, WHITE)
    text_center(draw, (0, CONTENT_Y1 + 112, W, CONTENT_Y1 + 136), "Progress will be lost.", F_SMALL, GRAY)
    footer_2btn(draw, "CANCEL", "STOP PRINT", l_style='ghost', r_style='danger')
    return img


def page_no_sd():
    return _icon_page("NO SD CARD",
        lambda d: _error_circle(d, W//2, CONTENT_Y1 + 44),
        [("SD card not found or removed", WHITE),
         ("Insert SD card and try again", GRAY)],
        btns=[("OK", 'ghost')])


def page_filament_heat():
    return _icon_page("HEAT REQUIRED",
        lambda d: _flame(d, W//2 - 16, CONTENT_Y1 + 20, size=32),
        [("Hotend must reach 220 C", WHITE),
         ("Heating to 230 C...", GRAY)],
        btns=[("OK - START HEATING", 'warning')], title_color=WARNING)


def page_wait_pause():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PAUSING...")
    _badge(draw, 'pause')
    text_center(draw, (0, CONTENT_Y1+156, W, CONTENT_Y1+180), "Finishing current move...", F_BODY, GRAY)
    wait_status_box(draw, 'Pausing ...')
    return img


def page_level_ensure():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "CONFIRM LEVELING")
    _warning_tri(draw, W//2, CONTENT_Y1 + 18, color=TEAL)
    text_center(draw, (0, CONTENT_Y1 + 78, W, CONTENT_Y1 + 106), "Place probe on build plate", F_BODY, WHITE)
    text_center(draw, (0, CONTENT_Y1 + 110, W, CONTENT_Y1 + 134), "Ensure bed is clear of objects", F_SMALL, GRAY)
    footer_2btn(draw, "BACK", "START  G29", l_style='ghost', r_style='primary')
    return img


def page_leveling():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "LEVELING IN PROGRESS")
    _badge(draw, 'leveling')
    text_center(draw, (0, CONTENT_Y1+128, W, CONTENT_Y1+152), "Probing mesh points...", F_BODY, GRAY)
    n = int(round(uf.GRID_POINTS ** 0.5))
    text_center(draw, (0, CONTENT_Y1+156, W, CONTENT_Y1+178), f"{n}x{n} = {uf.GRID_POINTS} points", F_SMALL, GRAY)
    if uf.PROGRESS_BARS:
        draw.rounded_rectangle([(MARGIN, 312), (W - MARGIN, 332)], radius=4, fill=BG_ELEVATED)
    wait_status_box(draw, 'Probing point 12 / 49')
    return img


def page_stats():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PRINTER STATISTICS")
    y = CONTENT_Y1 + 8
    _STATS_ICONS = {
        'TOTAL PRINTS': 0xf02f,  'FINISHED': 0xf058,  'FAILED': 0xf057,
        'TOTAL PRINT TIME': 0xf017, 'LONGEST PRINT': 0xf252, 'FILAMENT USED': 0xf338,
    }
    _fa11 = _fa(11)
    for lbl in ["TOTAL PRINTS", "FINISHED", "FAILED",
                "TOTAL PRINT TIME", "LONGEST PRINT", "FILAMENT USED"]:
        ico = _STATS_ICONS.get(lbl)
        if ico and _fa11:
            iw = _bbox(draw, chr(ico), _fa11)[0]
            draw.text((MARGIN, y + 7), chr(ico), font=_fa11, fill=GRAY, anchor='lm')
            draw.text((MARGIN + iw + 3, y + 7), lbl, font=F_TINY, fill=GRAY, anchor='lm')
        else:
            draw.text((MARGIN, y + 7), lbl, font=F_TINY, fill=GRAY, anchor='lm')
        y += 14
        vp_area(draw, MARGIN, y, W - MARGIN, y + 24, '-');  y += 38  # compact rows to fit BACK button
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_auto_offset():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "AUTO Z OFFSET")
    y = CONTENT_Y1 + 18
    btn(draw, MARGIN, y, W - MARGIN, y + 42, "PREPARE  (move to centre)", style='ghost',   icon=0xf05b);  y += 54
    btn(draw, MARGIN, y, W//2-4, y+42, "-1.0 mm", style='normal',  icon=0xf068)
    btn(draw, W//2+4, y, W-MARGIN, y+42, "+1.0 mm", style='primary', icon=0xf067);  y += 54
    btn(draw, MARGIN, y, W//2-4, y+42, "-0.1 mm", style='normal',  icon=0xf068)
    btn(draw, W//2+4, y, W-MARGIN, y+42, "+0.1 mm", style='primary', icon=0xf067);  y += 54
    btn(draw, MARGIN, y, W - MARGIN, y + 42, "FINE  +0.1 mm", style='ghost',   icon=0xf067)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_outage_recovery():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "POWER LOSS FOUND", color=WARNING)
    _warning_tri(draw, W//2, CONTENT_Y1 + 14)
    y = CONTENT_Y1 + 72
    text_left(draw, MARGIN, y, "FILE",     F_TINY, GRAY);  y += 14
    vp_area(draw, MARGIN, y, W - MARGIN, y + 34, 'last_print.gcode');  y += 46
    text_left(draw, MARGIN, y, "PROGRESS", F_TINY, GRAY);  y += 14
    vp_area(draw, MARGIN, y, W - MARGIN, y + 34, '72%');  y += 46
    text_center(draw, (0, y + 4, W, y + 24), "Resume from where you left off?", F_SMALL, GRAY)
    footer_2btn(draw, "CANCEL", "RESUME", l_style='ghost', r_style='primary')
    return img


def page_probe_preheating():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PREPARING TO LEVEL")
    _badge(draw, 'preheat')
    text_center(draw, (0, CONTENT_Y1+148, W, CONTENT_Y1+172), "Heating for leveling...", F_BODY, GRAY)
    text_center(draw, (0, CONTENT_Y1+176, W, CONTENT_Y1+198),
                f"{uf.LEVELING_NOZZLE_TEMP} C  /  {uf.LEVELING_BED_TEMP} C", F_SMALL, ORANGE)
    wait_status_box(draw, 'Hotend 120/190  Bed 40/60')
    return img


def page_homing():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "HOMING")
    _badge(draw, 'homing')
    text_center(draw, (0, CONTENT_Y1+150, W, CONTENT_Y1+174), "Please wait...", F_BODY, GRAY)
    wait_status_box(draw, 'Homing ...  X:0 Y:0 Z:0')
    return img


def _error_page(title, msg, detail='', back=True):
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, title, color=ERROR)
    _error_circle(draw, W//2, CONTENT_Y1 + 44)
    text_center(draw, (0, CONTENT_Y1 + 80, W, CONTENT_Y1 + 108), msg, F_BODY, WHITE)
    if detail:
        text_center(draw, (0, CONTENT_Y1 + 112, W, CONTENT_Y1 + 136), detail, F_SMALL, GRAY)
    if back:
        footer_1btn(draw, "BACK", style='ghost')
    else:
        # fatal fault: Marlin has halted the printer, so no button could do anything
        text_center(draw, (0, FOOTER_Y1 + 14, W, FOOTER_Y2 - 14), "Power-cycle the printer", F_SMALL, WARNING)
    return img


def page_probe_precheck():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "TESTING PROBE")
    _badge(draw, 'probe')
    text_center(draw, (0, CONTENT_Y1+140, W, CONTENT_Y1+164), "Press nozzle onto build plate", F_BODY, GRAY)
    text_center(draw, (0, CONTENT_Y1+168, W, CONTENT_Y1+190), "Waiting for strain gauge trigger", F_SMALL, GRAY)
    footer_1btn(draw, "CANCEL", style='ghost')
    return img


def page_probe_ok():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PROBE OK", color=SUCCESS)
    _check_circle(draw, W//2, CONTENT_Y1 + 44)
    text_center(draw, (0, CONTENT_Y1 + 80, W, CONTENT_Y1 + 108), "Strain gauge triggered!", F_BODY, SUCCESS)
    text_center(draw, (0, CONTENT_Y1 + 112, W, CONTENT_Y1 + 136), "Starting G29 mesh...", F_SMALL, GRAY)
    return img


def page_probe_failed():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PROBE NOT TRIGGERED", color=ERROR)
    _error_circle(draw, W//2, CONTENT_Y1 + 44)
    text_center(draw, (0, CONTENT_Y1 + 80, W, CONTENT_Y1 + 108), "No response from probe", F_BODY, ERROR)
    text_center(draw, (0, CONTENT_Y1 + 112, W, CONTENT_Y1 + 136), "Check wiring and retry", F_SMALL, GRAY)
    footer_1btn(draw, "BACK", style='ghost')
    return img


def page_thumbnail():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "PRINT PREVIEW")

    # Thumbnail VP area (left) — tw=160 leaves 90px right panel for filename
    tw = 160
    draw.rounded_rectangle([(MARGIN, CONTENT_Y1+6), (MARGIN+tw, CONTENT_Y1+202)],
                            radius=4, fill=BG_ELEVATED)
    draw.rounded_rectangle([(MARGIN, CONTENT_Y1+6), (MARGIN+tw, CONTENT_Y1+202)],
                            radius=4, outline=DIVIDER, width=1)

    # File info (right of thumbnail)
    ix = MARGIN + tw + 6  # = 174
    text_left(draw, ix, CONTENT_Y1 + 12, "FILE",   F_TINY, GRAY)
    vp_area(draw, ix, CONTENT_Y1 + 26, W - MARGIN, CONTENT_Y1 + 54, 'file.gcode')
    separator(draw, CONTENT_Y1 + 212)
    # Full-width filename below thumbnail for long names
    vp_area(draw, MARGIN, CONTENT_Y1 + 218, W - MARGIN, CONTENT_Y1 + 248, 'longfilename.gcode')

    footer_2btn(draw, "BACK", "PRINT", l_style='ghost', r_style='primary')
    return img


def page_terminal():
    img, draw = new_page()
    status_bar(draw)
    title_bar(draw, "TERMINAL")
    y = CONTENT_Y1  # = 92

    # Response log — 5 rows, each 38px
    for i, ph in enumerate(['ok', 'echo: N1 G28*18', 'T:220/220 B:60/60', 'ok', 'ok']):
        row_bg = BG_SURFACE if i % 2 == 0 else BG_DARK
        draw.rectangle([(0, y), (W - 1, y + 36)], fill=row_bg)
        text_left(draw, MARGIN, y + 10, ">", F_SMALL, TEAL)
        vp_area(draw, MARGIN + 14, y + 6, W - MARGIN, y + 30, ph)
        y += 38  # y: 92, 130, 168, 206, 244  → ends at 282

    separator(draw, y + 2)
    text_left(draw, MARGIN, y + 6, "SEND COMMAND", F_TINY, GRAY);  y += 24  # y = 282+24 = 306

    # 3 preset buttons: G28  G29  M105
    bw = (W - MARGIN * 2 - 8) // 3  # 82
    _TERM_ICONS = {'G28 HOME': 0xf015, 'G29 LEVEL': 0xf05b, 'M105 TEMPS': 0xf2c7}
    for i, (lbl, sty) in enumerate([("G28 HOME", 'normal'), ("G29 LEVEL", 'normal'), ("M105 TEMPS", 'teal')]):
        x1 = MARGIN + i * (bw + 4)
        x2 = (W - MARGIN) if i == 2 else (x1 + bw)
        btn(draw, x1, y, x2, y + 44, lbl, style=sty, fnt=F_TINY, icon=_TERM_ICONS.get(lbl))
    y += 52  # y = 358

    # 2 preset buttons: M502  M500
    btn(draw, MARGIN,       y, W // 2 - 4, y + 44, "M502 RESET", style='warning', fnt=F_TINY, icon=0xf1f8)
    btn(draw, W // 2 + 4,  y, W - MARGIN,  y + 44, "M500 SAVE",  style='success', fnt=F_TINY, icon=0xf0c7)

    footer_1btn(draw, "BACK", style='ghost')
    return img


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT TABLE
# ─────────────────────────────────────────────────────────────────────────────
#
# Maps filename -> generator function.
# Pages that are identical for CHS and ENG are listed twice.

def _build_page_map():
    m = {}

    m['000'] = page_boot

    # Core pages – CHS (001-034) and ENG mirrors (121-155)
    core = {
        1:  page_main,
        2:  page_file_browser,
        3:  page_status_paused,
        4:  page_status_printing,
        5:  page_print_adjust,
        6:  page_input_shaping,
        7:  page_tools,
        8:  page_move,
        9:  page_temp,
        10: page_speed,
        11: lambda: page_system(audio_on=True),
        13: page_about,
        15: page_prepare,
        16: page_pre_level,
        17: page_level_advance,
        18: page_preheat,
        19: page_filament,
        20: page_done,
        21: page_abnormal,
        22: page_print_finish,
        23: page_wait_stop,
        25: page_filament_lack,
        26: page_forbidden,
        27: page_stop_confirm,
        29: page_no_sd,
        30: page_filament_heat,
        32: page_wait_pause,
        33: page_level_ensure,
        34: page_leveling,
    }
    for n, fn in core.items():
        m[f'{n:03d}'] = fn
        m[f'{n + 120:03d}'] = fn  # ENG mirror

    # Special standalone pages
    m['093'] = page_stats
    m['115'] = page_auto_offset
    m['117'] = lambda: page_system(audio_on=False)   # CHS mute
    m['170'] = lambda: page_system(audio_on=False)   # ENG mute

    m['171'] = page_outage_recovery          # CHS power loss
    m['173'] = page_outage_recovery          # ENG power loss (Anycubic uses 173, not 171+120=291)

    m['175'] = page_probe_preheating         # CHS probe preheat
    m['176'] = page_probe_preheating         # ENG probe preheat

    m['177'] = page_homing   # CHS homing
    m['189'] = page_homing   # ENG homing

    # CHS error/status pages 178-188
    error_pages_chs = {
        178: ("BED HEATER FAULT",        "Bed heater failed",             "Check wiring and thermistor"),
        179: ("BED THERMISTOR FAULT",    "Bed NTC out of range",          "Check thermistor connection"),
        180: ("HOTEND HEATER FAULT",     "Hotend heater failed",          "Check wiring and cartridge"),
        181: ("HOTEND THERMISTOR FAULT", "Hotend NTC out of range",       "Check thermistor connection"),
        182: ("X ENDSTOP FAULT",         "X homing failed",               "Check X endstop wiring"),
        183: ("Y ENDSTOP FAULT",         "Y homing failed",               "Check Y endstop wiring"),
        184: ("Z ENDSTOP FAULT",         "Z homing failed",               "Check Z probe wiring"),
        185: ("ZL ENDSTOP FAULT",        "Z-Left homing failed",          "Check ZL endstop"),
        186: ("ZR ENDSTOP FAULT",        "Z-Right homing failed",         "Check ZR endstop"),
        187: ("LEVELING SENSOR FAULT",   "Probe not triggered during G29","Check strain gauge"),
        188: ("LEVELING FAILED",         "Mesh leveling failed",          "Retry or check probe"),
    }
    for n, (title, msg, detail) in error_pages_chs.items():
        # 187/188 (leveling) are recoverable and handled; the rest are fatal kills
        fn = lambda t=title, m=msg, d=detail, b=(n in (187, 188)): _error_page(t, m, d, b)
        m[f'{n:03d}'] = fn
        m[f'{n + 12:03d}'] = fn  # ENG mirrors are +12 for pages 178-188

    # Probe precheck pages
    m['201'] = page_probe_precheck
    m['202'] = page_probe_ok
    m['203'] = page_probe_failed
    m['204'] = page_probe_precheck   # ENG
    m['205'] = page_probe_ok         # ENG
    m['206'] = page_probe_failed     # ENG

    # Tools + case light
    m['207'] = page_tools_light                                  # light off
    m['209'] = lambda: page_tools_light(light_on=True)           # light on

    # Print settings + case light
    m['211'] = page_print_settings_light                         # light off
    m['212'] = lambda: page_print_settings_light(light_on=True)  # light on

    # Printer stats display
    m['213'] = page_stats

    # NEW pages
    m['214'] = page_thumbnail
    m['215'] = page_terminal
    m['216'] = page_thermal_tune
    m['217'] = page_factory_reset_confirm

    return m


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def generate_pressed(page_map):
    """Write the 'button held' pictures (IDs from press_effect.py).

    While a button is pressed the display copies the button's touch rectangle out of its pressed
    picture. So each pressed picture is the page's own art rendered with every button lit up
    (btn() in _PRESSED mode), cut down to the touch rectangles and black everywhere else — the black
    is never shown, and it keeps each picture small (a few KB instead of ~17)."""
    global _PRESSED
    zones = {}
    for page, x0, y0, x1, y1, key in gc._expand_zones(gc._ZONES):
        if pe.pressed_id(page, key) is not None:
            zones.setdefault(pe.base_page(page), set()).add((x0, y0, x1, y1))

    written = []
    for base in sorted(zones):
        pid = pe.pressed_id(base)
        _PRESSED = True
        try:
            art = page_map[f'{base:03d}']()
        finally:
            _PRESSED = False
        out = Image.new('RGB', (W, H), (0, 0, 0))
        for x0, y0, x1, y1 in zones[base]:
            box = (max(x0, 0), max(y0, 0), min(x1 + 1, W), min(y1 + 1, H))
            out.paste(art.crop(box), box[:2])
        out.save(os.path.join(OUT_DIR, f'{pid:03d}.bmp'))
        written.append(pid)
    print(f"{len(written)} pressed-button pictures generated: {written[0]}..{written[-1]}")
    return written


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    page_map = _build_page_map()

    total = len(page_map)
    ok = 0
    errors = []

    for name in sorted(page_map):
        fn = page_map[name]
        path = os.path.join(OUT_DIR, f'{name}.bmp')
        try:
            img = fn()
            img.save(path)
            print(f"  {name}.bmp")
            ok += 1
        except Exception as e:
            print(f"  ERROR {name}.bmp : {e}")
            errors.append((name, e))

    print(f"\n{ok}/{total} images generated in {OUT_DIR}/")
    if uf.PRESS_EFFECT:
        generate_pressed(page_map)
    if errors:
        print("Errors:")
        for name, e in errors:
            print(f"  {name}: {e}")


if __name__ == '__main__':
    main()
