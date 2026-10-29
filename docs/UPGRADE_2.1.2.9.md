# Marlin 2.1.2.9 port (branch `marlin-2.1.2.9`)

The old line (`kobra-max-hc32`) is an older Marlin snapshot (wabbitguy's V2.8.7, labelled 2.0.8) with our HC32 HAL and the
DGUS UI. This branch re-applies our changes onto a clean upstream 2.1.2.9 tree instead of merging, because the two
trees differ in thousands of lines outside our changes.

Upstream trees used for comparison live in `_marlin_upstream/` (git-ignored): `Marlin-2.1.2.9`, `Marlin-2.0.8`,
`Marlin-bugfix-2.1.x` (has the official HC32 HAL).

## What was changed (the review result)

| Area | Change |
|---|---|
| Tree | `source/Marlin/{src,Configuration*.h,Version.h}` replaced by 2.1.2.9. Other HALs, `src/tests` removed. |
| HAL | Our `HAL/HC32` kept (hardware-validated clock, serial, SD, endstops). Removed only its 2.0.8 compatibility bridge in `HAL.h` / `HAL.cpp` / `inc/Conditionals_post.h` (2.1.2.9 calls `hal.*` directly). `HAL.h` includes `MarlinConfigPre.h`. `eeprom_sdcard.cpp::capacity()` no longer subtracts `eeprom_exclude_size` (gone in 2.1). `HAL/shared/serial_ports.h` is ours (not in 2.1.2.9). `platforms.h` gets the HC32 branch. |
| Board | `BOARD_AC_TRI_F1_V1` (6200) in `core/boards.h`, `pins/pins.h`, pins file moved to `pins/hc32f4/`. Renames: `FAN_PIN` -> `FAN0_PIN`, `SDIO_SUPPORT` -> `ONBOARD_SDIO`. |
| Config | Every setting that differs from vanilla 2.0.8 was applied to the 2.1.2.9 files by script (`Configuration.h`: ~80, `_adv.h`: ~85), then by hand: PID names (`DEFAULT_KP/KI/KD`, `DEFAULT_BED_*`), `DEFAULT_STEPPER_TIMEOUT_SEC 0`, `ANYCUBIC_LCD_DGUS` + `LCD_SERIAL_PORT 4`, `FIL_SENSOR_OPTIONAL`. |
| LCD | `ANYCUBIC_LCD_DGUS` added to `Conditionals_LCD.h` (EXTENSIBLE_UI, serial host) and `SanityCheck.h`. DGUS library at `lcd/extui/lib/anycubic_dgus/`, glue `lcd/extui/anycubic_dgus_lcd.cpp` (hooks renamed: `onHomingDone`, `onPrintDone`, `onSettingsStored/Loaded`, `onLevelingStart/Done`, `onSetPowerLoss`, `FSTR_P` kill strings). |
| ExtUI additions | `onParamInit` (via `MarlinUI::param_init`, called after `settings.first_load()`), `clearProgress_seconds_elapsed`, `getFilamentRunoutOriginState`, `getProbeState`, `ProbeTare`, `language_t` / `audio_t`. `getMeshValid` -> `getLevelingIsValid`. |
| Kobra Max core mods | `gcodeComment`, `activeFilamentChange`, `mel_PrintAbort` (MarlinCore); G28 / M600 flags; `T` = colour change (M600); optional filament sensor (`state_original`, `FIL_SENSOR_OPTIONAL`) in `feature/runout.*`; `print_progress` saved in the power-loss record; `CardReader::getLongPath`. |
| Display tools | `tools/`, `DWIN_SET/`, `docs/` synced from `kobra-max-hc32`. |

## Not ported yet / to verify on hardware

* Anycubic's flash-based outage record (`FLASH_OUTAGE_DATA_ADDR`): the 2.1.2.9 SD-file power-loss recovery is used instead; outage detection through `POWER_LOSS_PIN` (PC2, also the voltage monitor) needs checking.
* `mel_PrintAbort` no longer affects `PrintCounter` (2.1.2.9 counts a print as finished only when `stop(true)`).
* Case light: the pin-mode fix (plain output when brightness control is off) is in `feature/caselight.h` (`init()`).
* The Terminal reply-capture hook (`SERIAL_RUNTIME_HOOK`) and every other change made on `kobra-max-hc32` after commit 7cfa4d5 live in the DGUS library, which was copied from that branch's latest state.
* Nothing from this branch has been flashed yet.
