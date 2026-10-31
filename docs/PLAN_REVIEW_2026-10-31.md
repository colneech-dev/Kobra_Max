# Review and work plan — 2026-10-31

Branch `kobra-max-hc32-2.1` (Marlin 2.1.2.9 + our HC32 HAL + DGUS display), after release_v46.
This is a plan only: nothing in it is built or changed yet. Each phase ends with one build that is flashed and
tested before the next phase starts.

Approved by the owner (2026-10-31): Phase 1 yes, Phase 2 yes, Phase 3 (thumbnail investigation) yes, Phase 4
(report and send fixes to Marlin) yes. Phase 5 housekeeping: done now, repeated after Phases 1–4.

---

## 1. What was reviewed

| Source | Result |
|---|---|
| Marlin `lts-2.1.2` (the patch branch 2.1.2.x releases come from) | Identical to tag 2.1.2.9 (0 commits ahead). 2.1.2.10 is not out. Nothing to take yet. |
| Marlin `bugfix-2.1.x` | Has the HC32 HAL and, since 2026-10-14, PR #28448 "Anycubic Kobra Max / Neo / Go board, display (beta)" (based on maikramer/MarlinKobraMax). Its only reported testing is CI builds; no printer test is reported. Details in section 1.1. |
| Our Marlin core changes vs vanilla 2.1.2.9 | 30 files, about 300 lines (power loss, runout, M600/T, M117, G28, endstop names, Z offset at homing, ExtUI hooks, getLongPath, boot temp fault guard). Findings in Phase 1. |
| Our HC32 HAL vs `bugfix-2.1.x` HAL | Ours started from upstream and carries our fixes: watchdog 21.5 s, JTAG/SWD release (PA13/PA14/PA15 used), probe-tare line init, ADC pin-mode guard, PWM clamp, no panic in `set_pwm_frequency`, crash-safe `eeprom.dat` (tmp + rename), host-serial RX filter fix, HRC clock. Upstream has nothing newer we need except `eeprom/eeprom_flash.cpp` (basis for Phase 2). Our copy also fixes four upstream bugs (listed in Phase 4). |
| Stock Anycubic BSP (`source/board/bsp_init.cpp`) | 8 MHz crystal, MPLL ×42 → 168 MHz. Confirms upstream's 16 MHz is wrong. |
| wabbitguy/Kobra_Max (our upstream) | Last commit 2023-11; already fully in our history. |
| ANYCUBIC-3D/Kobra_Max | Last commit 2022-10 (V2.8.7). Nothing new. |
| BRiera/Anycubic_Kobra_Max_LIN_ADVANCE | Stock firmware + LIN_ADVANCE. Key lesson: with stealthChop on the extruder, LA stalls E mid-print; fix is spreadCycle (`M569 S0 E`). Their K 0.1 was for direct drive (LGX Lite), not the stock Bowden. |
| malebuffy/Kobra-Max-Cobra-Kai-UI-and-Firmware | G-code thumbnail preview (Cura / Prusa post-processing scripts, 150×120 PNG), terminal app, M117, host-print page switch. Thumbnail preview is the one feature we lack (Phase 3). |
| George-Corrigan ShadowUI | Display art and languages only, no firmware logic. |
| Klipper conversions (ryanpie86, fuegovic, Bratwurst04 …) | Different firmware and boards; not applicable. |

### 1.1 Upstream beta Kobra Max port (PR #28448): what is right and wrong

Matches ours (confirms our pin map): X/Y/Z/E step-dir-enable, endstops PA6/PC5/PA8, heaters PA1/PA0, thermistors
PC1/PC0, fans PB9/PA13/PA14, beeper PB5, runout PC13, case light PB8, power loss PC2, probe PB6 (RX) / PB7 (TX tare),
LCD on USART4 PB10/PH2, SDIO pins, TMC UART on PA9/PA15 (they use software serial on those pins, we use the
hardware USART1).

