#!/usr/bin/env python3
"""
Write the pictures used by docs/MANUAL.md and README.md: docs/images/screens/NNN-name.png, made from the display pictures in DWIN_SET
(the same art that is flashed to the display). Run it after any change to the screens, then commit docs/images:

    python tools/export_manual_images.py

The "-lit" pictures show a page with one button lit by its Variable Icon (DWIN_SET/select_icons), the way the display shows it.
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_features as uf

OUT = os.path.join("docs", "images", "screens")
PAGES = {
    6: "keyboard", 119: "five-point-z", 121: "main", 122: "file-browser", 123: "paused", 124: "printing", 128: "move", 129: "temperature",
    130: "speed-fan", 131: "system", 133: "about", 135: "prepare", 136: "leveling-menu", 137: "z-offset", 138: "preheat", 139: "filament",
    141: "halted", 142: "print-finished", 143: "stopping", 145: "filament-lack", 146: "forbidden", 147: "stop-confirm", 149: "no-sd",
    152: "pausing", 153: "mesh-confirm", 154: "leveling-wait", 170: "system-sound-off", 172: "setup-wizard", 173: "power-loss",
    174: "linear-advance-k", 176: "probe-preheat", 189: "homing", 192: "fault-example-hotend-heater", 199: "leveling-error",
    200: "leveling-failed", 204: "probe-test", 205: "probe-ok", 206: "probe-failed", 207: "tools", 208: "bed-mesh-view",
    209: "tools-light-on", 210: "e-steps", 211: "print-settings", 212: "print-settings-light-on", 213: "statistics", 215: "terminal",
    216: "thermal-tuning", 217: "factory-reset",
}
# page, name, [(icon id, x, y)] : the base page with these lit copies pasted over it
LIT = [
    (138, "preheat-pla-lit", [(uf.PREHEAT_ICON_FIRST, uf.PREHEAT_BUTTONS[0])]),
    (119, "five-point-z-lit", [(uf.P5_ICON_FIRST + 2, uf.P5_BTN[2])]),
    (139, "filament-load-lit", [(uf.FILAMENT_ICON_FIRST, uf.FILAMENT_BUTTONS[0])]),
    (174, "linear-advance-k-lit", [(uf.KTEST_ICON, uf.KTEST_BUTTON)]),
    (216, "thermal-tuning-lit", [(uf.TUNE_ICON_FIRST, uf.TUNE_BUTTONS[0])]),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    for n, name in PAGES.items():
        Image.open(os.path.join("DWIN_SET", f"{n:03d}.bmp")).convert("RGB").save(os.path.join(OUT, f"{n:03d}-{name}.png"), optimize=True)
    for n, name, icons in LIT:
        img = Image.open(os.path.join("DWIN_SET", f"{n:03d}.bmp")).convert("RGB")
        for icon, (x1, y1, _x2, _y2) in icons:
            img.paste(Image.open(os.path.join("DWIN_SET", "select_icons", f"{icon:03d}.bmp")).convert("RGB"), (x1, y1))
        img.save(os.path.join(OUT, f"{n:03d}-{name}.png"), optimize=True)
    print(f"{len(os.listdir(OUT))} pictures written to {OUT}/")


if __name__ == "__main__":
    main()
