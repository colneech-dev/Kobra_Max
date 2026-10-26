# PlatformIO pre-build script: stamps the git revision into M115's FIRMWARE_NAME
# (DETAILED_BUILD_VERSION, see Marlin/src/inc/Version.h), e.g. "2.0.8-hc32-ab12cd3-dirty".
# Falls back to the plain version when git is unavailable.
Import("env")
import subprocess

def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, text=True,
                                   cwd=env.subst("$PROJECT_DIR")).strip()

try:
    ver = "2.0.8-hc32-" + git("rev-parse", "--short", "HEAD")
    if git("status", "--porcelain", "--untracked-files=no"):
        ver += "-dirty"
except Exception:
    ver = "2.0.8-hc32"

env.Append(CPPDEFINES=[("DETAILED_BUILD_VERSION", env.StringifyMacro(ver))])