Wrong or unproven:
1. `IIC_BL24CXX_EEPROM` on PB6/PB7: these are the strain-gauge probe pins (the same file defines them as
   `AUTO_LEVEL_RX/TX_PIN`). There is no EEPROM chip there. The fork the PR is based on (maikramer) used
   `FLASH_EEPROM_EMULATION`, so the error came in during upstreaming.
2. `BOARD_XTAL_FREQUENCY 16000000`: the stock BSP uses 8 MHz (`bsp_init.cpp`: 8 MHz x 42 / 2 = 168 MHz). The stock
   firmware runs on these boards with working serial, which could not happen if the crystal were 16 MHz (everything
   would run at double speed). maikramer's fork sets no crystal value, so the 16 MHz has no visible source.
3. Test configs use `TMC2208_STANDALONE`; the board (V1.0.4) has TMC2209 X/Y/Z + TMC2208 E on one UART.
4. Test config `serial_port 1`, `lcd_serial_port 2`, while the pins file says LCD on USART4.
5. `eeprom_flash.cpp`: one sector, erase then write, so a power cut mid-save loses all settings.
6. Display driver is the stock Anycubic one (≈2,800 lines); ours (≈4,900 lines) has every fix and page since.

Decision: do not switch to it. Borrow the flash-EEPROM skeleton (Phase 2), report the errors (Phase 4).

---

## 2. Phase 0 — prove release_v46 (gate for everything below)

1. Save current settings (`M503`, copy `eeprom.dat`), full power-down 15–20 s, flash `release_v46/DWIN_SET` from a
   separate card, then `firmware.bin`. First boot resets settings (V82 → V88).
2. Follow `docs/SETUP.md`: bed mesh FIRST, then Z offset (System > SETUP WIZARD). Hand on the power switch for the
   first homing.
3. Report: `M420 V1` and `M851` after the mesh; AUTO Z spread; full `M122` output.
   TMC addressing check (decides how Phase 1.1 is done): E0 is a TMC2208 at address 3 on the same UART as three
   TMC2209s. A TMC2208 has no address pins, so it most likely answers only address 0. If so, E0 ignores its own
   commands and takes X's settings, and X reads collide (the X register-read quirk already seen). Check: `M122`
   E0 lines (blank or errors = E0 not reachable); `M906 X700` then `M906` (does E0 change too?); restore `M906 X800`.
   Same as the stock firmware (same addresses, X and E both 800 mA stealthChop), so it is not a new fault.
4. Tick each once: wizard 4 steps; 49-cell mesh page; E-steps page; advance K page; pressed pictures 155–158; boot
   jingle; first-layer test; 30 mm extrude; About labels.
5. Power loss: `M413 O` during a print, resume; a real power pull only after the first layer is good.
6. Tag the passing build `v2.1.2.9-kobramax-v46` and push the tag.

Failure handling: display garbage or stuck boot → power down 15–20 s, reflash the previous display set. Scrape → stop,
report `M420 V1` / `M851`, do not continue.

---

## 3. Phase 1 — review fixes (one build, low risk)

