#!/usr/bin/env python3
"""
Build a clean release folder ready to copy to SD card.

Usage (from project root):
    python tools/build_release.py

Output:
    release/
      DWIN_SET/   <- copy this entire folder to SD root, insert SD into display USB port
        000.bmp … 217.bmp
        13TouchFile.bin
        14ShowFile.bin
        16_68_.icl
        22_Config.bin
      firmware.bin  <- copy to SD root, insert SD into mainboard slot
      README.txt    <- flashing instructions

The script regenerates all assets from source before assembling the folder,
so the release always reflects the current state of the codebase.
"""

import os, sys, shutil, subprocess, datetime, glob

# Verify PIL is available before doing anything else
try:
    from PIL import Image  # noqa: F401
except ImportError:
    print("ERROR: Pillow not found in this Python interpreter.")
    print(f"       Current interpreter: {sys.executable}")
    print()
    print("Run with the interpreter that has Pillow installed, e.g.:")
    print(r'  "C:\Users\Colin\AppData\Local\Programs\Python\Python314\python.exe" tools/build_release.py')
    sys.exit(1)

PYTHON      = sys.executable
NL          = chr(10)   # (kept as chr() so this file has no escape sequences to mangle)
# --out DIR builds into another folder (e.g. a test package) and leaves ./release untouched.
RELEASE_DIR = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "release"
DWIN_OUT    = os.path.join(RELEASE_DIR, "DWIN_SET")
FW_SRC      = os.path.join(".pio", "build", "HC32F460E_kobra_max", "firmware.bin")

# ── Helpers ───────────────────────────────────────────────────────────────────

def step(msg):
    print(f"\n[{msg}]")

