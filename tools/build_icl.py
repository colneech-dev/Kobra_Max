#!/usr/bin/env python3
"""
EXPERIMENTAL: build a DGUS picture / icon library (.icl) from BMP files without the DGUS IDE.

Why: the display only shows pictures from the compiled library, which until now could only be made by
hand in DWIN's IDE. The container format has been fully reverse-engineered (docs/DISPLAY_NOTES.md 2.3):

    "DGUS_3" + u16 CRC-16 of bytes 8.. + u32 total-8 + 04 <u16 count> 00
    u32 offset table, one entry per ID 0..max (0 = absent)
    per picture:  u16 width, u16 height, u16 header_len (= 626), u32 data_len,
                  JPEG header (identical for every picture of a size), JPEG entropy data
                  (zero padded: data_len is a multiple of 4 and ends with 8-11 zero bytes)

so this script takes the JPEG header and quantisation tables from an IDE-built library (the
TEMPLATE) and fills in new entropy-coded data produced by Pillow with those same tables and the
standard Huffman tables. The result is checked, before it is written, against the template's tables
and afterwards by decoding it with the independent decoder in check_icl.py.

WHAT IS NOT PROVEN: that the display's hardware JPEG decoder accepts it. Treat the output as a test
file: flash it, and if the display shows garbage, power off 15-20 s and reflash the IDE-built library.
The output goes to DWIN_SET/auto_icl/, never over DWIN_SET/16_68_.icl.

Usage (from the project root):
    python tools/build_icl.py                      # background library from DWIN_SET/*.bmp
    python tools/build_icl.py --kind icons --src DWIN_SET/spinner_icons --out DWIN_SET/auto_icl/29_SPIN.icl
    python tools/build_icl.py --selftest           # only run the checks against the template

Options: --template FILE (default DWIN_SET/16_68_.icl)   --src DIR   --out FILE   --quality-check
"""

import io
import struct
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_icl as ci          # noqa: E402  (independent decoder, used to verify the output)
import ui_features as uf        # noqa: E402

TEMPLATE = Path("DWIN_SET/16_68_.icl")
DEFAULT_SRC = Path("DWIN_SET")
DEFAULT_OUT = Path("DWIN_SET/auto_icl/16_68_.icl")
SCREEN = (272, 480)
MAX_LIBRARY_PAGE = 217


# ── JPEG segment helpers ──────────────────────────────────────────────────────────────────────

def segments(jpeg):
    """Yield (marker, payload_start, payload_end) for every segment up to and including SOS.
    payload excludes the 2 length bytes; entropy data starts at the SOS payload end."""
    i = 2                                     # after SOI
    while i < len(jpeg):
        assert jpeg[i] == 0xFF, f"bad marker at {i}"
        marker = jpeg[i + 1]
        length = int.from_bytes(jpeg[i + 2:i + 4], "big")
        yield marker, i + 4, i + 2 + length
        i += 2 + length
        if marker == 0xDA:
            return


def tables(jpeg):
    """{('DQT', id): 64 bytes, ('DHT', class_id): bytes, ...} regardless of segment framing."""
    out = {}
    for marker, a, z in segments(jpeg):
        body = jpeg[a:z]
        if marker == 0xDB:                    # one or more quantisation tables
            while body:
                pq_tq = body[0]
                assert pq_tq >> 4 == 0, "16-bit quantisation tables unsupported"
                out[("DQT", pq_tq & 15)] = body[1:65]
                body = body[65:]
        elif marker == 0xC4:                  # one or more Huffman tables
            while body:
                tc_th = body[0]
                counts = body[1:17]
                n = sum(counts)
                out[("DHT", tc_th)] = body[:17 + n]
                body = body[17 + n:]
    return out


def sof_info(jpeg):
    for marker, a, z in segments(jpeg):
        if marker == 0xC0:
            body = jpeg[a:z]
            return dict(prec=body[0], h=int.from_bytes(body[1:3], "big"), w=int.from_bytes(body[3:5], "big"),
                        comps=body[5:], at=a)
    raise ValueError("no SOF0")


def sos_end(jpeg):
    for marker, a, z in segments(jpeg):
        if marker == 0xDA:
            return z
    raise ValueError("no SOS")


# ── template ──────────────────────────────────────────────────────────────────────────────────

