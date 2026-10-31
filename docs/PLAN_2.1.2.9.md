# Marlin 2.1.2.9 port: fix plan (2026-10-30)

Branch `kobra-max-hc32-2.1`. Background and what was already ported: `docs/UPGRADE_2.1.2.9.md`.
Sources: my own old-vs-new comparison and an independent read-only review of the port.

## Already verified equal or fine

* DGUS library: identical to `kobra-max-hc32` apart from 2.1 API renames (`SERIAL_ECHOLNPAIR` -> `SERIAL_ECHOLNPGM`,
  `getMeshValid` -> `getLevelingIsValid`, `disable_all_steppers` -> `stepper.disable_all_steppers`, `HAL_watchdog_refresh` -> `hal.watchdog_refresh`).
* HC32 HAL: clock, serial, SD, endstops, timers, ADC identical; only the 2.0.8 compatibility bridge was removed.
* Pins: identical apart from `FAN_PIN` -> `FAN0_PIN`, `SDIO_SUPPORT` -> `ONBOARD_SDIO`.
* Effective configuration: identical apart from option renames and these new 2.1 defaults:
  arcs `MIN_ARC_SEGMENT_MM 0.1` / `MAX_ARC_SEGMENT_MM 1.0`; `PRINTCOUNTER_SAVE_INTERVAL 60`; `POWER_LOSS_ZRAISE` 2 (old 0).
* Thermistor tables 1 and 11: same temperatures; 2.1.2.9 oversamples 16x instead of 8x (scaled internally).
* Display hooks (`ExtUI::on*`): every hook the old core fired is fired by 2.1.2.9 under its new name, except the
  probe-preheat hooks (ported in b144c08).

## Ported in b144c08 (build pending item 0)

Strain-gauge probe reset (`AUTO_LEVEL_TX`) before every probe move; "Probe preheat start/stop" display hooks;
5 s startup grace for MIN/MAXTEMP errors; M117 text kept for the print page (`gcodeComment`); aborted prints not counted.

## To do

| # | Item | Severity | Fix |
|---|---|---|---|
| 0 | b144c08 does not build: `lcd/marlinui.cpp` uses `ExtUI::` without the include | build | `#include "extui/ui_api.h"` under `EXTENSIBLE_UI` |
| 1 | Power-loss detection: 2.1.2.9 reads `PC2` digitally (~2.2 V at 24 V); the old firmware compared the ADC value (< 2200 counts for > 4 samples) | safety | restore the ADC-threshold `outage()`; switch heaters off before the SD write |
| 2 | Power-loss resume trusts the saved Z; the old firmware did a full `G28`, Z+5, slow purge | safety | home Z on resume (as before) |
| 3 | `POWER_LOSS_ZRAISE` defaults to 2 (old 0) | behaviour | set 0 explicitly until resume is tested |
| 4 | Homing-failure kill no longer names the axis; the DGUS endstop-fault pages never appear | display | pass X/Y/Z through `validate_homing_move()` as before |
| 5 | `G28` no longer resets `colourCounter` | behaviour | `case 28: colourCounter = 0; G28();` |
| 6 | Pause strings changed ("Reheat Done", "Purging...") but `dgus_tft_defs.h` matches the old text | display | update `MARLIN_msg_reheat_done` / `MARLIN_msg_filament_purging` |
| 7 | Unused EEPROM backends (`eeprom_bl24cxx.cpp`, `eeprom_wired.cpp`) use the removed `eeprom_exclude_size` | tidy | same fix as `eeprom_sdcard.cpp` |
| 8 | First boot resets settings (EEPROM V82 -> V88): Z offset, mesh, language lost | first flash | procedure: `M503` on the old firmware first, then re-level and `M500` |

Then rebuild, cross-check the display files, package the next release, update `docs/UPGRADE_2.1.2.9.md`.
New 2.1.x features wait until this base has run on the printer.

## Decisions (recommendation in bold)

1. Power-loss detection: **restore the old ADC detection** / disable it (`POWER_LOSS_PIN -1`) and rely on per-layer saves.
2. Resume: **home Z** / trust the saved Z.
3. `POWER_LOSS_ZRAISE`: **0** / 2.

## Progress 2026-10-30

