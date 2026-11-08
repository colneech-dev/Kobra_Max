#!/usr/bin/env python3
"""
KobraMax-HC32 boot animation frame generator.

Draws the boot animation frames (272x480) as DWIN_SET/050.bmp .. 114.bmp. They are pictures
BOOT_FIRST..BOOT_LAST of the main picture library (16_68_.icl), played at power-on by the stock
Image Animation record on page 50 (see ui_features.BOOT_ANIMATION).

Reuses the exact colors/fonts/layout helpers from generate_screens.py so the
animation matches the rest of the redesign.

Run from the project root:
    python tools/generate_boot_animation.py

Output: DWIN_SET/050.bmp .. DWIN_SET/114.bmp
"""

import os
import sys
import math

sys.path.insert(0, os.path.dirname(__file__))
from generate_screens import (   # noqa: E402
    W, H, BG_DARK, ORANGE, TEAL, WHITE, GRAY, DIVIDER,
    F_HUGE, F_TITLE, F_SMALL, _fa, _bbox,
)
from PIL import Image, ImageDraw  # noqa: E402
import ui_features as uf  # noqa: E402

# The frames are pictures BOOT_FIRST..BOOT_LAST of the main library, played by the stock Image Animation record
# on page 50 (not touched by patch_14showfile.py; see ui_features.BOOT_*). Frame time is in units of 8 ms.
N_FRAMES = uf.BOOT_LAST - uf.BOOT_FIRST + 1
FPS = 1000.0 / (8 * uf.BOOT_FRAME_TIME)
DURATION_S = N_FRAMES / FPS

TITLE_TEXT = "KOBRA MAX"
SUB_TEXT = "KobraMax-HC32"
VER_TEXT = f"Marlin {uf.MARLIN_VERSION}  HC32F460"   # read from Version.h

# Timeline (in frames)
TITLE_FADE_START, TITLE_FADE_END = 0, 8
SUB_FADE_START, SUB_FADE_END = 6, 14
VER_FADE_START, VER_FADE_END = 10, 16
BAR_FILL_START, BAR_FILL_END = 8, N_FRAMES - 4
SPINNER_FA_CODE = 0xf110  # circle-notch


def _lerp(a, b, t):
    return a + (b - a) * t


def _ease(t):
    # smoothstep, keeps the fade/fill from feeling linear/robotic
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _alpha_text(base, rect, text, fnt, color, alpha, anchor_center=True):
    """Composite text at a given alpha onto base (RGB) image."""
    if alpha <= 0:
        return
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    x1, y1, x2, y2 = rect
    tw, th = _bbox(ld, text, fnt)
    tx = x1 + (x2 - x1 - tw) // 2
    ty = y1 + (y2 - y1 - th) // 2
    ld.text((tx, ty), text, font=fnt, fill=(*color, int(255 * alpha)))
    base.paste(Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB"), (0, 0))


def _gradient_bg():
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)
    for row in range(H):
        v = int(18 + 16 * row / H)
        draw.line([(0, row), (W, row)], fill=(v, int(v * 0.6), int(v * 0.3)))
    return img


def frame(i):
    img = _gradient_bg()
    draw = ImageDraw.Draw(img)

    title_t = _ease((i - TITLE_FADE_START) / max(1, TITLE_FADE_END - TITLE_FADE_START))
    sub_t = _ease((i - SUB_FADE_START) / max(1, SUB_FADE_END - SUB_FADE_START))
    ver_t = _ease((i - VER_FADE_START) / max(1, VER_FADE_END - VER_FADE_START))
    bar_t = _ease((i - BAR_FILL_START) / max(1, BAR_FILL_END - BAR_FILL_START))

    # Flame mark above the title: fades in, with a ring that pulses outwards and fades (a "heartbeat").
    flame_t = _ease(i / 10.0)
    cx, cy = W // 2, 84
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for k in range(2):
        ph = ((i / 12.0) + k * 0.5) % 1.0                 # 0..1 along the pulse
        r = 26 + 26 * ph
        ld.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=(*ORANGE, int(150 * (1 - ph) * flame_t)), width=2)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))
    fa_big = _fa(44)
    if fa_big:
        _alpha_text(img, (cx - 40, cy - 40, cx + 40, cy + 40), chr(0xF06D), fa_big, ORANGE, flame_t)

    _alpha_text(img, (0, 130, W, 196), TITLE_TEXT, F_HUGE, ORANGE, title_t)
    _alpha_text(img, (0, 202, W, 246), SUB_TEXT, F_TITLE, TEAL, sub_t)
    _alpha_text(img, (0, 252, W, 278), VER_TEXT, F_SMALL, GRAY, ver_t)

    draw = ImageDraw.Draw(img)
    # Progress bar track
    draw.rounded_rectangle([(36, 340), (W - 36, 360)], radius=6, outline=DIVIDER, width=1)
    fill_w = int(_lerp(0, (W - 36 - 2) - (38), bar_t))
    if fill_w > 0:
        draw.rounded_rectangle([(38, 342), (38 + fill_w, 358)], radius=4, fill=ORANGE)

    # Rotating spinner next to "Loading..." text
    dots = "." * (1 + i % 3)
    label = "Ready" if i >= N_FRAMES - 3 else f"Loading{dots}"
    lw, lh = _bbox(draw, "Loading...", F_SMALL)  # fixed width against longest variant
    total_w = 24 + 6 + lw
    cx0 = (W - total_w) // 2
    fa = _fa(18)
    if fa:
        spin_img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
        sd = ImageDraw.Draw(spin_img)
        sd.text((12, 12), chr(SPINNER_FA_CODE), font=fa, fill=(*TEAL, 255), anchor="mm")
        angle = -(360 * i / max(1, N_FRAMES - 1)) * 2  # two full spins over the animation
        spin_img = spin_img.rotate(angle, resample=Image.BICUBIC, center=(12, 12))
        img.paste(spin_img, (cx0, 372), spin_img)
    draw.text((cx0 + 24 + 6, 384), label, font=F_SMALL, fill=GRAY, anchor="lm")

    return img


# First picture-library index for the animation frames: the stock record on page 50 plays pictures 50..114
# of 16_68_.icl, so the frames must be exactly those pictures.
BMP_START_INDEX = uf.BOOT_FIRST
DWIN_SET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "DWIN_SET")


def main():
    dwin_set_dir = os.path.abspath(DWIN_SET_DIR)
    os.makedirs(dwin_set_dir, exist_ok=True)

    for i in range(N_FRAMES):
        frame(i).convert("RGB").save(os.path.join(dwin_set_dir, f"{BMP_START_INDEX + i:03d}.bmp"))

    print(f"{N_FRAMES} boot frames written to {dwin_set_dir} "
          f"({BMP_START_INDEX}.bmp .. {BMP_START_INDEX + N_FRAMES - 1}.bmp), "
          f"{FPS:.1f} fps, {DURATION_S:.1f} s")


if __name__ == "__main__":
    main()
