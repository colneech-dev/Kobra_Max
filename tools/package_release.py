#!/usr/bin/env python3
"""
Package a built release folder (tools/build_release.py --out release_vN) for download: three files and their checksums.

    python tools/package_release.py release_vN OUT_DIR [NAME]

  OUT_DIR/Kobra_Max_<NAME>.zip   firmware.bin and the DWIN_SET folder (nothing else)
  OUT_DIR/firmware.bin           the firmware alone
  OUT_DIR/DWIN_SET.zip           the display files alone (the DWIN_SET folder inside)
  OUT_DIR/SHA256SUMS.txt         SHA-256 of the three files above

NAME defaults to the release folder's name. The release folder's README.txt, SETUP.md, build.log and picture sources are left out on purpose.
"""
import hashlib
import os
import shutil
import sys
import zipfile


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    rel, out = sys.argv[1], sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(os.path.normpath(rel))
    fw, dwin = os.path.join(rel, "firmware.bin"), os.path.join(rel, "DWIN_SET")
    if not os.path.isfile(fw) or not os.path.isdir(dwin):
        sys.exit(f"{rel}: firmware.bin or DWIN_SET missing (is this a release folder?)")
    os.makedirs(out, exist_ok=True)
    files = sorted(f for f in os.listdir(dwin) if os.path.isfile(os.path.join(dwin, f)))
    both, display = f"Kobra_Max_{name}.zip", "DWIN_SET.zip"
    with zipfile.ZipFile(os.path.join(out, both), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(fw, "firmware.bin")
        for f in files:
            z.write(os.path.join(dwin, f), "DWIN_SET/" + f)
    with zipfile.ZipFile(os.path.join(out, display), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(os.path.join(dwin, f), "DWIN_SET/" + f)
    shutil.copy(fw, os.path.join(out, "firmware.bin"))
    with open(os.path.join(out, "SHA256SUMS.txt"), "w", newline="\n") as f:
        for n in (both, "firmware.bin", display):
            with open(os.path.join(out, n), "rb") as g:
                f.write(f"{hashlib.sha256(g.read()).hexdigest()}  {n}\n")
    print(open(os.path.join(out, "SHA256SUMS.txt")).read(), end="")


if __name__ == "__main__":
    main()