Done in `8376509`: build include (0), homing-failure axis (4), `G28` colour counter (5), pause strings (6), unused EEPROM backends (7), default feedrate 2000.
Done after that: manual Z-offset page parks at a saved start height (default 1.0 mm, `-`/`+` row on the Leveling menu) instead of Z0.
Held for decisions: power loss (1, 2, 3, `M413 O`), thermistor variance monitor. Auto Z offset: see the chat discussion (needs a design choice).
Auto Z offset (b3de2f5): third button on the Leveling menu. Checks for a bed mesh (runs the normal probe pre-check and G29 first when none exists),
heats, homes and runs `M48 P5` at the bed centre, reads the "Range:" from the reply and shows it on the Z page ("Spread 0.012 mm OK/FAIR/NOISY",
thresholds 0.03 / 0.08 mm), then parks at the manual start height with the heaters off. The user sets the final offset with the manual controls;
the offset applies to the whole mesh (the mesh holds contact heights, see the comment above `save_zoffset`). Untested on hardware: the spread
thresholds are guesses until real strain-gauge numbers are seen.

Power loss (decisions 1-3, done):
* Detection: raw PC2 ADC (new `PowerMonitor::getVoltsRaw()`) below 2200/4095 and still falling after more than 4 samples, as on the original firmware. Heaters are switched off before the SD write.
* Resume: `G92.9 Z<saved>`, lift `POWER_LOSS_ZRAISE` = 5 mm, `G28 R0 XY`, move to {0,0}, `G28 H Z` (home Z on the spot, no safe-homing move), lift back, continue.
  CORRECTION to the earlier recommendation "ZRAISE 0": in 2.1.2.9 that value is the resume lift when there is no UPS, so 0 would drag the nozzle across the print while XY homes. The original firmware got its lift from Z_HOMING_HEIGHT in G28.
* `M413 O` (simulated outage, via `DEBUG_POWER_LOSS_RECOVERY`) is back. It saves the job and ends the print without killing the board; power-cycle and resume to test.
* Untested on hardware. Test with `M413 O` on a short print first.

Independent review (2026-10-30): R1 fixed (`PROBING_MARGIN 10` had been dropped, G29 would have probed the bed edge); B3 fixed (upload size limit 480 KB).
Open from that review: B2 watchdog ~21 s, B5 internal G28 clears the filament-change flag, B1 looser thermal protection, features: M73 progress, variance monitor, bilinear subdivision, EXTRA_PROBING, linear advance, input shaping (hardware tests).

Low-risk features enabled: THERMAL_PROTECTION_VARIANCE_MONITOR, SET_PROGRESS_MANUALLY (M73 progress/remaining time), EXTRA_PROBING 1 (4 probes per point, worst discarded), ABL_BILINEAR_SUBDIVISION (3). Flash 39.0% of 448 KB, RAM 10.0%. If the variance monitor ever kills a healthy heat-up, turn it off first.

Hostile review (two reviewers, 2026-10-30) - fixed:
* H1 outage save recorded all heater targets as 0 (my heaters-first change): outputs are cut, targets kept until after the save.
* H2 `getLongPath` copied a full path into a 13-byte buffer (recovery page file name): buffer is now MAXPATHNAMELENGTH.
* M1 resume applied the bed mesh twice to the first Z: leveling stays off until the last resume move.
* M2 the "Write" debug dump (500+ bytes on a 64-byte serial buffer) is gone from every save.
* M3 no SD card at boot left every setting at zero: `settings.reset()` when the card is not mounted.
* Auto Z: the 300 s deadline injected over a running command: removed; every key is ignored while the nozzle sequence runs (BACK during it used to leave heaters on / overwrite the sequence).
* Terminal: leading spaces bypassed the M109/M190 guard. Manual Z minimum start height is 0.3 mm.
Left as is (matches the old firmware, hardware-proven): Z_PROBE_LOW_POINT -10, 21 s watchdog, runout state_original logic, looser thermal protection.
To check on the first power-up: `M119` with the Z input pressed by hand before the first G28 (Z homes on Z_MIN_PIN PA8, not the strain gauge).

