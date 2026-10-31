"""Extra display checks the cross-check tool does not do. Run from the project root."""
import os, re, sys, filecmp
from pathlib import Path
sys.path.insert(0, 'tools')
os.environ.setdefault('DISPLAY_SET_TAG', 'release_v46')
import ui_features as uf
import generate_dwin_controls as gc
import press_effect as pe

REL = Path('release_v46/DWIN_SET')
DS = Path('DWIN_SET')
CPP = Path('source/Marlin/src/lcd/extui/lib/anycubic_dgus/dgus_tft.cpp').read_text(encoding='latin-1')
HDR = Path('source/Marlin/src/lcd/extui/lib/anycubic_dgus/dgus_tft.h').read_text(encoding='latin-1')
probs = []
def P(sev, m): probs.append((sev, m)); print(f'{sev}: {m}')

# --- X1 release package vs repo -------------------------------------------------------------------------------
for f in sorted(os.listdir(REL)):
    if f.lower().endswith('.icl'):
        continue   # script-built in the release (checked with check_icl.py --icl)
    if not (DS / f).exists():
        P('INFO', f'release file {f} not in repo DWIN_SET')
    elif not filecmp.cmp(REL / f, DS / f, shallow=False):
        P('ERROR', f'release {f} differs from repo DWIN_SET/{f}')
src = Path('release_v46/ICL_SOURCE_BMPS')
diff_bmp = [f for f in os.listdir(src) if (DS / f).exists() and not filecmp.cmp(src / f, DS / f, shallow=False)]
if diff_bmp: P('ERROR', f'release ICL source BMPs differ from repo: {diff_bmp[:10]}')
extra = [f for f in os.listdir(src) if not (DS / f).exists()]
if extra: P('INFO', f'ICL source BMPs not in repo DWIN_SET: {extra[:10]}')

# --- X2 13TouchFile.bin vs generator ----------------------------------------------------------------------------
raw = (DS / '13TouchFile.bin').read_bytes()
binz = set()
for i in range(0, len(raw) - 31, 32):
    r = raw[i:i+32]
    if r[:2] == b'\xff\xff': break
    pg = int.from_bytes(r[0:2], 'big')
    x0, y0, x1, y1 = (int.from_bytes(r[k:k+2], 'big') for k in (2, 4, 6, 8))
    binz.add((pg, x0, y0, x1, y1))
genz = {(p, x0, y0, x1, y1) for p, x0, y0, x1, y1, key in gc._expand_zones(gc._ZONES)}
if binz != genz:
    P('ERROR', f'13TouchFile.bin zones != generator: only in bin {sorted(binz - genz)[:6]}, only in generator {sorted(genz - binz)[:6]}')
else:
    print(f'OK  13TouchFile.bin = generator ({len(binz)} zones)')
# key codes inside the bin: find the 2-byte key by matching generator order is format dependent; compare per page counts
from collections import Counter
cb, cg = Counter(z[0] for z in binz), Counter(z[0] for z in genz)

# --- helpers: page names --------------------------------------------------------------------------------------
PAGE = {m.group(1): int(m.group(2)) for m in re.finditer(r'#define\s+(PAGE_\w+)\s+\((\d+)\+PAGE_OFFSET\)', HDR)}
def body_of(sig):
    m = re.search(sig, CPP)
    if not m: return ''
    i, d = m.end(), 1
    while d and i < len(CPP):
        d += (CPP[i] == '{') - (CPP[i] == '}'); i += 1
    return CPP[m.end():i]

# --- X3 IdleLoop dispatch (real) --------------------------------------------------------------------------------
idle = body_of(r'void\s+DgusTFT::IdleLoop\s*\(\s*\)\s*\{')
pairs = re.findall(r'if\s*\(([^{}]*?page_index_now[^{}]*?)\)\s*\{\s*(page\w+_handle)\s*\(', idle, re.S)
disp = {}
for cond, h in pairs:
    nums = set(int(n) for n in re.findall(r'page_index_now\s*==\s*(\d+)', cond))
    nums |= {PAGE[n] for n in re.findall(r'page_index_now\s*==\s*(PAGE_\w+)', cond) if n in PAGE}
    for lo, hi in re.findall(r'page_index_now\s*>=\s*(\d+)\s*&&\s*page_index_now\s*<=\s*(\d+)', cond):
        nums |= set(range(int(lo), int(hi) + 1))
    for n in nums: disp.setdefault(n, h)
print(f'IdleLoop: {len(pairs)} dispatch branches parsed, {len(disp)} pages')
zone_pages = sorted({z[0] for z in genz})
for p in zone_pages:
    if p in disp: continue
    # pages 1..34 / 121..154 may be dispatched through a generic (page_index_now - 120) table
    P('CHECK', f'page {p} has touch zones; no explicit IdleLoop branch found (may be a generic dispatch)')

# --- X3b key cases from the top-level switch(key_value) only ----------------------------------------------------
def top_cases(h):
    b = body_of(r'void\s+DgusTFT::' + h + r'\s*\([^)]*\)\s*\{')
    out = set()
    for m in re.finditer(r'switch\s*\(\s*key_value\s*\)\s*\{', b):
        i, d, start = m.end(), 1, m.end()
        seg = []
        while d and i < len(b):
            c = b[i]
            if c == '{': d += 1
            elif c == '}': d -= 1
            seg.append(c if d == 1 else (' ' if c not in '\n' else c)); i += 1
        out |= set(int(x) for x in re.findall(r'case\s+(\d+)\s*:', ''.join(seg)))
        # "case 3: case 4:" ranges written as "case 3 ... 6:"
        for lo, hi in re.findall(r'case\s+(\d+)\s*\.\.\.\s*(\d+)\s*:', ''.join(seg)):
            out |= set(range(int(lo), int(hi) + 1))
    return out, bool(re.search(r'switch\s*\(\s*key_value\s*\)', b)), b
