Import("env")
import shutil, os, time

def rename_firmware(source, target, env):
    build_dir = env.subst("$BUILD_DIR")
    src = os.path.join(build_dir, "firmware.bin")
    dst = os.path.join(build_dir, "Firmware.bin")
    for _ in range(10):
        try:
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            return
        except OSError:
            time.sleep(0.5)

env.AddPostAction("checkprogsize", rename_firmware)