class Template:
    def __init__(self, path):
        d = Path(path).read_bytes()
        if d[:6] != b"DGUS_3":
            raise SystemExit(f"{path}: not a DGUS_3 library")
        # bytes 6-7 are a CRC-16 of d[8:] (check_icl.icl_crc); confirm our routine reproduces the template's
        self.crc_ok = ci.icl_crc(d) == d[6:8]
        first = struct.unpack(">I", d[16:20])[0]
        n = (first - 16) // 4
        offs = [o for o in struct.unpack(f">{n}I", d[16:16 + 4 * n]) if o]
        o = offs[0]
        w, h, hdr_len, _ln = struct.unpack(">HHHI", d[o:o + 10])
        self.hdr_len = hdr_len
        self.header = d[o + 10:o + 10 + hdr_len]          # up to and including the (quirky) SOS segment
        self.tables = tables(self.header + b"\xff\xd9")
        self.sof = sof_info(self.header)
        self.size = (self.sof["w"], self.sof["h"])
        sos = sos_end(self.header)
        assert sos == len(self.header), "template header does not end at SOS"
        # qtables for Pillow, in the order of their ids. A DQT segment stores a table in zigzag order,
        # Pillow's `qtables` argument wants natural (row-major) order — verified by comparing the output.
        self.qtables = [self._natural(self.tables[("DQT", i)])
                        for i in sorted(k[1] for k in self.tables if k[0] == "DQT")]

    ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20,
              13, 6, 7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59,
              52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]

    @classmethod
    def _natural(cls, zigzag_table):
        nat = [0] * 64
        for i, v in enumerate(zigzag_table):
            nat[cls.ZIGZAG[i]] = v
        return nat

    def header_for(self, size):
        """The JPEG header for an image of `size` (only the SOF dimensions change)."""
        w, h = size
        hdr = bytearray(self.header)
        at = self.sof["at"]
        hdr[at + 1:at + 3] = h.to_bytes(2, "big")
        hdr[at + 3:at + 5] = w.to_bytes(2, "big")
        return bytes(hdr)


# ── encoding ──────────────────────────────────────────────────────────────────────────────────

