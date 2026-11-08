#!/usr/bin/env python3
"""
Compare the display's compiled picture library (DWIN_SET/16_68_.icl) with the BMPs that
generate_screens.py produces — i.e. tell you whether the art ON THE DISPLAY is current.

The display never reads the BMPs: they are compiled into 16_68_.icl by DWIN's DGUS IDE (a manual
step), so any change to generate_screens.py needs an ICL rebuild before it appears on screen.

ICL format (reverse-engineered from the shipped file, checked on all 145 images):
    "DGUS_3" + 2 bytes, u32 BE total length - 8, u32 flags,
    then a table of u32 BE absolute offsets, one per picture number (0 = no picture), up to the
    first image block. Each image block is:
        u16 width, u16 height, u16 extra, u32 length, then length + extra bytes of JPEG data.
    DWIN's JPEGs are baseline 4:2:0, but their SOS header declares 3 bytes more than the standard
    one and they have no end-of-image marker; both are repaired before decoding.

Usage (from the project root):
    python tools/check_icl.py                  # report pages whose art differs from the BMP
    python tools/check_icl.py --extract DIR    # also write each decoded ICL picture as DIR/NNN.png
    python tools/check_icl.py --icl FILE       # check another library (default DWIN_SET/16_68_.icl)
    python tools/check_icl.py --src DIR        # compare with the BMPs in DIR (default DWIN_SET)
    python tools/check_icl.py --stamp          # after a PASSING check of a library you just built in the DGUS IDE from
                                               # exactly these BMPs: record their hashes next to it (see below)

How "current" is decided. A decoded JPEG never equals its source, so pixels are compared with a tolerance; that
tolerance cannot see a small text change ("0.3 mm" -> "0.5 mm" moves only a handful of pixels past it). Therefore
every library built by tools/build_icl.py gets a sidecar FILE.sources.json with a SHA-256 of each source picture's
pixels, and when a sidecar exists each picture must match it EXACTLY. Without a sidecar (an IDE-built library that was
never stamped) only the tolerant comparison runs, and a warning says so.

Exit code: 0 = ICL matches the BMPs, 1 = it is stale or incomplete.
"""

import hashlib
import io
import json
import re
import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui_features as uf

ImageFile.LOAD_TRUNCATED_IMAGES = True   # tolerate a final partial block

ICL = Path("DWIN_SET/16_68_.icl")
DWIN_SET = Path("DWIN_SET")

SOS = b"\xff\xda"
EOI = b"\xff\xd9"

# A decoded JPEG never matches the source exactly. Count pixels that differ by more than
# PIXEL_TOL on any channel; real art changes (a relabelled button, a removed bar) change
# hundreds of pixels, JPEG ringing around text edges changes only a handful.
PIXEL_TOL = 60
DIFF_PIXELS_MAX = 120


# The u16 at bytes 6-7 of every library written by DWIN's tools is a CRC-16 of everything from byte 8 to the
# end of the file: the classic table-driven "Modbus" routine (init 0xFFFF; auchCRCHi/auchCRCLo; high byte
# first). Found by decompiling DWIN's Excel2ICL.dll (Excel2ICL.Utils.CRC16 / ICL.getICL) and confirmed on
# six files (stock, IDE-built, another project's library, icon libraries; three distinct DWIN-produced libraries).
def _crc_tables():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
        t.append(c)
    return [x & 0xFF for x in t], [x >> 8 for x in t]


_CRC_HI, _CRC_LO = _crc_tables()


def icl_crc(data):
    """The 2 bytes stored at offset 6 of a library file (computed over data[8:])."""
    hi = lo = 0xFF
    for x in data[8:]:
        idx = hi ^ x
        hi = lo ^ _CRC_HI[idx]
        lo = _CRC_LO[idx]
    return bytes([hi, lo])


def _normalise_jpeg(j):
    """Rewrite DWIN's non-standard SOS length and add the missing end-of-image marker."""
    sos = j.find(SOS)
    declared = int.from_bytes(j[sos + 2:sos + 4], "big")
    standard = 2 * j[sos + 4] + 6
    body = j[sos + 4:sos + 2 + standard]
    out = j[:sos + 2] + standard.to_bytes(2, "big") + body + j[sos + 2 + declared:]
    return out if out.endswith(EOI) else out + EOI


