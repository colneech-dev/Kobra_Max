#!/usr/bin/env python3
"""
Build a release folder: the display set and firmware.bin, ready to copy to SD cards.

Usage (any folder; the script works from the repository root):
    python tools/build_release.py --out release_v63 --script-icl     # the normal way: every library built by script
    python tools/build_release.py --out release_v63                  # picture library from the DGUS IDE (DWIN_SET/16_68_.icl)
    python tools/build_release.py --out release_v63_bmps --bmps-only # only the source pictures for a DGUS IDE rebuild
    python tools/build_release.py --package-hashes                   # print the hashes of the installed framework packages

Options:
    --out NAME          REQUIRED. A NEW folder directly in the repository root whose name starts with "release"
                        (git-ignored). An existing folder is never overwritten: delete it yourself first.
    --script-icl        build 16_68_.icl from the BMPs (tools/build_icl.py) instead of using the IDE-built DWIN_SET/16_68_.icl
    --allow-dirty       build even with uncommitted changes (the release then cannot be traced to a commit)
    --allow-stale-icl   IDE path only: package an IDE library that check_icl.py reports as out of date
    --bmps-only         write only ICL_SOURCE_BMPS/ (and the icon sources) for building 16_68_.icl in the DGUS IDE

Output (<out>/):
    DWIN_SET/           copy this folder to the root of a FAT32 card with 4096-byte clusters, card into the display
      13TouchFile.bin 14ShowFile.bin DWINOS.bin T5LCFG.CFG 0_DWIN_ASC.HZK
      16_68_.icl (pictures)  29_ICO.icl (stock icons)  30_FontSong14X14.DZK  33_SPIN.icl (spinner)  34_SEL.icl (highlights)
    firmware.bin        copy to the root of the printer's card (front slot)
    README.txt          flashing instructions;  SETUP.md: first-time setup (docs/SETUP.md);  build.log
    ICL_SOURCE_BMPS/    the pictures 16_68_.icl was built from (for the DGUS IDE; the display never reads them)

How it stays safe:
  * everything is assembled in <out>.tmp and renamed to <out> only after every check passed; on any failure <out>.tmp is deleted,
    so a folder named release* always holds a complete, checked set;
  * missing display base files, fonts or tools stop the build;
  * the About pages carry the release name; they are drawn into the temporary folder, never into DWIN_SET;
  * the framework packages are hash-checked against tools/expected_package_hashes.json (HW-3);
  * firmware.bin: size, contents, initial stack pointer = __StackTop of firmware.elf, every core vector odd and inside the
    application area (HW-I3).

Test hook: KOBRA_RELEASE_FAIL_AT=<stage> makes the build fail on purpose at that stage (firmware, assembled, checked) to prove that no
half-finished release is left behind.
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

try:
    from PIL import Image  # noqa: F401
except ImportError:
    sys.exit(f"ERROR: Pillow is not installed for {sys.executable}. Run:  {sys.executable} -m pip install -r tools/requirements.txt")

import ui_features as uf          # noqa: E402
import check_icl as ci            # noqa: E402

PYTHON = sys.executable
BUILD_ROOT = ".pio_release"       # release builds use their own build folder: an IDE build in .pio cannot collide with them
LOG_DIR = "build_logs"            # every build attempt's log is kept here
ENV_NAME = "HC32F460E_kobra_max"
FW_BIN = os.path.join(BUILD_ROOT, ENV_NAME, "firmware.bin")
FW_ELF = os.path.join(BUILD_ROOT, ENV_NAME, "firmware.elf")
APP_START, APP_END = 0x8000, 0x3C000        # application area: after the bootloader, below the settings sectors
PACKAGES = ("framework-arduino-hc32f46x", "framework-hc32f46x-ddl")
PACKAGE_HASHES = os.path.join("tools", "expected_package_hashes.json")

# Files copied from DWIN_SET into every release (shipped name -> source); all REQUIRED.
FIXED_FILES = {"13TouchFile.bin": "13TouchFile.bin", "14ShowFile.bin": "14ShowFile.bin", "DWINOS.bin": "DWINOS.bin",
               "T5LCFG.CFG": "T5LCFG.CFG", "0_DWIN_ASC.HZK": "0_DWIN_ASC.HZK",
               **{shipped: src for src, shipped in uf.FLASH_RENAMES.items()}}
# Inputs that must exist before anything starts (the generated 13/14 files are made from the .base ones).
REQUIRED_INPUTS = ["DWIN_SET/13TouchFile.base.bin", "DWIN_SET/14ShowFile.base.bin", "DWIN_SET/DWINOS.bin",
                   "DWIN_SET/T5LCFG.CFG", "DWIN_SET/0_DWIN_ASC.HZK", "DWIN_SET/16_68_.icl",
                   *("DWIN_SET/" + s for s in uf.FLASH_RENAMES), "tools/fonts/fa-solid-900.ttf", "docs/SETUP.md"]
ABOUT_PAGES = (13, 133)
SPIN_LIB, SEL_LIB = f"{uf.SPINNER_ICON_LIB}_SPIN.icl", f"{uf.STEP_ICON_LIB}_SEL.icl"


class BuildError(Exception):
    pass


def fail(msg):
    raise BuildError(msg)


def step(msg):
    print(f"\n[{msg}]", flush=True)


def maybe_fail_at(stage):
    if os.environ.get("KOBRA_RELEASE_FAIL_AT") == stage:
        fail(f"KOBRA_RELEASE_FAIL_AT={stage}: failing on purpose (test of the clean-up)")


def run_tool(args, env=None):
    """Run a tool; on failure show ALL its output (not only the last line) and stop."""
    cmd = [PYTHON] + args
    print(f"  running {' '.join(args)} ...", end=" ", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    lines = (r.stdout or "").strip().splitlines()
    if r.returncode != 0:
        print("FAILED")
        print(r.stdout)
        print(r.stderr)
        fail(f"{args[0]} exited with status {r.returncode}")
    print(f"ok  ({lines[-1] if lines else 'done'})")
    return r.stdout


# ── git / packages ────────────────────────────────────────────────────────────────────────────────

def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, text=True).strip()


def git_state():
    """(branch@sha, list of changed tracked files)."""
    try:
        ref = f"{git('rev-parse', '--abbrev-ref', 'HEAD')}@{git('rev-parse', '--short', 'HEAD')}"
        dirty = [l for l in git("status", "--porcelain", "--untracked-files=no").splitlines() if l.strip()]
        return ref, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", ["(git not available)"]


def packages_dir():
    core = os.environ.get("PLATFORMIO_CORE_DIR") or os.path.join(os.path.expanduser("~"), ".platformio")
    return os.path.join(core, "packages")


def package_path(name):
    """The installed package folder. A package that platformio.ini pins by URL (the DDL 2.2.3 zip) is installed by PlatformIO as '<name>@src-<hash>'
    beside the registry copy: that one is what the build uses, so check it when it exists."""
    base = packages_dir()
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            if d.startswith(name + "@src-") and os.path.isdir(os.path.join(base, d)):
                return os.path.join(base, d)
    return os.path.join(base, name)


def package_hash(path):
    """SHA-256 over every file's relative path and contents (PlatformIO's .piopm, __pycache__ and *.pyc excluded)."""
    h = hashlib.sha256()
    files = []
    for dp, dns, fns in os.walk(path):
        dns[:] = sorted(d for d in dns if d not in ("__pycache__", ".git"))
        for fn in fns:
            if fn == ".piopm" or fn.endswith(".pyc"):
                continue
            files.append(os.path.relpath(os.path.join(dp, fn), path).replace(os.sep, "/"))
    for rel in sorted(files):
        with open(os.path.join(path, rel), "rb") as f:
            h.update(rel.encode() + b"\0" + hashlib.sha256(f.read()).digest())
    return h.hexdigest(), len(files)


def package_version(path):
    try:
        with open(os.path.join(path, ".piopm"), encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError):
        return None


def check_packages():
    """HW-3: the build must use pristine framework packages (a locally modified init.cpp shipped a diagnostic beep in v62)."""
    with open(PACKAGE_HASHES, encoding="utf-8") as f:
        expected = json.load(f)
    for name in PACKAGES:
        path = package_path(name)
        want = expected.get(name) or {}
        if not os.path.isdir(path):
            print(f"  {name}: not installed yet (pio run installs it); checked after the build")
            continue
        got, n = package_hash(path)
        ver = package_version(path)
        if want.get("version") and ver != want["version"]:
            fail(f"{name}: installed version {ver}, expected {want['version']} ({PACKAGE_HASHES})")
        if not want.get("sha256"):
            print(f"  WARNING: {name} {ver}: no known-good hash in {PACKAGE_HASHES} - NOT verified (installed: {got}, {n} files)")
        elif got != want["sha256"]:
            fail(f"{name} {ver} differs from the known-good copy (hash {got}, expected {want['sha256']}). The package was modified "
                 f"locally: delete {path} and let 'pio run' reinstall it")
        else:
            print(f"  {name} {ver}: matches the known-good hash")


# ── firmware ──────────────────────────────────────────────────────────────────────────────────────

def toolchain(tool):
    exe = shutil.which("arm-none-eabi-" + tool)
    if exe:
        return exe
    p = os.path.join(packages_dir(), "toolchain-gccarmnoneeabi", "bin", "arm-none-eabi-" + tool)
    return p + ".exe" if os.path.exists(p + ".exe") else p


def stack_top(elf):
    out = subprocess.check_output([toolchain("nm"), elf], text=True)
    m = re.search(r"^([0-9a-fA-F]+)\s+\S\s+__StackTop$", out, re.M)
    if not m:
        raise ValueError("__StackTop not found in firmware.elf")
    return int(m.group(1), 16)


def check_firmware_bin(path, elf=FW_ELF):
    """None if the file looks like a real HC32 application image, else the reason it does not.
    (release_v47 once shipped a firmware.bin that was all zeros except its last 250 bytes: the printer did not boot.)"""
    try:
        b = open(path, "rb").read()
    except OSError as e:
        return f"cannot read {path}: {e}"
    if not 0x1000 <= len(b) <= 0x34000:
        return f"size {len(b)} bytes is outside 4 KB .. 208 KB"
    vectors = struct.unpack("<16I", b[:64])
    sp = vectors[0]
    if not 0x1FFF8000 <= sp <= 0x20030000:
        return f"initial stack pointer 0x{sp:08X} is not in RAM"
    try:
        top = stack_top(elf)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        return f"cannot read __StackTop from {elf}: {e}"
    if sp != top:
        return f"initial stack pointer 0x{sp:08X} != __StackTop 0x{top:08X} of firmware.elf"
    # Cortex-M4 core vectors 1..15 (reset, NMI, HardFault, ..., SysTick): every one that is set must be a Thumb address in the image
    for i, v in enumerate(vectors[1:], 1):
        if v and (not v & 1 or not APP_START <= (v & ~1) < APP_END):
            return f"core vector {i} = 0x{v:08X} is not an odd address inside 0x{APP_START:X}-0x{APP_END:X}"
    if not vectors[1]:
        return "reset vector is 0"
    nonzero = len(b) - b.count(0)
    if nonzero < len(b) // 4:
        return f"only {nonzero} of {len(b)} bytes are not zero"
    return None


def regenerate_bin_from_elf():
    """Same step the platform runs (objcopy -O binary), repeated on the finished firmware.elf."""
    subprocess.run([toolchain("objcopy"), "-O", "binary", FW_ELF, FW_BIN], check=True)


def build_firmware(tag):
    step("Building firmware (pio run)")
    maybe_fail_at("firmware")
    print("  this takes several minutes ...", flush=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    env = dict(os.environ, PLATFORMIO_BUILD_DIR=os.path.abspath(BUILD_ROOT))
    for attempt in (1, 2, 3):      # the first attempt often fails with a SCons FortranCommon error
        r = subprocess.run(["pio", "run"], capture_output=True, text=True, env=env)
        log = os.path.join(LOG_DIR, f"{tag}_attempt{attempt}.log")
        with open(log, "w", encoding="utf-8", errors="replace") as f:
            f.write(r.stdout + "\n" + r.stderr)
        if r.returncode == 0:
            print(f"  build ok on attempt {attempt} (log: {log})")
            break
        print(f"  attempt {attempt} failed (log: {log})", flush=True)
    else:
        for line in (r.stdout + r.stderr).splitlines()[-30:]:
            print(f"  {line}")
        fail("pio run failed three times")
    for line in r.stdout.splitlines():
        if "RAM:" in line or "Flash:" in line:
            print(f"  {line.strip()}")
    bad = check_firmware_bin(FW_BIN)
    if bad:
        print(f"  WARNING: firmware.bin is not usable ({bad}); rebuilding it from firmware.elf")
        try:
            regenerate_bin_from_elf()
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"  objcopy failed: {e}")
        bad = check_firmware_bin(FW_BIN)
        if bad:
            fail(f"firmware.bin is still not usable: {bad}")
    print("  firmware.bin checked: size, contents, stack pointer = __StackTop, core vectors")
    return log


# ── display ───────────────────────────────────────────────────────────────────────────────────────

def regenerate_display():
    step("Regenerating the display files from source")
    run_tool(["tools/generate_screens.py"])
    run_tool(["tools/generate_dwin_controls.py"])
    run_tool(["tools/generate_spinner_icons.py"])
    run_tool(["tools/generate_select_icons.py"])
    if uf.BOOT_ANIMATION:
        run_tool(["tools/generate_boot_animation.py"])
    run_tool(["tools/patch_14showfile.py"])
    # art / touch zones / show file / firmware handlers must agree
    run_tool(["tools/cross_check_display.py"])


def library_sources(work, tag):
    """A copy of the picture-library sources with the About pages drawn for this release (DWIN_SET is not touched)."""
    src = os.path.join(work, "src")
    os.makedirs(src)
    n = 0
    for p in sorted(glob.glob(os.path.join("DWIN_SET", "*.bmp"))):
        stem = os.path.splitext(os.path.basename(p))[0]
        if stem.isdigit() and uf.in_library(int(stem)):
            shutil.copy2(p, src)
            n += 1
    run_tool(["tools/generate_screens.py", "--only", ",".join(str(p) for p in ABOUT_PAGES), "--out", src],
             env=dict(os.environ, DISPLAY_SET_TAG=tag))
    return src, n


def build_libraries(work, src, script_icl):
    """Returns ({shipped name: path} of the libraries for this release, whether 16_68_.icl is known to be out of date)."""
    libs, stale = {}, False
    jobs = [(SPIN_LIB, ["--kind", "icons", "--src", os.path.join("DWIN_SET", "spinner_icons")]),
            (SEL_LIB, ["--kind", "icons", "--src", os.path.join("DWIN_SET", "select_icons")])]
    if script_icl:
        jobs.insert(0, ("16_68_.icl", ["--src", src]))
    for name, extra in jobs:
        out = os.path.join(work, name)
        run_tool(["tools/build_icl.py"] + extra + ["--out", out])
        libs[name] = out
    if not script_icl:
        # The IDE-built library must show the current art (the tolerant check: an IDE library has no source hashes unless stamped)
        r = subprocess.run([PYTHON, "tools/check_icl.py"], capture_output=True, text=True)
        print("  check_icl: " + (r.stdout.strip().splitlines() or ["(no output)"])[-1])
        if r.returncode != 0:
            print(r.stdout[-3000:])
            if "--allow-stale-icl" not in sys.argv:
                fail("DWIN_SET/16_68_.icl is out of date: rebuild it (use --script-icl, or the DGUS IDE with --bmps-only sources)")
            print("  --allow-stale-icl given: continuing with an OUT OF DATE picture library")
            stale = True
        libs["16_68_.icl"] = os.path.join("DWIN_SET", "16_68_.icl")
    return libs, stale


def check_assembled(tmp, work, src, script_icl):
    step("Checking the assembled package")
    ds = os.path.join(tmp, "DWIN_SET")
    spans, problems = ci.flash_spans({f: os.path.getsize(os.path.join(ds, f)) for f in os.listdir(ds)})
    for p in problems:
        print(f"  FLASH: {p}")
    if problems:
        fail("flash slot problems")
    print("  flash slots: " + ", ".join(f"{n} {a}-{b}" for a, b, n in spans))
    size = os.path.getsize(os.path.join(ds, "16_68_.icl"))
    print(f"  picture library: {size:,} bytes, {ci.picture_lib_headroom(size):,} bytes left below {ci.PICTURE_LIB_MAX:,}")
    if script_icl:
        # the shipped libraries decode to EXACTLY the sources they were built from (sidecar hashes, see check_icl.py)
        run_tool(["tools/check_icl.py", "--icl", os.path.join(work, "16_68_.icl"), "--src", src])
    for name in ("16_68_.icl", SPIN_LIB, SEL_LIB):
        shipped = os.path.join(ds, name)
        built = os.path.join(work, name)
        if os.path.exists(built) and open(shipped, "rb").read() != open(built, "rb").read():
            fail(f"DWIN_SET/{name} differs from the library that was checked")
    run_tool(["tools/cross_check_display.py", "--release", tmp])
    maybe_fail_at("checked")


# ── README ────────────────────────────────────────────────────────────────────────────────────────

def readme_text(tag, git_ref, dirty, script_icl, stale):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    warn = ""
    if dirty:
        warn += ("\n!!! BUILT FROM A WORKING TREE WITH UNCOMMITTED CHANGES (--allow-dirty): this package cannot be traced to a commit.\n")
    if stale:
        warn += ("\n!!! THE PICTURE LIBRARY (16_68_.icl) IS OUT OF DATE (--allow-stale-icl): the display will show OLD pictures under NEW\n"
                 "!!! touch zones. Do not use this package on a printer.\n")
    lib_note = ("All libraries in DWIN_SET were built by script (tools/build_icl.py), not by the DGUS IDE." if script_icl else
                "16_68_.icl was built in the DGUS IDE; the icon libraries 33_SPIN.icl / 34_SEL.icl by script.")
    return f"""\
