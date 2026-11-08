# Fonts used by the screen generators

| File | Where it comes from | In git? |
|------|---------------------|---------|
| `fa-solid-900.ttf` | Font Awesome 6 Free Solid (SIL Open Font License 1.1) | yes |
| `segoeui.ttf`, `segoeuib.ttf` | Segoe UI regular / bold, Microsoft (Windows licence, not redistributable) | **no** (git-ignored) |

`tools/generate_screens.py` (and every tool that imports it: `cross_check_display.py`, `generate_boot_animation.py`, ...)
draws all text with Segoe UI. There is deliberately **no fallback**: another font would change every picture, the
BMPs would no longer match the committed ones and the touch zones / text records were laid out for Segoe UI.
If the font is missing the tools stop with an error.

Search order: `$KOBRA_FONT_DIR`, then this folder, then `%WINDIR%\Fonts` (`C:\Windows\Fonts`).
On Windows nothing needs doing. On Linux/macOS copy `segoeui.ttf` and `segoeuib.ttf` from a Windows
installation you own into this folder (or point `KOBRA_FONT_DIR` at them). Do not commit them.

The committed art was drawn with the Segoe UI that ships with Windows 11. A different version
of the font can move glyphs by a pixel: `python tools/cross_check_display.py` then reports the BMPs as stale.
