#!/usr/bin/env python3
"""
Generate the "selected button" icons for the Move Axes step buttons.

Output: DWIN_SET/select_icons/NNN.bmp  (NNN = icon ID 0..2, one per step button, 24-bit)

The display cannot keep a button lit, so each step button has a Variable Icon (record 0x5A00, guide
7.2) laid exactly over it. The icon is the SAME button drawn in the 'primary' (orange) style; the
firmware writes 1 to the icon's VP to show it (the step is selected) and 0 to hide it. These are the
source images for the icon library 34_SEL.icl (built by build_icl.py --kind icons).

Run from the project root:   python tools/generate_select_icons.py
"""

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_screens as gs
import ui_features as uf

OUT = os.path.join("DWIN_SET", "select_icons")


def step_label(mm):
    return f"{mm} mm"


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, (mm, (x1, y1, x2, y2)) in enumerate(zip(uf.STEP_SIZES, uf.STEP_BUTTONS)):
        w, h = x2 - x1 + 1, y2 - y1 + 1
        img = Image.new("RGB", (w, h), gs.BG_DARK)
        gs.btn(ImageDraw.Draw(img), 0, 0, w - 1, h - 1, step_label(mm), style="primary")
        img.save(os.path.join(OUT, f"{i:03d}.bmp"))
    for i, (lbl, _ico) in enumerate(gs.WZ_STEPS):   # the setup wizard's step buttons (icons 3..7), lit orange for the first step not done
        x1, y1, x2, y2 = uf.WZ_BTN(i)
        w, h = x2 - x1 + 1, y2 - y1 + 1
        img = Image.new("RGB", (w, h), gs.BG_DARK)
        gs.btn(ImageDraw.Draw(img), 0, 0, w - 1, h - 1, lbl, style="primary", icon=_ico)
        img.save(os.path.join(OUT, f"{uf.WZ_ICON_FIRST + i:03d}.bmp"))
    for i, ((x1, y1, x2, y2), (lbl, hot, bed)) in enumerate(zip(uf.PREHEAT_BUTTONS, (uf.PREHEAT[1], uf.PREHEAT[2]))):   # the Preheat page's preset buttons (icons 8, 9)
        w, h = x2 - x1 + 1, y2 - y1 + 1
        img = Image.new("RGB", (w, h), gs.BG_DARK)
        gs.btn(ImageDraw.Draw(img), 0, 0, w - 1, h - 1, f"{lbl}  {hot}/{bed} C", style="primary", icon=0xf06d)
        img.save(os.path.join(OUT, f"{uf.PREHEAT_ICON_FIRST + i:03d}.bmp"))
    def lit(i, rect, label, **kw):
        x1, y1, x2, y2 = rect
        w, h = x2 - x1 + 1, y2 - y1 + 1
        img = Image.new("RGB", (w, h), gs.BG_DARK)
        gs.btn(ImageDraw.Draw(img), 0, 0, w - 1, h - 1, label, style="primary", **kw)
        img.save(os.path.join(OUT, f"{i:03d}.bmp"))
    for i, (rect, nm) in enumerate(zip(uf.P5_BTN, gs.P5_NAMES)):                    # 5-point Z corners (icons 10..13)
        lit(uf.P5_ICON_FIRST + i, rect, nm, icon=0xf192)
    for i, (rect, (lbl, ico)) in enumerate(zip(uf.FILAMENT_BUTTONS, gs.FILAMENT_LABELS)):   # Filament actions (14..16)
        lit(uf.FILAMENT_ICON_FIRST + i, rect, lbl, icon=ico)
    lit(uf.KTEST_ICON, uf.KTEST_BUTTON, "STOP  K TEST", icon=0xf04d)                 # K TEST while the pattern prints (17)
    for i, (rect, lbl, ico) in enumerate(zip(uf.TUNE_BUTTONS, gs.tune_labels(), (0xf06d, 0xf236))):   # Thermal Tuning (18..19)
        lit(uf.TUNE_ICON_FIRST + i, rect, lbl, fnt=gs.F_LABEL, icon=ico)
    n = len(os.listdir(OUT))
    print(f"{n} select icons written to {OUT}/")


if __name__ == "__main__":
    main()