def read_icl(path):
    d = path.read_bytes()
    if d[:6] != b"DGUS_3":
        raise SystemExit(f"{path}: not a DGUS_3 picture library")
    # The offset table ends where the first picture starts, i.e. at its smallest non-zero entry. (An icon
    # library's table begins with empty entries, so the very first word cannot be used.)
    words = struct.unpack(f">{(len(d) - 16) // 4}I", d[16:16 + 4 * ((len(d) - 16) // 4)])
    first = next(w for w in words if w)
    n = (first - 16) // 4
    offsets = struct.unpack(f">{n}I", d[16:16 + 4 * n])
    pics = {}
    for idx, off in enumerate(offsets):
        if not off:
            continue
        # header_len (extra) + data_len bytes follow the 10-byte block header: the JPEG header and its entropy data.
        w, h, extra, length = struct.unpack(">HHHI", d[off:off + 10])
        pics[idx] = (w, h, _normalise_jpeg(d[off + 10: off + 10 + length + extra]))
    return pics


SLOT = 256 * 1024     # DWIN T5L flash is divided into fixed 256 KB slots (guide section 2.5)
PICTURE_LIB_SLOTS = (16, 28)                 # 16_68_.icl must end before the icon library in slot 29
PICTURE_LIB_MAX = (PICTURE_LIB_SLOTS[1] - PICTURE_LIB_SLOTS[0] + 1) * SLOT   # 3,407,872 bytes
# Files with a number in front of their name are flashed to that slot. .bin files have FIXED meanings (13 touch, 14 show,
# 22 config): only these may be shipped, and 13/14 must fit their single slot. 22_Config.bin is NOT shipped: slot 22 is inside
# the picture library (16-28), and T5LCFG.CFG does not load it (TL-4).
ALLOWED_BIN = {"13TouchFile.bin": 1, "14ShowFile.bin": 1, "DWINOS.bin": None}   # name -> max slots (None: not slot-addressed)


def flash_spans(files):
    """files: {shipped name: size}. Returns ([(first, last, name)], [problems])."""
    spans, problems = [], []
    for name, size in sorted(files.items()):
        m = re.match(r"(\d+)", name)
        ext = Path(name).suffix.lower()
        if ext == ".bin":
            if name not in ALLOWED_BIN:
                problems.append(f"{name}: not an allowed .bin file ({', '.join(sorted(ALLOWED_BIN))})")
                continue
            if ALLOWED_BIN[name] and size > ALLOWED_BIN[name] * SLOT:
                problems.append(f"{name}: {size:,} bytes does not fit its {ALLOWED_BIN[name]} flash slot (256 KB)")
        if not m or ext not in (".icl", ".dzk", ".hzk", ".bin"):
            continue
        first = int(m.group(1))
        spans.append((first, first + max(1, -(-size // SLOT)) - 1, name))
    for i, (a0, a1, an) in enumerate(spans):
        for b0, b1, bn in spans[i + 1:]:
            if b0 <= a1 and a0 <= b1:
                problems.append(f"{an} (slots {a0}-{a1}) overlaps {bn} (slots {b0}-{b1})")
    return spans, problems


def picture_lib_headroom(size):
    """Bytes left in slots 16-28 for a picture library of `size` bytes (negative: too big)."""
    return PICTURE_LIB_MAX - size


def check_flash_slots(size_override=None):
    """Files named '<ID>_...' start at flash slot <ID> and occupy ceil(size / 256 KB) slots. Two files
    whose slots overlap corrupt each other. The stock background library fits exactly in slots 16-22
    so the icon library can sit at 23; a bigger rebuilt library silently overwrites it (and the font).
    Checks DWIN_SET under the names the files are shipped with (ui_features.FLASH_RENAMES); .base. files are inputs only."""
    files = {}
    for p in sorted(DWIN_SET.iterdir()):
        if not p.is_file() or ".base." in p.name or p.suffix.lower() not in (".icl", ".dzk", ".hzk", ".bin"):
            continue
        files[uf.FLASH_RENAMES.get(p.name, p.name)] = (size_override or {}).get(p.name, p.stat().st_size)
    return flash_spans(files)[1]


# ── source hashes (sidecar next to a library) ─────────────────────────────────────────────────

def image_hash(img):
    """SHA-256 of a picture's RGB pixels and size (independent of the BMP file's header bytes)."""
    img = img.convert("RGB")
    return hashlib.sha256(f"{img.size[0]}x{img.size[1]}:".encode() + img.tobytes()).hexdigest()


def sidecar_path(lib_path):
    return Path(str(lib_path) + ".sources.json")


def write_sidecar(lib_path, images):
    """images: {id: PIL image} exactly as packed into lib_path."""
    data = {"library_sha256": hashlib.sha256(Path(lib_path).read_bytes()).hexdigest(),
            "sources": {str(i): image_hash(im) for i, im in sorted(images.items())}}
    sidecar_path(lib_path).write_text(json.dumps(data, indent=1), encoding="utf-8")


def read_sidecar(lib_path):
    """{id: hash} if a sidecar exists AND belongs to this exact library file, else None (with the reason)."""
    p = sidecar_path(lib_path)
    if not p.exists():
        return None, "no source-hash sidecar"
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("library_sha256") != hashlib.sha256(Path(lib_path).read_bytes()).hexdigest():
        return None, f"{p.name} belongs to another version of the library"
    return {int(k): v for k, v in data["sources"].items()}, None


def picture_differs(shown, want):
    """Tolerant comparison of a decoded picture with its source: None if they match, else the reason."""
    if shown.size != want.size:
        return f"size {shown.size} vs {want.size}"
    diff = ImageChops.difference(shown, want).convert("L").point(lambda v: 255 if v > PIXEL_TOL else 0)
    n = sum(diff.histogram()[1:])
    return f"{n} px differ  bbox={diff.getbbox()}" if n > DIFF_PIXELS_MAX else None


def main():
    extract = None
    if "--extract" in sys.argv:
        extract = Path(sys.argv[sys.argv.index("--extract") + 1])
        extract.mkdir(parents=True, exist_ok=True)

    # --icl FILE checks another library (e.g. the script-built DWIN_SET/auto_icl/16_68_.icl)
    icl_path = Path(sys.argv[sys.argv.index("--icl") + 1]) if "--icl" in sys.argv else ICL
    src_dir = Path(sys.argv[sys.argv.index("--src") + 1]) if "--src" in sys.argv else DWIN_SET
    if not icl_path.exists():
        raise SystemExit(f"{icl_path} not found")
    pics = read_icl(icl_path)
    # Source images that belong in the library (uf.in_library): pages, pressed pictures, boot frames.
    bmps = {int(p.stem): p for p in src_dir.glob("*.bmp")
            if p.stem.isdigit() and uf.in_library(int(p.stem))}
    hashes, no_hashes = read_sidecar(icl_path)

    stale, missing_in_icl, sources = [], [], {}
    for page in sorted(bmps):
        if page not in pics:
            missing_in_icl.append(page)
            continue
        _w, _h, jpeg = pics[page]
        shown = Image.open(io.BytesIO(jpeg)).convert("RGB")
        if extract:
            shown.save(extract / f"{page:03d}.png")
        want = sources[page] = Image.open(bmps[page]).convert("RGB")
        why = picture_differs(shown, want)
        if not why and hashes is not None and hashes.get(page) != image_hash(want):
            why = "source picture changed since the library was built (hash differs from the sidecar)"
        if why:
            stale.append((page, why))

    extra = sorted(set(pics) - set(bmps))
    raw = icl_path.read_bytes()
    crc_problem = None if icl_crc(raw) == raw[6:8] else (
        f"header CRC mismatch: stored {raw[6:8].hex()}, computed {icl_crc(raw).hex()} (file damaged, "
        "or written by a tool that does not set it)")
    overlaps = check_flash_slots({ICL.name: icl_path.stat().st_size} if icl_path != ICL else None)
    print(f"{icl_path}: {len(pics)} pictures, {len(bmps)} BMPs from {src_dir}")
    if icl_path.name.startswith("16_"):
        left = picture_lib_headroom(len(raw))
        print(f"picture library: {len(raw):,} bytes, {left:,} bytes left below {PICTURE_LIB_MAX:,} (slots 16-28)"
              + ("  ** TOO BIG **" if left < 0 else ""))
        if left < 0:
            overlaps.append(f"{icl_path.name} is {-left:,} bytes larger than slots 16-28")
    if hashes is None:
        print(f"WARNING: {no_hashes}: only the tolerant pixel comparison ran, so a small text change "
              "(e.g. '0.3 mm' -> '0.5 mm') would NOT be noticed")
    for line in overlaps:
        print("FLASH OVERLAP:", line)
    if missing_in_icl:
        print(f"NOT IN ICL (needs a rebuild): {missing_in_icl}")
    if extra:
        print(f"In the ICL but not wanted there (boot frames / hidden pages; they take up flash space): {extra}")
    for page, why in stale:
        print(f"STALE page {page:3d}: {why}")
    if crc_problem:
        print("CRC:", crc_problem)
    ok = not stale and not missing_in_icl and not overlaps and not crc_problem
    if ok and "--stamp" in sys.argv:
        write_sidecar(icl_path, sources)
        print(f"wrote {sidecar_path(icl_path)}: from now on any change to these {len(sources)} pictures is reported")
    if ok:
        print("ICL is current")
    else:
        if stale or missing_in_icl:
            print(f"ICL is STALE for {len(stale) + len(missing_in_icl)} page(s) - rebuild it (build_release.py --script-icl, or the DGUS IDE)")
        if overlaps:
            print("The library is too large for its flash slots - leave out hidden pages (and the boot frames "
                  "if BOOT_ANIMATION is off) when rebuilding it.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