| # | Change | Where | Why | How to test |
|---|---|---|---|---|
| 1.1 | E driver in spreadCycle. If Phase 0 shows E0 answers on its own: `STEALTHCHOP_E` off, XYZ stay stealthChop. If E0 follows X (address-0 sharing): it can only change together with X, so choose between X+E spreadCycle (louder X) or keeping K small; owner decides with the Phase 0 numbers. | `Configuration_adv.h:3052` (and `STEALTHCHOP_XY` in the second case) | LIN_ADVANCE + stealthChop on E stalls the extruder in prints (BRiera). Needed before K is set above 0. | Print with `M900 K` > 0; E keeps feeding. `M122` is only trusted for E if Phase 0 showed E0 answers on its own. |
| 1.2 | T-code colour change only when the tool number differs from the last T (first T still ignored). Keep `colourCounter` resets (G28, print start). | `src/gcode/gcode.cpp:1107` | Today every T after the first runs M600, so a repeated `T0` from a slicer or host pauses the print. | Test file `T0 … T0 … T1 … T1`: exactly one M600 (at the first T1). |
| 1.3 | `getLongPath()` walks every path segment, building `folder/…/file` long names with length checks. | `src/sd/cardreader.cpp:368` | Stops after the first segment, so a file in a subfolder shows the folder name on the power-loss page. | Power loss (`M413 O`) on a file in a subfolder: page shows the file's long name. |
| 1.4 | Remove page 115 handler (`M1024` buttons), its dispatch and `PAGE_AUTO_OFFSET`. | `dgus_tft.cpp:590`, `:1247`, `:3703`; `dgus_tft.h:97`, `:550`; tools that list 115 | Page is hidden and unreachable; `M1024` exists on neither branch. Frees flash. | Build; `cross_check_display.py` 0 errors. |
| 1.5 | Correct wrong comments: `dgus_tft.cpp:301` ("G29 bakes the Z offset into the mesh" — it does not; the mesh holds absolute heights); `sysclock.cpp` header (says crystal with HRC fallback, code is HRC only); `platformio.ini` `BOARD_XTAL_FREQUENCY` marked "required by the HC32 SanityCheck, not used for the clock"; `HAL/HC32/app_config.h` `HANG_ON_PANIC 1` removed (leftover from the old debug branch; it has no effect because our `panic_end()` in `MinSerial.cpp` always resets, but it reads as if a crash would hang with heaters on). | as listed | Wrong comments caused the scrape confusion; keep docs truthful. | Build only. |
| 1.6 | Boot temperature-fault guard: keep heaters forced off in the first 5 s, but print one `Temp fault ignored at boot` warning. | `src/module/temperature.cpp:1352`, `:1363` | Today the fault is swallowed silently. | Boot with the thermistor unplugged: warning, then a real MINTEMP after 5 s. |
| 1.7 | Command-injection guard: helper that refuses (and shows "Busy") when commands from the display are still pending; used by multi-step jobs and every display `M500`. Audit all 62 `injectCommands*` sites and list each as "guarded" or "single tap, safe". | `dgus_tft.cpp` | `injectCommands_P` keeps one pointer; a second call before the first runs replaces it (lost M500, lost heater-off). | Fast double taps on each job's buttons; queue never loses the tail (heaters always end off). |
| 1.8 | Power-loss debug (`DEBUG_POWER_LOSS_RECOVERY`): leave on until Phase 0 step 5 passes, then turn off unless `M413 O` is still wanted. | `src/feature/powerloss.h` | Costs flash and prints debug on resume. | Owner decides after Phase 0. |

Phase 1 build: release_v47. Test list = the "How to test" column plus a short regression (home, mesh view, one print).

---

## 4. Phase 2 — settings in the chip's own flash

Goal: settings no longer depend on the SD card (survive card swaps, no "no card = zero settings" workaround).

Design:
1. New `src/HAL/HC32/eeprom/eeprom_flash_ab.cpp` (`FLASH_EEPROM_EMULATION`), based on upstream `eeprom_flash.cpp`
   (EFM unlock / sector erase / single program, interrupts off while erasing).
2. Two 8 KB sectors, A = 0x3C000, B = 0x3E000 (reserved already: `board_upload.maximum_size = 245760`). Each copy:
   header {magic, sequence number, length, CRC32} + 4 KB data. Load: newest valid copy. Save: write the OTHER sector,
   verify by read-back, only then is it current. A power cut mid-save leaves the previous copy intact.
3. Addresses fixed at 0x3C000/0x3E000 (not "last sector"), so the same build works on 256 KB (KCTA) and 512 KB
   (PETB) chips. Static check: firmware image end ≤ 0x3C000 (keep, plus the runtime check from upstream).
4. Migration on first boot: flash empty and `eeprom.dat` on the SD card → load it, save to flash, leave the file.
   Fallback: neither → defaults.
