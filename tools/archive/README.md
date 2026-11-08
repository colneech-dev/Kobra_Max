# tools/archive

Kept for history only. Nothing in the build uses these files; do not run them.

| File | What it was |
|------|-------------|
| `fix_eng_pages_and_term.py`, `fix_mpc_save.py`, `fix_null_terminators.py`, `patch_page216.py` | One-off migrations of `dgus_tft.cpp` (language-neutral pages, terminal VP overflow, MPC save, NUL escapes, page 216). Already applied; they hold absolute paths to one PC and would rewrite the firmware source if run. |
| `34_BootAnim.icl` | The Movie2ICL boot-animation library from the 2.0.8 era. The boot frames now live inside `16_68_.icl` (pictures 50-114), and slot 34 belongs to `34_SEL.icl`: shipping this file would overwrite the selected-button icons. |