def run_tool(script, desc):
    print(f"  running tools/{script} ...", end=" ", flush=True)
    result = subprocess.run(
        [PYTHON, os.path.join("tools", script)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("FAILED")
        print(result.stdout[-800:] if result.stdout else "")
        print(result.stderr[-800:] if result.stderr else "")
        sys.exit(1)
    # Extract last line as summary
    lines = (result.stdout or "").strip().splitlines()
    summary = lines[-1] if lines else "done"
    print(f"ok  ({summary})")

def copy_file(src, dst_dir, required=True):
    dst = os.path.join(dst_dir, os.path.basename(src))
    if os.path.exists(src):
        shutil.copy2(src, dst)
        return True
    if required:
        print(f"  WARNING: {src} not found — skipping")
    return False

def git_info():
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
        return f"{branch}@{sha}"
    except Exception:
        return "unknown"

# ── 1. Build firmware ────────────────────────────────────────────────────────

step("Building firmware (pio run)")
print("  this takes a minute ...", flush=True)
result = subprocess.run(["pio", "run"], capture_output=True, text=True)
if result.returncode != 0:
    print("FAILED")
    # Print last 30 lines of output for diagnosis
    for line in (result.stdout + result.stderr).splitlines()[-30:]:
        print(f"  {line}")
    sys.exit(1)
# Extract RAM/Flash usage line
for line in result.stdout.splitlines():
    if "RAM:" in line or "Flash:" in line or "ram:" in line.lower():
        print(f"  {line.strip()}")
        break
print("  ok")

# ── 2. Regenerate all DWIN assets from source ─────────────────────────────────

step("Regenerating DWIN assets")
run_tool("generate_screens.py",      "BMP page backgrounds (000–217)")
run_tool("generate_dwin_controls.py","13TouchFile.bin (touch zones)")
run_tool("generate_spinner_icons.py","spinner icon frames (for the optional 29_SPIN.icl)")
run_tool("patch_14showfile.py",      "14ShowFile.bin (VP display areas)")

# The three display files above are hand-synchronised; refuse to package them if they disagree
# with each other or with the firmware's key handlers.
run_tool("cross_check_display.py",   "art / touch zones / show-file / handler cross-check")

# The display shows the compiled 16_68_.icl, NOT the BMPs. If it is older than the BMPs, the touch
# zones and text records generated above will not line up with what is on screen.
step("Checking 16_68_.icl against the BMPs")
_icl = subprocess.run([PYTHON, os.path.join("tools", "check_icl.py")], capture_output=True, text=True)
print(_icl.stdout.strip().splitlines()[-1] if _icl.stdout.strip() else "check_icl produced no output")
if _icl.returncode != 0:
    print()
    print("  The picture library is out of date, so this release would show OLD art with NEW touch zones.")
    print("  Rebuild DWIN_SET/16_68_.icl in the DGUS IDE from the current DWIN_SET/*.bmp (see")
    print("  tools/check_icl.py for the list of stale pages), or pass --allow-stale-icl to override.")
    if "--allow-stale-icl" not in sys.argv:
        sys.exit(1)
    print("  --allow-stale-icl given: continuing.")

# ── 2. Create clean release directory ────────────────────────────────────────

step("Assembling release folder")

if os.path.exists(RELEASE_DIR):
    shutil.rmtree(RELEASE_DIR)
os.makedirs(DWIN_OUT)
print(f"  created {RELEASE_DIR}/")

# ── 3. Copy DWIN_SET output files (no .base.* files) ─────────────────────────

# BMP backgrounds. The display NEVER reads these — it only shows pictures compiled into
# 16_68_.icl. They are the input for rebuilding that library in the DGUS IDE, so they go in their
# own folder, not into DWIN_SET (which is what gets copied to the display's SD card).
ART_OUT = os.path.join(RELEASE_DIR, "ICL_SOURCE_BMPS")
os.makedirs(ART_OUT, exist_ok=True)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import ui_features as uf
# Only the pictures that belong in the library: pages 0-217 minus screens hidden by a feature flag.
# That includes the "button held" pictures (IDs 35-83). The abandoned boot-animation frames (218-256)
# are left out ON PURPOSE: they would push the library past its 9 flash slots (16-24).
bmp_files = [p for p in sorted(glob.glob(os.path.join("DWIN_SET", "*.bmp")))
             if int(os.path.splitext(os.path.basename(p))[0]) <= 217
             and int(os.path.splitext(os.path.basename(p))[0]) not in uf.HIDDEN_PAGES]
for src in bmp_files:
    copy_file(src, ART_OUT)
with open(os.path.join(ART_OUT, "README.txt"), "w", encoding="utf-8") as f:
    f.write(
        "Source images for rebuilding DWIN_SET/16_68_.icl in the DGUS IDE (ICL tool).\n"
        "The display never reads these files.\n\n"
        f"{len(bmp_files)} images, named by page number; the picture index must equal the page number.\n"
        "Import ALL of them, in numeric order, and nothing else.\n\n"
        "These include the 'button held' pictures (035-083): pressing a button shows its rectangle from one of them.\n\n"
        "SIZE LIMIT: the library must stay under 2,359,296 bytes (9 flash slots of 256 KB, slots 16-24), because\n"
        "the icon library is shipped as 25_ICO.icl and the font as 26_FontSong14X14.DZK. Do NOT add the old\n"
        "boot-animation frames (218-256) or the hidden pages (6, 115, 126). Expect roughly 2.0 MB.\n"
        "Check the result with:  python tools/check_icl.py\n")
print(f"  copied {len(bmp_files)} BMPs to {ART_OUT} (source images for the DGUS IDE only)")

# Spinner icon frames: source images for the separate ICON library 29_SPIN.icl (built in the DGUS IDE).
if os.path.isdir(os.path.join("DWIN_SET", "spinner_icons")):
    icon_out = os.path.join(RELEASE_DIR, "ICON_LIB_SOURCE")
    os.makedirs(icon_out, exist_ok=True)
    for src in sorted(glob.glob(os.path.join("DWIN_SET", "spinner_icons", "*"))):
        copy_file(src, icon_out)
    print(f"  copied spinner icon sources to {icon_out}")

# Binary config files
for fname in ["13TouchFile.bin", "14ShowFile.bin", "16_68_.icl", "22_Config.bin",
              "T5LCFG.CFG", "DWINOS.bin",
              "0_DWIN_ASC.HZK", "23_ICO.icl", "24_FontSong14X14.DZK"]:
    src = os.path.join("DWIN_SET", fname)
    # The repo only keeps 22_Config.base.bin (the display's config file, byte-identical to the one
    # already running on the printer); ship it under the name the display expects.
    if fname == "22_Config.bin" and not os.path.exists(src):
        src = os.path.join("DWIN_SET", "22_Config.base.bin")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DWIN_OUT, fname))
            print(f"  copied 22_Config.base.bin as {fname}  ({os.path.getsize(src):,} bytes)")
            continue
    ok = copy_file(src, DWIN_OUT)
    if ok:
        shipped = uf.FLASH_RENAMES.get(fname)
        if shipped:   # the display flashes a file to the slot in its name; see ui_features.FLASH_RENAMES
            os.replace(os.path.join(DWIN_OUT, fname), os.path.join(DWIN_OUT, shipped))
            print(f"  renamed {fname} -> {shipped}")
            fname = shipped
        size = os.path.getsize(os.path.join(DWIN_OUT, fname))
        print(f"  copied {fname}  ({size:,} bytes)")

