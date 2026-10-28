#!/usr/bin/env python3
"""
DWIN display cross-check — KobraMax-HC32

Verifies that the three hand-synchronised display sources agree with each other
and with the firmware, by re-rendering the screens in memory and comparing:

  [1] BMP freshness  — every DWIN_SET/NNN.bmp equals what generate_screens.py
                       would draw now.
  [2] Art vs touch   — every drawn button has a touch zone (IoU >= 0.85), and every
                       touch zone has a drawn button (generate_dwin_controls.py).
  [3] Art vs show    — every drawn VP text box has a record in 14ShowFile.bin at the
                       same place, and every record sits inside a drawn box.
  [4] Touch vs code  — every touch-zone key has a `case` in the page's handler, and
                       the page has a handler that IdleLoop actually dispatches.

Unlike validate_display.py this parses handlers with real brace matching, so a `{`
on the line after the signature does not hide a handler.

Run from the project root:
    python tools/cross_check_display.py [--overlay DIR]

--overlay DIR writes each screen with touch zones (red, key number) and show-file
records (cyan) drawn on top, for eyeballing.

Exit code: 0 = no errors, 1 = errors. Warnings never fail the run.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageChops, ImageDraw  # noqa: E402
import generate_screens as gs                  # noqa: E402
import generate_dwin_controls as gc            # noqa: E402
import ui_features as uf                       # noqa: E402
import press_effect as pe                      # noqa: E402

CPP      = Path("source/Marlin/src/lcd/extui/lib/anycubic_dgus/dgus_tft.cpp")
SHOWFILE = Path("DWIN_SET/14ShowFile.bin")
DWIN_SET = Path("DWIN_SET")

STATUS_VPS = (0x2030, 0x2880)           # status bar, drawn on every content page
BTN_COVER_MIN = 0.85    # fraction of a drawn button that its touch zone must cover
BOX_IOU_MIN = 0.80

errors, warnings = [], []
def err(m):  errors.append(m)
def warn(m): warnings.append(m)


# ── geometry ──────────────────────────────────────────────────────────────────

def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union else 0.0


def coverage(button, zone):
    """Fraction of the button's area that lies inside the zone."""
    ix = max(0, min(button[2], zone[2]) - max(button[0], zone[0]))
    iy = max(0, min(button[3], zone[3]) - max(button[1], zone[1]))
    area = (button[2]-button[0]) * (button[3]-button[1])
    return ix * iy / area if area else 0.0


# ── record the art as it is drawn ─────────────────────────────────────────────

REC = []
_btn, _vp = gs.btn, gs.vp_area

def _rec_btn(draw, x1, y1, x2, y2, label, *a, **k):
    REC.append(('btn', x1, y1, x2, y2, label))
    return _btn(draw, x1, y1, x2, y2, label, *a, **k)

def _rec_vp(draw, x1, y1, x2, y2, placeholder='', *a, **k):
    REC.append(('vp', x1, y1, x2, y2, placeholder))
    return _vp(draw, x1, y1, x2, y2, placeholder, *a, **k)

gs.btn, gs.vp_area = _rec_btn, _rec_vp


# ── load show file and touch zones ────────────────────────────────────────────

SP_BAD = []   # (page, vp): text records whose SP slot (bytes 2-3) is not 0xFFFF


def load_show():
    show = {}
    if not SHOWFILE.exists():
        warn(f"{SHOWFILE} missing — run tools/patch_14showfile.py")
        return show
    d = SHOWFILE.read_bytes()
    for i in range(int.from_bytes(d[8:10], 'big')):
        n   = int.from_bytes(d[16+i*4:18+i*4], 'little')
        off = int.from_bytes(d[18+i*4:20+i*4], 'big')
        recs = []
        for j in range(n):
            r = d[off+j*32: off+j*32+32]
            if len(r) < 32:
                break
            t = int.from_bytes(r[0:2], 'big')
            vp = int.from_bytes(r[6:8], 'big')
            x, y = int.from_bytes(r[8:10], 'big'), int.from_bytes(r[10:12], 'big')
            if t == 0x5A11:   # text: box start at bytes 14..17 (8..11 is the text's own start), absolute x2,y2 at 18..21
                x, y = int.from_bytes(r[14:16], 'big'), int.from_bytes(r[16:18], 'big')
                if int.from_bytes(r[2:4], 'big') != 0xFFFF:
                    SP_BAD.append((i, vp))
                recs.append((vp, x, y, int.from_bytes(r[18:20], 'big'), int.from_bytes(r[20:22], 'big')))
            elif t == 0x5A10:  # integer: only the top-left corner is stored
                recs.append((vp, x, y, None, None))
        show[i] = recs   # table index == DGUS page ID (page 0 is the first entry)
    return show