KobraMax-HC32 firmware and display set
Release:  {tag}          (the About page shows "display set: {tag}")
Build:    {git_ref}{'-dirty' if dirty else ''}          (the About page's BUILD box shows the same commit)
Date:     {ts}
{warn}
FLASH THE DISPLAY FILES AND firmware.bin OF THE *SAME* RELEASE. The firmware sends key codes that the display files
define: a mixed set mis-routes buttons (the wizard keys were renumbered in release_v49 and v54). After flashing, open
System > ABOUT and check both: "display set: {tag}" and the build id.

YOU NEED TWO SD CARDS
---------------------
  * The PRINTER'S OWN card (front slot of the printer) for firmware.bin. Do not format it.
  * A SEPARATE card for the display, formatted FAT32 with 4096-byte clusters (formatting erases it).

If anything goes wrong (blank, frozen or garbled display): power the printer OFF, wait 15-20 seconds (a quick off/on does
not reset the display), then flash the last set that worked.


STEP 1 - Flash the display (DWIN_SET)
-------------------------------------
1. Format the display card: FAT32, allocation unit 4096 bytes. Windows, administrator command prompt (ERASES the card):
       format X: /q /fs:fat32 /a:4096
   With any other cluster size the display's blue screen reports 0 files and flashes nothing.
2. Copy the DWIN_SET folder of this package to the card root, nothing else:
       DWIN_SET/13TouchFile.bin  14ShowFile.bin  DWINOS.bin  T5LCFG.CFG  0_DWIN_ASC.HZK
       DWIN_SET/16_68_.icl  29_ICO.icl  30_FontSong14X14.DZK  33_SPIN.icl  34_SEL.icl
   {lib_note}
   (Do not copy the repository's own DWIN_SET folder: it keeps the stock file names and the source pictures.)
3. Power the printer OFF and wait 15-20 seconds.
4. Put the card into the card slot on the BACK of the display (not the printer's front slot). Power ON.
5. A blue screen lists the files it flashed and ends with "END !". Expect non-zero counts:
       .CFG 1   .BIN 3   .DZK 1   .HZK 1   .ICL 4
6. Power OFF, wait 15-20 seconds, remove the card.


STEP 2 - Flash the mainboard (firmware.bin)
-------------------------------------------
1. Copy firmware.bin to the root of the printer's own card (no folder). Do not format the card.
2. Power OFF the printer and wait 15-20 seconds.
3. Card into the printer's FRONT slot, power ON. The bootloader flashes firmware.bin; the display then shows the boot
   animation and the main page.
4. Once the new firmware has started it RENAMES firmware.bin on the card to firmware.cur, so the next power-up does not
   flash it again. To flash the same file again, copy firmware.bin onto the card again (or rename firmware.cur back to
   firmware.bin).
5. Check System > ABOUT (see the top of this file).


WHERE THE SETTINGS LIVE
-----------------------
Bed mesh, Z offset, PID values, E-steps, K and the setup-wizard progress are stored in the printer's own chip flash (since
release_v52), not on the SD card. Flashing firmware does not erase them. The first time a firmware with flash settings
starts on a printer that has none in flash yet, it takes over eeprom.dat from the SD card ONCE; after that eeprom.dat is not
used. If the settings layout changes between releases the firmware restores defaults (redo the setup wizard).


STEP 3 - First-time setup
-------------------------
Follow SETUP.md (in this package). In short: System > SETUP WIZARD, five steps in this order:
   1 PROBE CHECK        five probe touches, checks the probe repeats
   2 BED MESH           heats, 10 min heat soak, then probes 9 x 9 points: allow 45-60 minutes in total
   3 Z OFFSET           paper test at the bed centre
   4 5-POINT Z          paper test at the four corner squares (REAR LEFT, REAR RIGHT, FRONT LEFT, FRONT RIGHT)
   5 FIRST LAYER TEST   prints five squares to check the first layer
Before a Z-offset, 5-point or first-layer step the printer probes the bed and refuses to go on if the bed is more than
0.5 mm away from where the mesh says it is (glass added or removed, bed moved): make a new mesh then.
Also once: Prepare > THERMAL TUNING (PID hotend and bed, saved automatically), Prepare > E-STEPS, and
Prepare > ADVANCE K > K TEST (prints a Linear Advance pattern; enter the K of the best line, SAVE).

FACTORY RESET: System > FACTORY RESET (M502 + M500): all settings back to defaults, the mesh is gone.
"""


def bmps_only_readme(n):
    return f"""\
Source pictures for building DWIN_SET/16_68_.icl in DWIN's DGUS IDE (ICL tool). The display never reads these files.

{n} pictures, named by picture number; the picture number in the library must equal the file number. Import ALL of them,
in numeric order, and nothing else. They include the "button held" pictures and the boot animation frames (050-114); the
About pages 013 / 133 carry this folder's release name.

SIZE LIMIT: the library must stay below {ci.PICTURE_LIB_MAX:,} bytes (slots 16-28): the icon library is shipped in slot 29.
Save it as DWIN_SET/16_68_.icl, then check it and record its source hashes:
    python tools/check_icl.py --src <this folder> --stamp
The icon libraries 33_SPIN.icl / 34_SEL.icl cannot be made in the IDE; build_release.py always builds them by script.
Simpler: python tools/build_release.py --out release_vNN --script-icl builds every library without the IDE.
"""


# ── main ──────────────────────────────────────────────────────────────────────────────────────────

def parse_out(name):
    """--out must name a NEW folder directly in the repository root whose name starts with 'release' (TL-7)."""
    out = os.path.abspath(name)
    base = os.path.basename(out)
    if os.path.dirname(out) != ROOT or not base.lower().startswith("release") or base.lower().endswith(".tmp"):
        sys.exit(f"--out {name}: must be a folder directly in the repository root whose name starts with 'release' "
                 "(e.g. --out release_v63)")
    if os.path.exists(out):
        sys.exit(f"--out {name}: {out} already exists. Releases are never overwritten (the last known-good set may be in it): "
                 "delete it yourself or choose another name")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    ap.add_argument("--script-icl", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--allow-stale-icl", action="store_true")
    ap.add_argument("--bmps-only", action="store_true")
    ap.add_argument("--package-hashes", action="store_true")
    a = ap.parse_args()

    if a.package_hashes:
        for name in PACKAGES:
            path = package_path(name)
            if os.path.isdir(path):
                h, n = package_hash(path)
                print(f"{name} {package_version(path)}: {h}  ({n} files, {path})")
            else:
                print(f"{name}: not installed ({path})")
        return
    if not a.out:
        ap.error("--out is required (a new folder in the repository root whose name starts with 'release')")
    out = parse_out(a.out)
    tag = os.path.basename(out)
    tmp = out + ".tmp"

    step("Preflight")
    missing = [p for p in REQUIRED_INPUTS if not os.path.exists(p)]
    if missing:
        sys.exit("FAILED: required files are missing: " + ", ".join(missing))
    git_ref, dirty = git_state()
    print(f"  {git_ref}, release name {tag}")
    if dirty and not a.allow_dirty:
        sys.exit("FAILED: uncommitted changes (a release must be traceable to a commit). Commit them, or pass --allow-dirty:\n  "
                 + "\n  ".join(dirty[:20]))
    try:
        check_packages()
    except BuildError as e:
        sys.exit(f"FAILED: {e}")

    if os.path.exists(tmp):
        shutil.rmtree(tmp)       # left over from a crashed run: it is ours (named <out>.tmp)
    ok = False
    try:
        if a.bmps_only:
            build_bmps_only(tmp, tag)
        else:
            build_release(a, tmp, tag, git_ref, dirty)
        os.rename(tmp, out)
        ok = True
    except BuildError as e:
        print(f"\nFAILED: {e}")
    finally:
        if not ok and os.path.exists(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"  removed the unfinished {tmp}")
    if not ok:
        sys.exit(1)
    step("Done")
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(out) for f in fs)
    print(f"  {out}: {sum(len(fs) for _, _, fs in os.walk(out))} files, {total / 1048576:.1f} MB")


def build_bmps_only(tmp, tag):
    regenerate_display()
    os.makedirs(tmp)
    src, n = library_sources(tmp, tag)
    os.rename(src, os.path.join(tmp, "ICL_SOURCE_BMPS"))
    with open(os.path.join(tmp, "ICL_SOURCE_BMPS", "README.txt"), "w", encoding="utf-8") as f:
        f.write(bmps_only_readme(n))


def build_release(a, tmp, tag, git_ref, dirty):
    log = build_firmware(tag)
    check_packages()             # now that pio run has surely installed them
    regenerate_display()
    _ref, dirty_after = git_state()
    if dirty_after and not dirty:
        fail("the generators changed tracked files (the committed display files were not up to date): "
             + ", ".join(l[3:] for l in dirty_after[:10]) + ". Commit the regenerated files first")

    step("Assembling " + tmp)
    os.makedirs(os.path.join(tmp, "DWIN_SET"))
    work = os.path.join(tmp, "_work")
    os.makedirs(work)
    src, n = library_sources(work, tag)
    libs, stale = build_libraries(work, src, a.script_icl)
    ds = os.path.join(tmp, "DWIN_SET")
    for shipped, source in FIXED_FILES.items():
        shutil.copy2(os.path.join("DWIN_SET", source), os.path.join(ds, shipped))
    for shipped, path in libs.items():
        shutil.copy2(path, os.path.join(ds, shipped))
    for f in sorted(os.listdir(ds)):
        print(f"  DWIN_SET/{f:24s} {os.path.getsize(os.path.join(ds, f)):>10,} bytes")
    shutil.copytree(src, os.path.join(tmp, "ICL_SOURCE_BMPS"))
    with open(os.path.join(tmp, "ICL_SOURCE_BMPS", "README.txt"), "w", encoding="utf-8") as f:
        f.write(bmps_only_readme(n))
    shutil.copy2(FW_BIN, os.path.join(tmp, "firmware.bin"))
    bad = check_firmware_bin(os.path.join(tmp, "firmware.bin"))
    if bad or open(os.path.join(tmp, "firmware.bin"), "rb").read() != open(FW_BIN, "rb").read():
        fail(f"the packaged firmware.bin is not usable: {bad or 'the copy differs from the build'}")
    shutil.copyfile(log, os.path.join(tmp, "build.log"))
    shutil.copyfile(os.path.join("docs", "SETUP.md"), os.path.join(tmp, "SETUP.md"))
    with open(os.path.join(tmp, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme_text(tag, git_ref, bool(dirty), a.script_icl, stale))
    maybe_fail_at("assembled")

    check_assembled(tmp, work, src, a.script_icl)
    shutil.rmtree(work)


if __name__ == "__main__":
    main()
