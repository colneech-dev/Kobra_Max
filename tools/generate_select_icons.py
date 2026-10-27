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
    print(f"{len(uf.STEP_SIZES)} select icons written to {OUT}/")


if __name__ == "__main__":
    main()