# ── 3b. EXPERIMENTAL: a second, complete display set whose picture library was built by script ──────
# (tools/build_icl.py) instead of in the DGUS IDE. Flash it to test the script-built library; if the
# display shows garbage, power off 15-20 s and reflash the normal set. Not part of the normal output.
if "--script-icl" in sys.argv:
    step("Building the script-made picture library (EXPERIMENTAL)")
    _bi = subprocess.run([PYTHON, os.path.join("tools", "build_icl.py")], capture_output=True, text=True)
    print("  " + NL.join("  " + ln for ln in (_bi.stdout or _bi.stderr).strip().splitlines()[-4:]).lstrip())
    if _bi.returncode == 0:
        exp = os.path.join(RELEASE_DIR, "EXPERIMENTAL_SCRIPT_ICL")
        shutil.copytree(DWIN_OUT, os.path.join(exp, "DWIN_SET"))
        shutil.copy2(os.path.join("DWIN_SET", "auto_icl", "16_68_.icl"), os.path.join(exp, "DWIN_SET", "16_68_.icl"))
        note = [
            "EXPERIMENTAL display set: identical to ../DWIN_SET except 16_68_.icl, which was built by",
            "tools/build_icl.py (no DGUS IDE). It decodes back to every source image with an independent",
            "decoder, but nobody has seen the display accept it yet.",
            "",
            "Test:  flash this DWIN_SET (SD card: FAT32, 4096-byte allocation unit), then walk the screens.",
            "If anything is garbled or blank: power the printer OFF for 15-20 seconds, then flash ../DWIN_SET",
            "(or your IDE-built library) again. Report what you saw so the builder can be corrected.",
        ]
        with open(os.path.join(exp, "README.txt"), "w", encoding="utf-8") as f:
            f.write(NL.join(note) + NL)
        print(f"  wrote {exp}/  (a full display set with the script-built library)")
    else:
        print("  build_icl.py FAILED - no experimental set written")

# ── 4. Copy firmware binary ───────────────────────────────────────────────────

fw_copied = copy_file(FW_SRC, RELEASE_DIR, required=False)
if fw_copied:
    size = os.path.getsize(os.path.join(RELEASE_DIR, "firmware.bin"))
    print(f"  copied firmware.bin  ({size:,} bytes)")
else:
    print(f"  WARNING: firmware.bin not found at {FW_SRC}")
    print(f"           Run 'pio run' first, then re-run this script.")

# ── 5. Write README ───────────────────────────────────────────────────────────

git_ref  = git_info()
build_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