def encode_entropy(img, tpl):
    """Entropy-coded data for `img` using the template's quantisation tables, 4:2:0, standard Huffman."""
    buf = io.BytesIO()
    img.save(buf, "JPEG", qtables=tpl.qtables, subsampling=2, optimize=False, progressive=False)
    jpeg = buf.getvalue()

    # The entropy data is only valid under the template header if every table matches.
    mine = tables(jpeg)
    for key, want in tpl.tables.items():
        if mine.get(key) != want:
            raise SystemExit(f"Pillow's {key} differs from the template's - the entropy data would not match "
                             "the header; refusing to build")
    sof = sof_info(jpeg)
    if sof["comps"] != tpl.sof["comps"]:
        raise SystemExit("Pillow's component/sampling layout differs from the template (need 4:2:0)")

    start = sos_end(jpeg)
    end = len(jpeg)
    assert jpeg[end - 2:end] == b"\xff\xd9", "missing EOI"
    data = jpeg[start:end - 2]
    # IDE output: zero padded so the length is a multiple of 4 and 8-11 zero bytes follow the data
    padded = -(-(len(data) + 8) // 4) * 4
    return data + b"\x00" * (padded - len(data))


def make_block(img, tpl):
    if img.mode != "RGB":
        img = img.convert("RGB")
    entropy = encode_entropy(img, tpl)
    w, h = img.size
    return struct.pack(">HHHI", w, h, tpl.hdr_len, len(entropy)) + tpl.header_for(img.size) + entropy


def build_library(images, tpl, kind="background"):
    """images: {id: PIL image}. kind 'background' -> count field = highest ID (as the IDE wrote it for our
    library); 'icons' -> count field = number of icons (as in the stock icon library)."""
    ids = sorted(images)
    entries = ids[-1] + 1
    pos = 16 + 4 * entries
    offsets = [0] * entries
    blocks = []
    for i in ids:
        blk = make_block(images[i], tpl)
        assert len(blk) % 4 == 0
        offsets[i] = pos
        pos += len(blk)
        blocks.append(blk)
    count = ids[-1] if kind == "background" else len(ids)
    head = b"DGUS_3" + b"\x00\x00" + struct.pack(">I", pos - 8) + bytes([0x04]) + struct.pack(">H", count) + b"\x00"
    data = head + struct.pack(f">{entries}I", *offsets) + b"".join(blocks)
    return data[:6] + ci.icl_crc(data) + data[8:]     # bytes 6-7 = CRC-16 of everything after byte 8


# ── source selection and checks ───────────────────────────────────────────────────────────────

def load_sources(src, kind):
    out = {}
    for p in sorted(Path(src).glob("*.bmp")):
        if not p.stem.isdigit():
            continue
        i = int(p.stem)
        if kind == "background" and (i > MAX_LIBRARY_PAGE or i in uf.HIDDEN_PAGES):
            continue
        out[i] = Image.open(p).convert("RGB")
    return out


def verify(path, images):
    """Decode what was written with check_icl's independent decoder and compare with the sources."""
    pics = ci.read_icl(Path(path))
    problems = []
    if sorted(pics) != sorted(images):
        problems.append(f"picture IDs differ: missing {sorted(set(images) - set(pics))}, extra {sorted(set(pics) - set(images))}")
    worst = 0
    for i, src in images.items():
        if i not in pics:
            continue
        shown = Image.open(io.BytesIO(pics[i][2])).convert("RGB")
        if shown.size != src.size:
            problems.append(f"id {i}: size {shown.size} != {src.size}")
            continue
        from PIL import ImageChops
        diff = ImageChops.difference(shown, src).convert("L").point(lambda v: 255 if v > ci.PIXEL_TOL else 0)
        n = sum(diff.histogram()[1:])
        worst = max(worst, n)
        if n > ci.DIFF_PIXELS_MAX:
            problems.append(f"id {i}: {n} pixels differ from the source")
    data = Path(path).read_bytes()
    first = struct.unpack(">I", data[16:20])[0]
    if first % 4 or len(data) % 4:
        problems.append("file or table is not 4-byte aligned")
    return problems, worst


def selftest(tpl, template_path):
    """Checks that need no source images: the template's own pictures, re-encoded, must behave like the
    IDE's (same tables, similar size), and a library built from them must decode back to them."""
    pics = ci.read_icl(Path(template_path))
    sample = {i: Image.open(io.BytesIO(pics[i][2])).convert("RGB") for i in list(pics)[:12]}
    lib = build_library(sample, tpl)
    tmp = Path("DWIN_SET/auto_icl/_selftest.icl")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(lib)
    problems, worst = verify(tmp, sample)
    # compare compressed size with the IDE's for the same pixels (a mismatch would mean different quantisation)
    raw = Path(template_path).read_bytes()
    first = struct.unpack(">I", raw[16:20])[0]
    offs = struct.unpack(f">{(first - 16) // 4}I", raw[16:first])
    ratios = []
    for i in sample:
        ide_len = struct.unpack(">I", raw[offs[i] + 6:offs[i] + 10])[0]
        mine = len(encode_entropy(sample[i], tpl))
        ratios.append(mine / ide_len)
    print(f"selftest: {len(sample)} pictures re-encoded, worst differing-pixel count {worst}, "
          f"size vs IDE: {min(ratios):.2f}-{max(ratios):.2f}x")
    tmp.unlink()
    return problems


def main():
    argv = sys.argv[1:]

    def opt(name, default):
        return Path(argv[argv.index(name) + 1]) if name in argv else default

    template_path = opt("--template", TEMPLATE)
    kind = argv[argv.index("--kind") + 1] if "--kind" in argv else "background"
    src = opt("--src", DEFAULT_SRC)
    out = opt("--out", DEFAULT_OUT)

    tpl = Template(template_path)
    print(f"template {template_path}: JPEG header {tpl.hdr_len} bytes, {len(tpl.tables)} tables, "
          f"{tpl.size[0]}x{tpl.size[1]}")
    if not tpl.crc_ok:
        sys.exit("the CRC routine does not reproduce the template's stored CRC - refusing to build")
    print("CRC-16 routine reproduces the template's stored header CRC.")
    problems = selftest(tpl, template_path)
    if "--selftest" in argv:
        print("selftest " + ("FAILED: " + "; ".join(problems) if problems else "passed"))
        sys.exit(1 if problems else 0)
    if problems:
        sys.exit("selftest failed: " + "; ".join(problems))

    images = load_sources(src, kind)
    if not images:
        sys.exit(f"no numbered BMPs found in {src}")
    if kind == "background":
        bad = [i for i, im in images.items() if im.size != SCREEN]
        if bad:
            sys.exit(f"pictures with the wrong size (need {SCREEN}): {bad}")
    lib = build_library(images, tpl, kind)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(lib)
    problems, worst = verify(out, images)
    slots = -(-len(lib) // ci.SLOT) if hasattr(ci, "SLOT") else None
    print(f"wrote {out}: {len(images)} pictures, {len(lib):,} bytes ({len(lib) / 262144:.2f} slots), "
          f"worst differing-pixel count {worst}")
    if problems:
        print("VERIFY FAILED:")
        for p in problems:
            print("  ", p)
        sys.exit(1)
    print("verified: every picture decodes back to its source image.")
    print("NOT verified: that the display itself accepts the file (see the docstring).")


if __name__ == "__main__":
    main()