def load_zones():
    zones = {}
    for p, x0, y0, x1, y1, key in gc._expand_zones(gc._ZONES):
        zones.setdefault(p, []).append((x0, y0, x1, y1, key))
    return zones


# ── firmware handler parsing (brace-matched) ──────────────────────────────────

def strip_if0(text):
    out, skip = [], 0
    for line in text.splitlines():
        s = line.strip()
        if skip == 0:
            if re.match(r'#\s*if\s+0(\s|$)', s):
                skip = 1
            else:
                out.append(line)
        elif s.startswith('#if'):
            skip += 1
        elif s.startswith('#endif'):
            skip -= 1
    return '\n'.join(out)


def parse_handlers(text):
    handlers = {}
    for m in re.finditer(r'void\s+DgusTFT::page(\w+)_handle\s*\([^)]*\)[^{;]*\{', text):
        i, depth = m.end(), 1
        while depth and i < len(text):
            depth += (text[i] == '{') - (text[i] == '}')
            i += 1
        body = text[m.end():i]
        handlers[m.group(1)] = set(int(x) for x in re.findall(r'case\s+(\d+)\s*:', body)) - {0}
    return handlers


def handler_for(page, idle_text):
    """Name of the handler IdleLoop runs for a device page, or None."""
    # Mirrors the explicit branches of DgusTFT::IdleLoop (keep in sync when they change).
    explicit = {115: '115', 117: '117', 170: '170', 171: '171', 173: '173',
                175: '175', 176: '176', 213: '213', 93: '213', 214: '214', 215: '215',
                216: '216', 217: '217', 187: '199_to_200', 188: '199_to_200'}
    if page in explicit:
        return explicit[page]
    if 177 <= page <= 198:
        return '177_to_198' if re.search(r'^\s*page177_to_198_handle\s*\(', idle_text, re.M) else None
    if page in (199, 200): return '199_to_200'
    if page in (201, 204): return '201'
    if page in (202, 205): return '202'
    if page in (203, 206): return '203'
    if page in (207, 209): return '207_209'
    if page in (5, 125, 211, 212): return '211_212'   # page5_handle delegates to the shared Print Settings handler
    if 1 <= page <= 34:    return str(page)
    if 121 <= page <= 154: return str(page - 120)
    return None


def check_press_effect(page_map):
    """[6] every press-effect picture named by a touch record exists and does not collide with a page;
    [7] pages that share a pressed picture really have identical art."""
    tf = Path("DWIN_SET/13TouchFile.bin")
    if not tf.exists():
        warn("13TouchFile.bin missing")
        return
    raw = tf.read_bytes()
    named = {}
    for i in range(0, len(raw) - 1, 32):
        rec = raw[i:i + 32]
        if rec[:2] == b'\xff\xff':
            break
        pic_on = int.from_bytes(rec[12:14], 'big')
        if pic_on != pe.NO_EFFECT:
            named.setdefault(pic_on, set()).add(int.from_bytes(rec[0:2], 'big'))
    page_ids = {int(n) for n in page_map}
    for pid, pages in sorted(named.items()):
        if pid in page_ids:
            err(f"press-effect picture {pid} (used by pages {sorted(pages)}) is also a page")
        if not (DWIN_SET / f"{pid:03d}.bmp").exists():
            err(f"press-effect picture {pid:03d}.bmp (pages {sorted(pages)}) does not exist - run generate_screens.py")
    for page, twin in sorted(pe.TWIN.items()):
        a, b = page_map.get(f"{page:03d}"), page_map.get(f"{twin:03d}")
        if a and b and ImageChops.difference(a(), b()).getbbox():
            err(f"pages {page} and {twin} share a pressed picture but their art differs")