5. Remove `if (!card.isMounted()) settings.reset()` (`MarlinCore.cpp:1344`) and `SDCARD_EEPROM_EMULATION` from
   `pins_AC_TRI_F1_V1.h`.
6. No erase during a print (interrupts off stalls the steppers):
   - `PRINTCOUNTER_SAVE_INTERVAL 0` (today it saves every 60 min during prints; stats are saved at the end instead).
   - Every display-triggered `M500` audited (e.g. Z-change save `dgus_tft.cpp:3200`, babystep, PID, E-steps):
     during a print they are deferred until the print ends (flag + save in idle when not printing).
   - `M500` from G-code during a print: deferred the same way, with a "saved after print" message.
7. Migration needs an SD reader for `eeprom.dat` that still compiles once `SDCARD_EEPROM_EMULATION` is off (the
   current reader is only built with it). Small one-shot read in the new file.
8. Check before writing code: whether the HC32F460 keeps fetching code from flash while a sector is erased (CPU
   waits) or not (then the erase / program routines must run from RAM). Upstream assumes it waits; confirm in the
   reference manual / DDL examples.
9. While interrupts are off (erase + program of one sector), serial bytes from the display or a host can be lost.
   Acceptable only because saves happen when idle; a lost touch is simply pressed again.
10. Our HAL removed upstream's `FLASH_EEPROM_EMULATION needs HC32_FLASH_SIZE` check; add our own static check that
    both sectors lie at or above the image limit (0x3C000) and below 256 KB.
11. Settings size: confirm the settings block (7x7 mesh included) plus header fits the 8 KB sector and the 4 KB
    `MARLIN_EEPROM_SIZE` (Marlin reports the size on `M500` / boot); maikramer used 8 KB, so check, not assume.
12. Flash cost estimate: about 1 KB.

Tests: `M500`/`M501`/reboot; 10 power pulls during `M500` (always boots with old or new settings, never defaults);
boot with no SD card keeps settings; migration from an existing `eeprom.dat`; print-counter totals after a print;
`M500` during a print is deferred.

Phase 2 build: release_v48. Owner action: photo of the MCU marking (C = 256 KB, E = 512 KB) — nice to have, not
required.

---

## 5. Phase 3 — G-code thumbnail preview (investigation first, then a go / no-go)

Step 1, research (no code):
1. Read malebuffy's firmware and post-processing scripts: image format (size, colour depth, how it is embedded in the
   G-code), how the display draws it (DGUS VP image, icon slot, or pixel writes), how long it takes over 115200 baud.
2. Constraint: picture library has ~155 KB spare, so thumbnails cannot be stored as library pictures; they must be
   drawn at run time from the file.
3. Check whether the slicer formats you use (Prusa / Orca / Cura) can produce it without a custom script.

Step 2, report to the owner: approach, flash / RAM cost, display-memory cost, time to show one preview, what changes in
the file list page. Build only after a yes.

Also checked in this phase:
- 3.2 Host (OctoPrint) prints switch to the print page — verify we already do (wabbitguy merge).
- 3.3 Input shaping (open item MD5): available in 2.1.2.9; needs measured X/Y resonance frequencies; would ship off.
  The archived old branch (`archive/upgrade-2.1.x`, `page6_handle`) has a finished Input Shaping page: X/Y
  frequency and damping +/- via `M593`, reading `stepper.get_shaping_frequency()`. Reuse it on a new page number
  (page 6 is now the keyboard).
- 3.4 `SDCARD_SORT_ALPHA`: decide whether the display's own file list makes it pointless.
- 3.5 LA K for the stock Bowden: calibrate (expect well above the 0.1 direct-drive value), do not copy.

---

## 6. Phase 4 — report and send fixes to Marlin (public, done after Phases 1–2 are proven)