Native PROBE_TARE (2026-10-30): the custom strain-gauge reset in `probe.cpp` is gone; `PROBE_TARE` (pin AUTO_LEVEL_TX_PIN = PB7, LOW for 300 ms, 100 ms settle) does the same job with Marlin's own code, so there is one core patch less to merge. Marlin tares before each probe attempt as well as before each probe_down_to_z call, so each G29 point takes a little longer than before. Untested on hardware: check that G29 still probes cleanly.
Drivers (user, 2026-10-30): board is the Anycubic TriGorilla Pro A V1.0.4 with soldered TMC2209 on X/Y/Z and TMC2208 on E0, all on one UART (hardware serial MSerial1, PA9/PA15, addresses 0-3). The config already matches. Upstream Marlin's Kobra Max CI configs say TMC2208_STANDALONE, which is a simplification; ignore it. Known board quirk: a TMC2208 has no address pins, so it answers as address 0 whatever E0_SLAVE_ADDRESS says (not checked here what that does to X's register reads).
Marlin upstream added Kobra Max board + display support (PR #28448, 2026-10-14, in bugfix-2.1.x, not yet released): when 2.1.2.10 or later ships, expect a competing board (TRIGORILLA_F1_V1) and driver (anycubic_kobra).

Flash budget (2026-10-30): the build now assumes the smallest HC32F460 (256 KB) so it runs on every variant. The app gets 0x8000-0x3C000 (208 KB, linker limit via `board_upload.maximum_size = 245760`); the last two 8 KB sectors (0x3C000 outage data, 0x3E000 settings) are what Anycubic's own code used (`source/framework/cores/flash.cpp`) and are kept free for a future two-sector settings store (ping-pong, sequence number + CRC, SD copy as backup; power-loss file stays on SD). Current size 179 KB = 84 %, about 29 KB of headroom: linear advance + input shaping would fit, UBL would not. Still to confirm: the chip marking on the mainboard (C = 256 KB, E = 512 KB).

Improvements batch (2026-10-30, unbuilt):
* Config: `DEBUG_LEVELING_FEATURE` off (flash), mesh fade height 10 mm, `Z_PROBE_LOW_POINT` -4 (was -10), junction deviation instead of classic jerk, linear advance on with K = 0.
* The `T` colour-change counter is reset when a print starts (it used to survive from the previous print), README credits Marlin, Anycubic, wabbitguy, shadow578's HC32 HAL.
Deliberately NOT done, with reasons:
* Watchdog 5.4 s: tried before on hardware and too short (setup plus the first idle path took 5-6 s); keep 21 s.
* Stepper timeout: `DISABLE_X/Y/Z` are off, so a timeout would do nothing; enabling them unhomes axes and breaks pause/resume flows.
* Alphabetical SD sort: `SDSORT_LIMIT` can hide files beyond the limit in the display's list; needs a test with a full card.
* Thermal protection tightening: only after several clean prints (false kills are worse than loose limits).
* `TMC_DEBUG` kept: `M122` is the only way to see what the drivers report (needed for the TMC2208 address quirk).
* Internal G28 clearing `activeFilamentChange`: no real trigger found (the display clears it itself).
* New screens (mesh viewer, E-steps page, LA K page): after the display has been proven on the printer.

REGRESSION FOUND ON HARDWARE (2026-10-31, release_v44): the Z offset had no effect on the nozzle height. The vendor's 2.0.8 `set_axis_is_at_home()` subtracts `probe.offset.z` from the Z home position for EVERY Z home (Anycubic deleted the `#if HOMING_Z_WITH_PROBE` that upstream has around it). Marlin 2.1.2.9 only does it when homing with the probe; this config homes Z on the Z-min endstop (PA8; the probe pin is PB6 = AUTO_LEVEL_RX_PIN, `USE_PROBE_FOR_Z_HOMING` is off), so a saved offset only changed what a later G29 stored in the mesh. Result: mesh, then manual Z, then SAVE left Z0 at the contact height and the nozzle scraped. Fixed in `module/motion.cpp` (unconditional `current_position.z -= probe.offset.z`). The manual Z page's arithmetic (SAVE = live offset + start height) was written for exactly that behaviour. A mesh made before the fix stays valid (it holds contact heights); an offset saved before the fix now takes effect at the next G28.
LESSON: the earlier "vendor-only lines" comparison finds lines the vendor ADDED, not conditions the vendor DELETED. Still to do: list lines present in vanilla Marlin but removed in the vendor tree (core/module/gcode/feature) and check each against 2.1.2.9.

Vendor-deletion check (2026-10-31): lines present in every vanilla Marlin 2.0.6.1-2.0.9.11 release but missing from the old tree (counted as multisets, so a removed `#if` that appears elsewhere is still found; core/module/gcode/feature/libs/sd/inc, HAL and servo excluded).
Result: one real behaviour change, the removed `#if HOMING_Z_WITH_PROBE` around the Z-offset shift in `set_axis_is_at_home()` (fixed in 93e20bb). Everything else is already ported (`validate_homing_move` with the axis, `case 28` / `case 'T'`, M117, M600 flag, runout threshold decision) or is formatting / older-snapshot drift (`{0}` initialisers, float suffixes, macro helpers, JTAG disable moved into the HAL init, kill-loop watchdog refresh). The vendor's per-axis homing_state in G28 is covered by the kill component the display reads.
Method limit: this finds deleted lines, the earlier analysis found added lines; a line the vendor CHANGED shows up in both only if its new text is unique, so changed conditions inside shared lines can still hide. The hardware test above is what caught the Z offset.
