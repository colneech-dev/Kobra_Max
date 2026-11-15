# Vendor reference documents

These documents are published by their vendors and are **not stored in this repository** (their terms do not clearly allow
redistribution). Download them yourself and put them in this folder if you want to use the searches mentioned in
[../DISPLAY_NOTES.md](../DISPLAY_NOTES.md); `*.pdf` and `*.txt` files here are ignored by git.

| Document | Needed for | Where to get it |
|---|---|---|
| **DWIN T5L DGUS II Application Development Guide (V2.8)**, `T5L_DGUS_V2.8.pdf` | The display file formats: touch file, show file (records), picture and icon libraries. The section numbers in the display notes refer to it. | <https://dwin-global.ir/downloads/T5L_DGUS_V2.8.pdf> (the link the notes were written from; if it has moved, search DWIN's download pages at <https://www.dwin-global.com/>) |
| **HC32F460 datasheet and user manual** (XHSC, formerly HDSC), for example `HC32F460 series Datasheet Rev1.3.pdf` | The processor: clocks, flash (EFM) sectors for the settings store, USART, SDIO. | <https://www.xhsc.com.cn/> (XHSC product pages for the HC32F460) or the distributor pages for the part, for example <https://www.lcsc.com/product-detail/C784663.html> |
| **HC32 HAL notes for Marlin** | How the HAL maps to Marlin; Marlin itself does not ship the vendor documents either. | <https://github.com/MarlinFirmware/Marlin/tree/bugfix-2.1.x/Marlin/src/HAL/HC32> |
| **HC32 DDL and Arduino core** | The device library the firmware is built with (fetched by PlatformIO). | <https://github.com/shadow578/framework-arduino-hc32f46x> and <https://github.com/shadow578/framework-hc32f46x-ddl> |
| **Anycubic Kobra Max firmware and display files** | The stock files this project started from (`DWIN_SET/*.base.*`). | <https://github.com/ANYCUBIC-3D/Kobra_Max> |

The display notes in this repository are written in this project's own words from the guide and from observation on a real display.