1. Issue on MarlinFirmware/Marlin referencing PR #28448, with evidence: I2C EEPROM on the probe pins; 8 MHz crystal
   (stock BSP `bsp_init.cpp`); TMC2209/2208 UART on PA9/PA15 for the V1.0.4 board; LCD serial port mismatch;
   single-sector flash save is not power-cut safe.
2. PR with our HC32 HAL fixes, each re-checked against current `bugfix-2.1.x`:
   - `HAL.cpp` `core_hook_usart_rx_irq` host-port filter (`false || a != X || a != Y` is always true with two host
     ports, so the emergency parser never sees input), and feeding the matching serial's parser.
   - `timers.h` `HAL_timer_interrupt_enabled()` returns `isPaused()`, the opposite of its name.
   - `sdio.cpp` card size `_MAX(cardSizeBytes, UINT32_MAX)` always returns UINT32_MAX (should be `_MIN`); a failed
     init leaks the handle.
   - `inc/SanityCheck.h` tests `PANIC_USART3_TX_PIN` twice (the second should be USART4).
3. PR (after Phase 2 is proven): two-sector power-safe flash EEPROM for HC32.
Not sent: the "Z offset shifts Z0 at homing" change is Anycubic vendor behaviour, not an upstream bug.

Each text is shown to the owner before it is posted. Evidence for the crystal point is the stock BSP and the
stock firmware working, not a measurement on our build (ours runs on the internal clock).

---

## 7. Phase 5 — repo housekeeping

Now (2026-10-31): plan committed; `upgrade-2.1.x` archived as local tag `archive/upgrade-2.1.x` (54 commits found
nowhere else) and the branch deleted; `kobra-max-hc32-2.1` pushed to origin. The archive tag is local only;
pushing it (`git push origin archive/upgrade-2.1.x`) would protect it against losing this PC (owner to decide).
After Phases 1–4: push branch and tags again; update README branch section, memory notes, `docs/PLAN_2.1.2.9.md`.

---

## 8. Later — staying in step with Marlin

- 2.1.2.10 when released: diff 2.1.2.9..2.1.2.10, 3-way merge into our 30 changed core files, re-run the
  vendor-deletion check, re-check `set_axis_is_at_home` Z shift, build, test Z offset before releasing.
- 2.1.3 (first release with the HC32 HAL): consider moving onto it — Marlin's board name, a corrected pins file, our
  HAL fixes as patches, our display code kept. Only after 2.1.3 is final and the beta Kobra port has run on printers.
- Crystal clock (8 MHz, with HRC fallback): possible accuracy gain for UART / timers; only after everything else is
  proven, since a clock mistake stops the printer booting. Ready-made code: commit `dab2751` in
  `archive/upgrade-2.1.x` (tries the crystal with high drive, checks the timeout, falls back to HRC; both give
  200 MHz). It was replaced the same day by "HRC always" while chasing a no-boot that later turned out to be the
  display serial (USART4) setup, so the crystal itself was never shown to be at fault.

## 9. Hostile review of this plan (2026-10-31, same day)

Checked every claim against the sources. Corrected above: CI-only wording for the upstream PR; crystal evidence and
where the I2C EEPROM error came from; TMC2208 addressing makes 1.1 depend on a Phase 0 check; `BOARD_XTAL_FREQUENCY`
is required by a sanity check (not "unused"); temperature line numbers; `HANG_ON_PANIC` leftover; five Phase 2 gaps
(SD reader for migration, flash-erase code fetch, lost serial bytes, address check, settings size); archived Input
Shaping page and crystal-fallback code; three more upstream HAL bugs; archive tag only local.
Confirmed correct: lts-2.1.2 = 2.1.2.9; all line references in 1.2 to 1.4; 62 injection sites; M1024 handled on no
branch; flash limit 245760 = app 0x8000 to 0x3C000; pin matches; wabbitguy and Anycubic have nothing new;
`panic_end()` always resets.

## 10. Rejected

Upstream beta display driver or pins file; 16 MHz crystal; I2C EEPROM; upstream single-sector flash save as is;
changing the clock source now.
