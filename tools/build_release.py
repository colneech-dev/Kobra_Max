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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import ui_features as uf
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
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            stderr=subprocess.DEVNULL, text=True).strip()
        return f"{branch}@{sha}" + ("-dirty (uncommitted changes)" if dirty else "")
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
run_tool("generate_spinner_icons.py","spinner icon frames (33_SPIN.icl)")
run_tool("generate_select_icons.py", "selected-button icons (34_SEL.icl)")
if uf.BOOT_ANIMATION:
    run_tool("generate_boot_animation.py", "boot animation frames (pictures %d-%d)" % (uf.BOOT_FIRST, uf.BOOT_LAST))
run_tool("patch_14showfile.py",      "14ShowFile.bin (VP display areas)")

# The three display files above are hand-synchronised; refuse to package them if they disagree
# with each other or with the firmware's key handlers.
run_tool("cross_check_display.py",   "art / touch zones / show-file / handler cross-check")

# The display shows the compiled 16_68_.icl, NOT the BMPs. If it is older than the BMPs, the touch
# zones and text records generated above will not line up with what is on screen.
SCRIPT_ICL = "--script-icl" in sys.argv   # libraries are built by script (tools/build_icl.py) below
ICL_STALE = False
if not SCRIPT_ICL:
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
        ICL_STALE = True


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
# Only the pictures that belong in the library: pages 0-217 minus screens hidden by a feature flag.
# That includes the "button held" pictures (35-49 and 218-252) and, with BOOT_ANIMATION, the boot frames
# (pictures 50-114, played by the stock boot record).
bmp_files = [p for p in sorted(glob.glob(os.path.join("DWIN_SET", "*.bmp")))
             if uf.in_library(int(os.path.splitext(os.path.basename(p))[0]))]
for src in bmp_files:
    copy_file(src, ART_OUT)
with open(os.path.join(ART_OUT, "README.txt"), "w", encoding="utf-8") as f:
    f.write(
        "Source images for rebuilding DWIN_SET/16_68_.icl in the DGUS IDE (ICL tool).\n"
        "The display never reads these files.\n\n"
        f"{len(bmp_files)} images, named by page number; the picture index must equal the page number.\n"
        "Import ALL of them, in numeric order, and nothing else.\n\n"
        "These include the 'button held' pictures (035-049, 218-252) and the boot animation frames (050-114).\n\n"
        "SIZE LIMIT: the library must stay under 2,883,584 bytes (11 flash slots of 256 KB, slots 16-26), because\n"
        "the icon library is shipped as 29_ICO.icl. Do NOT add the hidden pages (6, 115, 126).\n"
        "Note: the spinner and selected-button icon libraries (33_SPIN.icl, 34_SEL.icl) cannot be made by this\n"
        "route; use build_release.py --script-icl for a complete set.\n"
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

# ── 3b. Script-built libraries (tools/build_icl.py) instead of the DGUS-IDE-built 16_68_.icl ─────────
# The picture library (with the boot frames and pressed pictures) and the icon libraries (spinner, selected
# button) are built straight from the BMPs. Nobody has seen every one of them accepted by the display yet:
# if it shows garbage, power off 15-20 s, then flash a known-good older set.
if SCRIPT_ICL:
    step("Building the picture and icon libraries by script")
    libs = [
        ("16_68_.icl", []),
        ("%d_SPIN.icl" % uf.SPINNER_ICON_LIB, ["--kind", "icons", "--src", os.path.join("DWIN_SET", "spinner_icons")]),
        ("%d_SEL.icl" % uf.STEP_ICON_LIB, ["--kind", "icons", "--src", os.path.join("DWIN_SET", "select_icons")]),
    ]
    for name, extra in libs:
        out = os.path.join("DWIN_SET", "auto_icl", name)
        r = subprocess.run([PYTHON, os.path.join("tools", "build_icl.py")] + extra + ["--out", out],
                           capture_output=True, text=True)
        lines = (r.stdout or r.stderr).strip().splitlines()
        print("  " + (lines[-3] if len(lines) >= 3 else NL.join(lines)))
        if r.returncode != 0:
            print(f"  build_icl.py FAILED for {name}")
            sys.exit(1)
        shutil.copy2(out, os.path.join(DWIN_OUT, name))

    # Every library must have its own flash slots (256 KB each, slot = number in the file name).
    SLOT = 256 * 1024
    spans = []
    for f in sorted(os.listdir(DWIN_OUT)):
        head = f.split("_", 1)[0]
        if f.lower().endswith((".icl", ".dzk", ".hzk")) and head.isdigit():
            first = int(head)
            spans.append((first, first + -(-os.path.getsize(os.path.join(DWIN_OUT, f)) // SLOT) - 1, f))
    clash = [(a, b) for i, a in enumerate(spans) for b in spans[i + 1:] if b[0] <= a[1] and a[0] <= b[1]]
    for a, b in clash:
        print(f"  FLASH OVERLAP: {a[2]} (slots {a[0]}-{a[1]}) and {b[2]} (slots {b[0]}-{b[1]})")
    if clash:
        sys.exit(1)
    print("  flash slots: " + ", ".join(f"{f} {a}-{b}" for a, b, f in spans))
    with open(os.path.join(RELEASE_DIR, "DWIN_SET_README.txt"), "w", encoding="utf-8") as f:
        f.write(NL.join([
            "DWIN_SET in this package uses libraries built by script (tools/build_icl.py), not the DGUS IDE:",
            "16_68_.icl (screens, pressed-button pictures, boot animation frames), %d_SPIN.icl (spinner) and"
            % uf.SPINNER_ICON_LIB,
            "%d_SEL.icl (selected-button highlight). Each decodes back to its source images, but the display" % uf.STEP_ICON_LIB,
            "may still reject one. If anything is garbled or blank: power the printer OFF for 15-20 seconds, then",
            "flash a known-good older DWIN_SET. Report what you saw so the builder can be corrected.", ""]))

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

stale_banner = ("""
!!! WARNING: THE PICTURE LIBRARY IN THIS PACKAGE (16_68_.icl) IS OUT OF DATE !!!
It was built before the latest artwork. It will show OLD pictures under NEW touch zones and
text records (missing button art, no pressed-button effect). Rebuild it first (STEP 0).
=======================================================
""" if ICL_STALE else ("""
NOTE: the picture and icon libraries in DWIN_SET were built by script, not the DGUS IDE (STEP 0 below is
not needed). If the display shows garbage after flashing it: power off 15-20 s and flash an older set.
See DWIN_SET_README.txt.
=======================================================
""" if SCRIPT_ICL else ""))

readme = f"""\
KobraMax-HC32 Firmware
Build: {git_ref}
Date:  {build_ts}
=======================================================
{stale_banner}
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
     SD:/DWIN_SET/29_ICO.icl            (the stock icon library, moved from slot 23)
     SD:/DWIN_SET/30_FontSong14X14.DZK  (moved from slot 24)
     SD:/DWIN_SET/33_SPIN.icl, 34_SEL.icl  (spinner and selected-button icons; script-built sets only)
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
   Use the printer's OWN card for this and do NOT format it: bed mesh, Z offset and PID are stored in
   eeprom.dat on it. A reformatted card means no mesh and the default Z offset (prints come out too
   high). Format only the separate card you use for the display (STEP 1).
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