zone_keys = {}
for p, x0, y0, x1, y1, key in gc._expand_zones(gc._ZONES): zone_keys.setdefault(p, set()).add(key)
for p in zone_pages:
    h = disp.get(p)
    if not h: continue
    cs, has_sw, b = top_cases(h)
    if not has_sw:
        # handlers that test key_value with if/else
        cs = set(int(x) for x in re.findall(r'key_value\s*==\s*(\d+)', b))
    missing = zone_keys[p] - cs
    if p == uf.KEYBOARD_PAGE: missing -= set(range(uf.KB_KEY_BASE, uf.KB_KEY_BASE + len(uf.KB_CHARS)))
    if missing: P('ERROR', f'page {p}: zone keys {sorted(missing)} have no top-level case in {h}')

# --- X4 navigation targets have a picture -----------------------------------------------------------------------
single = {PAGE[n] for n in re.findall(r'page_index\s*==\s*(PAGE_\w+)', body_of(r'uint32_t\s+DgusTFT::TranslatePage\s*\([^)]*\)\s*\{')) if n in PAGE}
pics = {int(f[:3]) for f in os.listdir(src) if re.fullmatch(r'\d{3}\.bmp', f)}
targets = set()
for fn, arg in re.findall(r'(ChangePageOfTFT(?:_DevicePage)?)\s*\(\s*(PAGE_\w+|\d+)\s*\)', CPP):
    v = PAGE.get(arg) if arg.startswith('PAGE_') else int(arg)
    if v is None: P('CHECK', f'{fn}({arg}): unknown name'); continue
    dev = v if fn.endswith('DevicePage') or v in single or v >= 160 else v + 120   # ENG firmware: +120 unless single
    targets.add((arg, v, dev))
for arg, v, dev in sorted(targets, key=lambda t: t[2]):
    if dev not in pics: P('ERROR', f'navigates to {arg} -> device page {dev}: no picture in the release library')
    if dev in uf.HIDDEN_PAGES: P('ERROR', f'navigates to {arg} -> hidden page {dev}')
print(f'navigation: {len(targets)} literal targets checked')

# --- X5 / X6 show-file text records: VP overlap and capacity ----------------------------------------------------
d = (DS / '14ShowFile.bin').read_bytes()
recs = []
for pg in range(int.from_bytes(d[8:10], 'big')):
    n = int.from_bytes(d[16+pg*4:18+pg*4], 'little'); off = int.from_bytes(d[18+pg*4:20+pg*4], 'big')
    for j in range(n):
        r = d[off+j*32: off+j*32+32]
        if len(r) < 32: break
        t = int.from_bytes(r[0:2], 'big'); vp = int.from_bytes(r[6:8], 'big')
        if t == 0x5A11:
            x, x2 = int.from_bytes(r[14:16], 'big'), int.from_bytes(r[18:20], 'big')
            ln = int.from_bytes(r[22:24], 'big'); cw = r[26] // 2
            recs.append((pg, vp, ln, (x2 - x - 4) // max(cw, 1), 'T'))
        elif t == 0x5A10:
            recs.append((pg, vp, 2, 99, 'I'))
spans = {}
for pg, vp, ln, cap, k in recs:
    end = vp + (ln + 1) // 2
    old = spans.get(vp)
    spans[vp] = max(old or vp, end)
starts = sorted(spans)
for a, b in zip(starts, starts[1:]):
    if spans[a] > b:
        P('ERROR', f'VP 0x{a:04X} text runs to 0x{spans[a]:04X}, over VP 0x{b:04X}')
print(f'show file: {len(recs)} records, {len(starts)} distinct VPs checked for overlap')

# capacity of the fields the new code writes (longest string each can receive)
want = {'TXT_WZ_STATUS0': 25, 'TXT_ES_STATUS': 27, 'TXT_LA_STATUS': 25, 'TXT_MESH_INFO1': 27, 'TXT_MESH_INFO2': 27,
        'TXT_ES_CUR': 8, 'TXT_ES_NEW': 8, 'TXT_ES_ACTUAL': 6, 'TXT_LA_K': 6, 'TXT_MESH_BASE': 4}
vpname = {}
for m in re.finditer(r'#define\s+(TXT_\w+)\s+(0x[0-9A-Fa-f]+)', HDR): vpname[int(m.group(2), 16)] = m.group(1)
for pg, vp, ln, cap, k in recs:
    nm = vpname.get(vp)
    base = nm if nm in want else None
    if nm is None and 0x3120 <= vp <= 0x3150: base = 'TXT_WZ_STATUS0'
    if nm is None and 0x2E00 <= vp < 0x2F90 and (vp - 0x2E00) % 8 == 0: base = 'TXT_MESH_BASE'
    if base:
        need = want[base]
        if ln < need + 1 or cap < need:
            P('WARN', f'p{pg} {base} VP 0x{vp:04X}: Text_Length {ln}, fits {cap} chars, longest string {need}')
print('done:', Counter(s for s, _ in probs))