def _eval_addr(expr):
    expr = expr.strip()
    return eval(expr, {"__builtins__": {}}) if re.fullmatch(r'[0-9a-fA-Fx+*() ]+', expr) else None


def check_vp_addresses():
    """[5] Every TXT_*/ADDRESS_* VP defined in both dgus_tft.h and patch_14showfile.py must agree."""
    hdr = Path("source/Marlin/src/lcd/extui/lib/anycubic_dgus/dgus_tft.h").read_text(encoding='utf-8', errors='replace')
    pat = Path("tools/patch_14showfile.py").read_text(encoding='utf-8', errors='replace')
    h = {m.group(1): _eval_addr(m.group(2)) for m in
         re.finditer(r'#define\s+(TXT_\w+)\s+(\(?[0-9a-fA-Fx+*() ]+\)?)\s*(?://.*)?$', hdr, re.M)}
    p = {m.group(1): _eval_addr(m.group(2)) for m in
         re.finditer(r'^(TXT_\w+)\s*=\s*([0-9a-fA-Fx+*() ]+?)\s*(?:#.*)?$', pat, re.M)}
    shared = sorted(set(h) & set(p))
    for name in shared:
        if None not in (h[name], p[name]) and h[name] != p[name]:
            err(f"VP {name}: dgus_tft.h = 0x{h[name]:04X} but patch_14showfile.py = 0x{p[name]:04X}")
    m = re.search(r'#define\s+BOOT_ANIM_LAST_FRAME\s+(\d+)', hdr)
    if uf.BOOT_ANIMATION and (not m or int(m.group(1)) != uf.BOOT_LAST):
        err(f"BOOT_ANIM_LAST_FRAME in dgus_tft.h ({m.group(1) if m else 'missing'}) != ui_features.BOOT_LAST ({uf.BOOT_LAST})")
    for name in ("TXT_WAIT_STATUS", "TXT_STEP_SEL0", "TXT_STEP_SEL1", "TXT_STEP_SEL2"):
        if name not in h:
            err(f"VP {name} is in patch_14showfile.py but missing from dgus_tft.h")


# ── checks ────────────────────────────────────────────────────────────────────

