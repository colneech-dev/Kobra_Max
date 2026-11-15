# Third-party components and licences

This project is licensed under the GNU General Public License v3 ([LICENSE](LICENSE)). It contains or uses the following
third-party work. Entries marked **to verify** were not checked against the original licence text when this file was written.

| Component | Where | Licence | Notes |
|---|---|---|---|
| Marlin Firmware 2.1.2.9 | `source/Marlin/` | GPLv3 | Base of the firmware. |
| Anycubic Kobra Max firmware and DGUS display library | `source/Marlin/src/lcd/extui/lib/anycubic_dgus/` (modified), board files | GPLv3 (upstream repository `ANYCUBIC-3D/Kobra_Max`) | This repository is a fork of it. |
| wabbitguy's Kobra Max fork | git history, parts of `dgus_tft.*` | GPLv3 | Starting point of this code; history kept. |
| HC32F460 HAL for Marlin | `source/Marlin/src/HAL/HC32/` | GPLv3 (Marlin) | By shadow578 and contributors; modified here. |
| `framework-arduino-hc32f46x` 1.3.1 and `framework-hc32f46x-ddl` 2.2.3 | fetched by PlatformIO at build time, not stored here | GPL-3.0 (core); the vendor DDL code is reported to be BSD 3-Clause (**to verify** from the package) | Pinned and hash-checked by `tools/build_release.py`. |
| HDSC / Huada device headers and startup code | removed from this repository (they were inherited in `source/main/`, never compiled) | HDSC licence limited to HDSC components: not GPL-compatible | The build uses the device library fetched by PlatformIO (`framework-hc32f46x-ddl`) instead. |
| TMCStepper 0.7.3 | fetched by PlatformIO at build time | MIT (**to verify**) | Pinned in `platformio.ini`. |
| FatFs | `source/FatFs/` | its own licence, see `source/FatFs/00readme.txt` | Permissive licence in that file. |
| Font Awesome Free (`fa-solid-900.ttf`) | `tools/fonts/` | Fonts: SIL OFL 1.1. Icons: CC BY 4.0. Code: MIT (**to verify**) | Used to draw icons into the display pictures. The OFL requires its licence text to accompany the font: <https://fontawesome.com/license/free>. |
| Segoe UI | not included | Microsoft font licence | The display art is drawn with it on the build machine and the rendered pictures are committed. See `tools/fonts/README.md`. Whether shipping the rendered glyphs is covered by the font licence has **not** been clarified. |
| DWIN DGUS display file formats | `tools/` (written from the public guide and by observation) | n/a | The vendor guide and the HC32 datasheet are not redistributed; links are in [docs/reference/README.md](docs/reference/README.md). |

If you find a missing or wrong entry, please open an issue.