readme = f"""\
KobraMax-HC32 Firmware
Build: {git_ref}
Date:  {build_ts}
=======================================================

SD CARD CONTENTS
----------------
The SD card needs two separate flashing passes:

  1. Display update  (DWIN_SET folder)
  2. Mainboard update (firmware.bin)

They can be done in sequence on the same SD card,
but the display update must be done FIRST.


STEP 0 — Rebuild the picture library (only when the artwork changed)
-------------------------------------------------------------------
The display shows pictures from 16_68_.icl, never from the .bmp files. After any change to the
screens, rebuild it in DWIN's DGUS IDE from the images in ICL_SOURCE_BMPS/ (see the README there):
import all of them in numeric order, save as DWIN_SET/16_68_.icl. Then run
    python tools/check_icl.py
It must say "ICL is current" and report no FLASH OVERLAP.

Optional spinner: build an ICON library from ICON_LIB_SOURCE/ (see the README there), save it as
29_SPIN.icl in DWIN_SET/, set SPINNER_ANIMATION = True in tools/ui_features.py and re-run this script.


STEP 1 — Flash the display
--------------------------
Files: everything in the DWIN_SET/ folder

1. SD card: FAT32 with a 4096-BYTE ALLOCATION UNIT, e.g. (admin command prompt, erases the card):
       format X: /q /fs:fat32 /a:4096
   Cards formatted any other way make the display's blue screen report 0 files and flash NOTHING.
2. Copy the DWIN_SET/ folder to the SD card root.
   SD card should look like:
     SD:/DWIN_SET/13TouchFile.bin
     SD:/DWIN_SET/14ShowFile.bin
     SD:/DWIN_SET/16_68_.icl
     SD:/DWIN_SET/22_Config.bin
     SD:/DWIN_SET/25_ICO.icl            (the stock icon library, moved from slot 23)
     SD:/DWIN_SET/26_FontSong14X14.DZK  (moved from slot 24)
     SD:/DWIN_SET/... (fonts, config)
   (No .bmp files: the display ignores them.) After flashing, the blue screen should list non-zero
   file counts (.CFG 1, .BIN 4, .DZK 1, .HZK 1, .ICL 2 or 3).
3. Power OFF the printer.
4. Insert the SD card into the small USB port on the
   BACK of the display (not the front SD slot).
5. Power ON. The display will show an orange progress
   bar while flashing. Takes about 30 seconds.
6. When complete, power OFF and remove the SD card
   from the display port.


STEP 2 — Flash the mainboard
-----------------------------
File: firmware.bin
{"(firmware.bin was NOT included — run 'pio run' and rebuild)" if not fw_copied else ""}
1. Copy firmware.bin to the SD card root (no folder).
   SD card should look like:
     SD:/firmware.bin
2. Power OFF the printer.
3. Insert the SD card into the FRONT SD card slot.
4. Power ON. The mainboard flashes automatically.
   The display will show the boot screen when done.
5. Remove the SD card.


STEP 3 — First-boot calibration
---------------------------------
After flashing for the first time (or after a factory
reset), run these commands via the terminal screen or
a USB serial connection:

  M502          ; restore factory defaults
  M500          ; save to EEPROM

  M303 E0 S200 C8 U1   ; PID hotend autotune (~5 min)
                ; Menu: Prepare -> Thermal Tuning -> PID Tune Hotend (saves automatically)
  M303 E-1 S60 C8 U1   ; PID bed autotune (~8 min), same menu

  G28           ; home all axes
  G29           ; bilinear bed levelling (7x7 mesh)
  M500          ; save mesh

  ; Verify extruder steps:
  M83           ; relative extrusion
  G1 E100 F100  ; extrude 100mm — measure actual and adjust with M92 E


FACTORY RESET
-------------
Menu: System -> Factory Reset -> Reset
(runs M502 then M500 automatically)
"""

readme_path = os.path.join(RELEASE_DIR, "README.txt")
with open(readme_path, "w", encoding="utf-8") as f:
    f.write(readme)
print(f"  wrote README.txt")

# ── 6. Summary ────────────────────────────────────────────────────────────────

step("Release summary")
total = sum(
    os.path.getsize(os.path.join(dp, fn))
    for dp, _, files in os.walk(RELEASE_DIR)
    for fn in files
)
file_count = sum(len(files) for _, _, files in os.walk(RELEASE_DIR))
print(f"  {file_count} files, {total / 1024 / 1024:.1f} MB total")
print(f"  output: {os.path.abspath(RELEASE_DIR)}/")
if not fw_copied:
    print()
    print("  *** Run 'pio run' then re-run this script to include firmware.bin ***")
print()
print("Done.")