def main():
    # button labels can be Font Awesome private-use glyphs, which a cp1252 console cannot print
    sys.stdout.reconfigure(errors='backslashreplace')
    overlay = None
    if '--overlay' in sys.argv:
        overlay = Path(sys.argv[sys.argv.index('--overlay') + 1])
        overlay.mkdir(parents=True, exist_ok=True)

    show, zones = load_show(), load_zones()
    cpp = strip_if0(CPP.read_text(encoding='utf-8', errors='replace'))
    handlers = parse_handlers(cpp)
    idle = re.search(r'void\s+DgusTFT::IdleLoop\s*\(\s*\)\s*\{', cpp)
    idle_text = cpp[idle.end():idle.end() + 6000] if idle else ''

    page_map = gs._build_page_map()
    for name in sorted(page_map):
        pg = int(name)
        REC.clear()
        img = page_map[name]()
        btns = [r for r in REC if r[0] == 'btn']
        vps  = [r for r in REC if r[0] == 'vp' and r[1] not in (40, 176)]   # skip status bar
        z    = zones.get(pg, [])
        recs = [r for r in show.get(pg, []) if r[0] not in STATUS_VPS]

        # [1] BMP freshness
        bmp = DWIN_SET / f'{name}.bmp'
        if not bmp.exists():
            err(f"p{pg}: {bmp} missing")
        elif uf.BOOT_FIRST <= pg <= uf.BOOT_LAST:
            pass   # boot-animation frame now (the Chinese-language page 93 is not shown by the English firmware)
        elif ImageChops.difference(img, Image.open(bmp).convert('RGB')).getbbox():
            err(f"p{pg}: {bmp.name} is stale vs generate_screens.py")

        if pg in uf.HIDDEN_PAGES:
            # drawn but unreachable: the firmware lacks the feature (see ui_features.py)
            if z:
                err(f"p{pg}: hidden page still has touch zones")
            continue

        # [2] art vs touch zones
        for b in btns:
            best = max(z, key=lambda zz: iou(b[1:5], zz[:4]), default=None)
            s = iou(b[1:5], best[:4]) if best else 0.0
            if s < 0.5:
                err(f'p{pg}: button "{b[5]}" {b[1:5]} has no touch zone')
            elif coverage(b[1:5], best[:4]) < BTN_COVER_MIN:
                # a zone larger than the button is harmless; one that misses part of it is not
                err(f'p{pg}: button "{b[5]}" {b[1:5]} vs zone {best[:4]} (key {best[4]}): '
                    f'zone covers only {coverage(b[1:5], best[:4]):.0%} of the button')
        for zz in z:
            if max((iou(zz[:4], b[1:5]) for b in btns), default=0) < 0.5:
                # file-browser rows are whole-row tap targets, not buttons
                if pg in (2, 122) and zz[4] in (7, 8, 9, 10, 11):
                    continue
                err(f'p{pg}: touch zone key {zz[4]} {zz[:4]} has no drawn button')

        # [3] art vs show file
        for bad_pg, bad_vp in SP_BAD:
            if bad_pg == pg:
                err(f'p{pg}: text record VP 0x{bad_vp:04X} has SP slot != 0xFFFF')
        for vp_, x, y, x2, y2 in recs:
            if x2 is None:
                if not any(v[1] <= x <= v[3] and v[2] <= y <= v[4] for v in vps):
                    err(f'p{pg}: integer record VP 0x{vp_:04X} at ({x},{y}) is outside every drawn box')
            elif max((iou((x, y, x2, y2), v[1:5]) for v in vps), default=0) < BOX_IOU_MIN:
                err(f'p{pg}: text record VP 0x{vp_:04X} {(x, y, x2, y2)} matches no drawn box')
        for v in vps:
            ok = any((r[3] is None and v[1] <= r[1] <= v[3] and v[2] <= r[2] <= v[4]) or
                     (r[3] is not None and iou((r[1], r[2], r[3], r[4]), v[1:5]) >= BOX_IOU_MIN)
                     for r in recs)
            if not ok:
                warn(f'p{pg}: drawn box {v[1:5]} ("{v[5]}") has no show-file record (renders blank)')

        # [4] touch vs firmware
        if z:
            h = handler_for(pg, idle_text)
            keys = {zz[4] for zz in z}
            if h is None:
                err(f'p{pg}: has touch zones {sorted(keys)} but IdleLoop dispatches no handler')
            elif h not in handlers:
                err(f'p{pg}: handler page{h}_handle not found')
            else:
                dead = keys - handlers[h]
                if pg == uf.KEYBOARD_PAGE:   # the character keys (16..) are handled by the handler's default branch
                    dead -= set(range(16, 16 + len(uf.KB_CHARS)))
                if dead:
                    err(f'p{pg}: zone keys {sorted(dead)} have no case in page{h}_handle')

        if overlay:
            ov = img.copy(); d = ImageDraw.Draw(ov)
            for zz in z:
                d.rectangle(zz[:4], outline=(255, 0, 0)); d.text((zz[0]+2, zz[1]+2), str(zz[4]), fill=(255, 255, 0))
            for r in show.get(pg, []):
                d.rectangle((r[1], r[2], r[3] or r[1]+60, r[4] or r[2]+30), outline=(0, 255, 255))
            ov.save(overlay / f'{name}.png')

    check_vp_addresses()
    check_press_effect(page_map)

    print(f"cross_check_display: {len(page_map)} screens, {len(handlers)} handlers parsed")
    for w in warnings:
        print("WARN :", w)
    for e in errors:
        print("ERROR:", e)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
