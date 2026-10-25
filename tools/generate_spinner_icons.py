#!/usr/bin/env python3
"""
Generate the spinner icon frames for the "please wait" screens.

Output: DWIN_SET/spinner_icons/NNN.bmp  (NNN = icon ID, 82x82, 24-bit)

Each wait screen has a static ring-and-glyph badge (generate_screens._wait_badge). The display can
animate an icon only by cycling icons of an icon library (DWIN T5L DGUS II guide 7.3), so for every
badge this makes SPINNER_FRAMES frames of the SAME badge with a bright arc travelling round the ring,
plus one resting frame identical to the static badge (the animation's "stopped" icon).

These are the source images for an ICON library, built in the DGUS IDE (icon library, not the
background-picture library) and saved as   29_SPIN.icl   (ID 29 = flash slot 29; see
ui_features.SPINNER_ICON_LIB). Then set SPINNER_ANIMATION = True in tools/ui_features.py and
regenerate 14ShowFile.bin. Icon IDs per badge are in ui_features.WAIT_BADGES.

Run from the project root:   python tools/generate_spinner_icons.py
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_features as uf

OUT = os.path.join("DWIN_SET", "spinner_icons")
S = uf.SPINNER_SIZE
C = S // 2                    # centre of a frame
R = 40                        # ring radius: same as generate_screens._wait_badge
FA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "fa-solid-900.ttf")


def _dim(color, f=0.30):
    """A faint version of the ring colour for the part of the ring the arc is not on."""
    return tuple(int(v * f + c * (1 - f)) for v, c in zip(color, uf.BG_DARK))


def frame(glyph, color, step=None):
    """One frame. step=None -> the resting badge (full ring); else the arc at step/SPINNER_FRAMES."""
    img = Image.new("RGB", (S, S), uf.BG_DARK)
    d = ImageDraw.Draw(img)
    box = [(C - R, C - R), (C + R, C + R)]
    if step is None:
        d.ellipse(box, outline=color, width=3)
    else:
        d.ellipse(box, outline=_dim(color), width=3)
        start = -90 + step * 360 / uf.SPINNER_FRAMES
        d.arc(box, start, start + 110, fill=color, width=5)
    font = ImageFont.truetype(FA, int(R * 0.95))
    d.text((C, C), chr(glyph), font=font, fill=color, anchor="mm")
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for name, b in uf.WAIT_BADGES.items():
        for i in range(uf.SPINNER_FRAMES):
            frame(b["glyph"], b["color"], i).save(os.path.join(OUT, f"{b['first'] + i:03d}.bmp"))
            n += 1
        frame(b["glyph"], b["color"]).save(os.path.join(OUT, f"{b['first'] + uf.SPINNER_FRAMES:03d}.bmp"))
        n += 1
    with open(os.path.join(OUT, "README.txt"), "w", encoding="utf-8") as f:
        f.write(
            f"{n} icon images ({S}x{S}) for the spinner ICON library, {uf.SPINNER_ICON_LIB}_SPIN.icl.\n"
            "Build it in the DGUS IDE as an ICON library (not the background-picture library): import all of\n"
            "these, keeping the numeric file names - the number is the icon ID the display records use.\n"
            f"Save it as {uf.SPINNER_ICON_LIB}_SPIN.icl and flash it with the other display files.\n"
            f"Size must stay under one flash slot if possible (256 KB); it occupies slot {uf.SPINNER_ICON_LIB}.\n")
    print(f"{n} spinner icons written to {OUT}/  (IDs {min(b['first'] for b in uf.WAIT_BADGES.values())}-"
          f"{max(b['first'] for b in uf.WAIT_BADGES.values()) + uf.SPINNER_FRAMES})")


if __name__ == "__main__":
    main()
