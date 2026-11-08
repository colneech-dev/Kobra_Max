# Review plan, 2026-11-08 (after release_v62)

Source: five independent code reviews (Opus), each given one area and NO prior knowledge of the project, each comparing with upstream Marlin
(2.1.2.9, lts-2.1.2, bugfix-2.1.x) and, where relevant, the upstream HC32 HAL, the stock Anycubic source and the community display projects.
Areas: (A) Marlin core changes, (B) HC32 hardware layer + flash settings, (C) display driver, general part, (D) levelling / calibration / wizard /
first-layer / K-test code, (E) tools, display pipeline, release packaging, docs.

**How far to trust this plan.** Everything below was found by READING code. Nothing was run on the printer. Three of the most alarming claims were
re-checked in the code by me (tagged **[confirmed in code]**): the tone hang (HW-1), the resume/M600 wait (DR-1) and the purge-before-gate order (LV-1).
Their effect on the real printer has NOT been observed. Everything else is tagged with the reviewer's own confidence: `verified` = traced in code,
`suspected` = plausible but needs a test. Item IDs: HW = hardware layer, MC = Marlin core, DR = display driver, LV = levelling code, TL = tools/docs.

Nothing in this plan has been implemented. Order of work and the decisions needed from the owner are at the end.

---------------------------------------------------------------------------------------------------------------------------------------

## 0. Test on the printer FIRST (cheap, decide what is real)

Do these before changing code; each one either confirms or kills a top finding. Heaters cold unless stated.

| # | Test | Confirms | Expected if the finding is real |
|---|------|----------|---------------------------------|
| T1 | Start any SD print (or a short G-code), PAUSE, then RESUME. Repeat with an `M600` in the file. Hot nozzle, hand near the power switch. | DR-1, DR-2 | After the purge the printer waits forever, nozzle stays hot, STOP does not leave it. |
| T2 | Heaters OFF. Send `M300 S440 P200` from the Terminal. | HW-1 | Board freezes ~21 s then resets (display dead, no serial). Do NOT run with heaters on. |
| T3 | `M119` with filament in and out (and probe cable unplugged, then plugged). | MC-4, MC-3 | Shows the real runout polarity; shows whether an unplugged probe reads "triggered" or "open". |
| T4 | Make a mesh. Put a 3 mm shim/plate on the bed. Heaters at temperature. Run the first-layer test, hand on the power switch. | LV-1 | Purge lowers to Z0.3 against the old mesh and the nozzle presses into the plate at X20 Y10. After the fix it must refuse before any low move. |
| T5 | Same shim, press AUTO Z OFFSET (mesh valid). | LV-2 | Nozzle goes into the plate at the start height. |
| T6 | After SAVE on the Z page (no re-home), use the Move page to go to Z0, check with paper. | LV-8 | Z0 is below paper by the start height. |
| T7 | Open the mesh viewer (9x9): do all 9 rows and both info lines draw? | TL-5 | Bottom rows / Range and Low/High lines missing. |
| T8 | `M500` in the Terminal, note the About counter "#n"; re-flash the same firmware.bin; check "#n". | HW-S7 | Counter resets if the bootloader erases the settings sectors. |
| T9 | Pause a print, change Z offset on Print Settings, SAVE, resume. | DR-7 | Offset change/M500 lost (replaced by the pending M24). |

---------------------------------------------------------------------------------------------------------------------------------------

## 1. CRITICAL / HIGH safety items (do first)

### HW-1 CRITICAL: any buzzer tone freezes the board with interrupts off  [confirmed in code]
- `src/HAL/HC32/tone.cpp:19-31` busy-waits on `millis()`; `millis()` only advances in the SysTick interrupt. `src/libs/buzzer.cpp:68-71` calls
  `ExtUI::onPlayTone` inside `CRITICAL_SECTION_START()` (`__disable_irq`), so `tone()` never returns. (Reviewer also found `cpsid i` before the call in
  the shipped binary.) Triggers: every `BUZZ()`: M300 from G-code/host, the M600 waiting beeps, runout-driven M600.
- Effect: stepper ISR, temperature ISR and serial stop; heater pins stay as they were until the watchdog resets the board ~21.5 s later (see HW-2).
  Same root cause makes `PlayTune()` play every note twice as long.
- Fix: make `tone()` non-blocking (timer PWM on PB5 or a small timer ISR with a countdown; `noTone()` stops it); at minimum return at once when
  `__get_PRIMASK()` is set and drop the CRITICAL_SECTION wrapper in this HAL. Effort S/M.
- Test: T2 before, then after the fix; M600 beeps with heaters on.

### DR-1 CRITICAL (suspected on hardware): every resume after a pause, and every M600, waits forever after the purge  [confirmed in code]
- Marlin 2.1.2.9 defines `M600_PURGE_MORE_RESUMABLE` for EXTENSIBLE_UI (`inc/Conditionals_post.h:2934`). `pause.cpp:284-292`, after the purge:
  `pause_menu_response = PAUSE_RESPONSE_WAIT_FOR; while (pause_menu_response == PAUSE_RESPONSE_WAIT_FOR) idle_no_sleep();`. Only
  `ExtUI::setPauseMenuResponse()` or a host `M876` ends it. A grep of the display driver finds no call to it.
- Effect: display PAUSE then RESUME hangs; so does M600 (runout or from the file). STOP does not clear it. Nozzle stays hot (the idle heater timeout is
  also off while "printing", see DR-3). Upstream has the same gap (they added `ExtUI::onPauseMode` for this in bugfix-2.1.x; the Anycubic drivers do not answer it).
- Fix: in IdleLoop `if (pause_menu_response == PAUSE_RESPONSE_WAIT_FOR) setPauseMenuResponse(PAUSE_RESPONSE_RESUME_PRINT);` (auto-resume, no "purge
  more"), or map the paused page's Resume key to that call while the loop waits. Effort S.
- Test: T1 first. If T1 does NOT hang, find out why before touching it.

### LV-1 CRITICAL: first-layer and K tests print the purge before the stale-mesh check  [confirmed in code]
- `fl_poll` `FL_HOME` injects `... G1 X20 Y10 F5000, G1 Z0.3 F600, G1 E15 ...` (dgus_tft.cpp ~5134); `stale_gate(true)` only runs in `FL_PURGE`,
  AFTER the purge. After G28 the purge lowers to Z0.3 against a mesh that may be several mm stale (glass added: nozzle ~3 mm into the plate).
  The K pattern uses the same stages.
- Fix: run the gate straight after G28 and before any low move (lift Z10, gate, `M420 S1 Z0`, then purge). Effort S. Test T4.

### LV-2 CRITICAL: AUTO Z OFFSET lowers the nozzle with no stale-mesh check  [verified]
- `az_start_test(false)` runs G28 + `M48 P5`; on finish sets `z_need_check = false` ("mesh just made or passed the probe test"). M48 only measures
  repeatability; nothing compares with the mesh. Wizard step 1 only measures (safe). Fix: `z_need_check = !save_first`, or compare M48's mean with the
  centre node. Effort S. Test T5.

### LV-3 HIGH: the stale gate passes when a reading is missing (fails open)  [verified]
- `stale_gate()`: `if (sc_n < 2) { ... "no reading, skipped"; return 1; }`. A G30 that fails (early trigger above the clearance, strain-gauge false
  trigger, thick plate) prints no `Bed X:` line, so the gate passes exactly when it should refuse. Fix: treat `sc_n < 2` as -1 ("probe failed: redo mesh"),
  at most one retry. Effort S. Also parse the upstream G30 format `Bed X:%.2f Y:%.2f Z:%.3f` (no space after colons; bugfix-2.1.x changed it): see LV-U1.

### MC-12 HIGH: upstream thermal-protection gap fix missing (bugfix-2.1.x c27424fa, PR #28695, 2026-10-17)
- `temperature.cpp` `TRFirstHeating: if (current < running_temp) break;` and HeaterWatch arms only when `curr+INCREASE < tgt-HYST-1`: a thermistor that
  slips and reads 2-5 C under target leaves neither runaway nor watch active, heater at full power indefinitely. Fix: backport (~15 lines). Effort S.

### HW-2 HIGH: ~21.5 s watchdog, and nothing checks MAXTEMP while the main loop hangs
- `MarlinHAL.cpp:337-342` `WDT.begin(8000)` gives 21.5 s on this framework (only ~5.4 s or ~21.5 s possible with PCLK3 25 MHz). MAXTEMP/runaway
  checks run in main-loop code; `readings_ready()` in the ISR has no range check, so a hung main loop leaves the soft-PWM ISR driving the heater for
  up to 21.5 s. Also: the framework's `yield()` reloads the watchdog and `Usart::write()` spins on `yield()`, so a write with TX interrupts masked
  spins forever and the watchdog never fires.
- Fix: after HW-1 return to ~5.4 s (or set `F_PCLK3 = F_HCLK/16` for exactly 10.7 s); add an ISR-level dead-man (if `manage_heater` has not run for ~3 s,
  force `soft_pwm_amount` to 0); stop `yield()` reloading the watchdog. Effort S/M. Candidate cause of the open "random restarts" item.

### HW-3 HIGH: build depends on a locally modified framework; v62 ships a leftover diagnostic beep
- `~/.platformio/packages/framework-arduino-hc32f46x/cores/arduino/main/init.cpp` differs from the pristine 1.3.1 zip: a `DIAG-COREINIT` PB5 beep loop
  (4000 iterations) before VTOR/clock setup; confirmed present in the v62 ELF. Every boot beeps ~1-2 s and is delayed; a build on another machine
  gives a different binary. Fix: restore the pristine package; vendor it or pin by URL+hash; `build_release.py` hash-checks the framework and DDL
  packages and refuses `-dirty` builds. Effort S.

### MC-1/MC-2 MEDIUM-HIGH: Z offset can be changed without a re-home, and its range is not checked
- Z0 is shifted by `probe.offset.z` only at homing (`motion.cpp:2333`). M851 / babystepping `BABYSTEP_ZPROBE_OFFSET` change the offset without re-syncing
  the frame; G29 then stores `trigger + offset_new` taken in a frame shifted by `offset_old`: every node off by (new - old) (a negative delta pushes the
  nozzle into the bed). `Z_PROBE_OFFSET_RANGE_MIN/MAX` is +-20 mm: "M851 Z-3" is a 5 mm crash after the next home (hardware needs ~1.5-2.5).
- Fix: in M851 and `setProbeOffset_mm`, if Z is homed, `current_position.z -= (new-old); sync_plan_position();` (or mark Z never-homed so G29 refuses);
  set `Z_PROBE_OFFSET_RANGE_MIN 0`, `_MAX 4` and clamp in `setProbeOffset_mm`. Effort S. (Same family as LV-8.)

### MC-5 MEDIUM: power-loss resume homes Z over the bed, not off it
- `POWER_LOSS_ZHOME_POS { 0, 0 }` commented "front-left corner, as G28 does"; Z_SAFE_HOMING is off so G28 homes at (-6.2,-20.5) in front of the bed. At (0,0)
  the nozzle drops to the endstop plane, ~3-5 mm above the glass. Fix: `{ X_MIN_POS, Y_MIN_POS }`. Effort S.

### LV-4 HIGH: the bed-warm window can switch the heaters off in the middle of a job; the G29 soak then never ends  [verified]
- `bed_warm_until` (25 min) expiry calls `heaters_off_when_idle()`, whose only guard is `isPrinting()` (false during the G29 soak, between probes, FL_HEAT,
  the K-test M900 sync, the Z-page paper test). A 9x9 mesh + 10 min soak is ~45 min. If the window ends inside the soak loop, bed target goes to 0,
  `soak_since` to 0, and the `probe.cpp` loop `for(;;){ if (hot >= need || !wait_for_heatup) break; idle(); }` never ends (only M108/power cycle).
  Mid-probing the rest of the mesh is probed on a cooling bed.
- Fix: one `ac_job_active()` (probing, ol_run, fl_stage, az_stage, z_heat_wait, zoffset_moving, p5_busy, pages 17/119); use it in
  `heaters_off_when_idle()` and the expiry check; refresh the window while active; in `probe.cpp` break when `degTargetBed() < bed_temp - 5` and add a maximum wait (2x soak).
  Same finding from Marlin core (MC-8). Effort M.

### LV-5 HIGH: background jobs are not "busy"; two state machines can drive the nozzle at once  [verified]
- During `FL_HEAT` (heat + 10 min soak) the queue is empty, so `BlockedWhilePrinting()` and `!isPrinting()` let BED MESH, Z pages, 5-POINT, Move-page G28/jog
  start. The K-test page lets BACK leave while the test runs. PROGMEM injections replace each other's pointer (a purge `G28` vs `mesh_finish`'s M500),
  RAM-buffer fl rows interleave with a Z-page G30 sequence, and a background M500 can save a test K or unsaved 5-point corrections.
- Fix: `BlockedWhilePrinting()` and every flow-start check include `ac_job_active()` (shared with LV-4); K-test page BACK stops the test. Effort S/M.

### DR-3 HIGH: `printer_state` stays "stopping" after every finished print
- Timer stop sets `AC_printer_stopping`; only the "Print Aborted" message returns it to idle. Effects: the idle heater timeout (`printer_state != idle`) is off
  forever after the first completed print; the Main page jumps back to the print page whenever a command is queued. Fix: set idle in the page22/page29 OK handlers
  and in `onPrintDone()` (exists, empty). Effort S.

### HW-4 MEDIUM-HIGH: flash erase/program can stall the stepper ISR in the middle of a move
- `eeprom_flash_ab.cpp` guards only with `printingIsActive()`. Sector erase 16-20 ms, 1028-word program ~50 ms of 48 us stalls; code runs from flash so every ISR
  waits (lost steps, display/host UART overrun). Writes fire at M500 from a host stream, at print end while the park move is still queued (PrintCounter::saveStats),
  and right after `printingIsActive()` turns false. Fix: hold the write while `printingIsActive() || planner.has_blocks_queued() || stepper busy`; do not call
  `planner.synchronize()` inside `access_finish`. Plus HW-S1/S2 below. Effort S.

---------------------------------------------------------------------------------------------------------------------------------------

## 2. MEDIUM items

### Levelling / calibration (LV)
- **LV-6** `stale_gate()` XY-travels to its first probe at the current Z with leveling on (from Z1 at X20 Y13 in the first-layer test; with a stale +3.5 mm mesh clearance is
  1.5 mm or negative over up to 300 mm). Prefix `G1 Z10 F600` (worst case 61 characters, still fits 63) or adopt upstream's safe-Z travel (LV-U2). S.
- **LV-7** No floor on lowering: Z page checks `z_off <= -5` on the OFFSET not the nozzle height (can reach ~-4 mm = 4 mm into the glass); the 5-point page allows
  `p5_h` down to -1.5. Refuse a step when nozzle height would fall below about -0.3 mm (Z page) / -0.5 mm (5-point). S.
- **LV-8** Z-page SAVE keeps the babysteps and changes the offset without re-homing: until the next G28 logical Z0 is the start height (0.3-5 mm) BELOW paper. After SAVE
  undo the babysteps and inject `G28` (or shift `current_position.z`). S. Test T6.
- **LV-9** The outlier re-probe scans the PREVIOUS mesh: `StatusChange` reacts to "Kobra Max Ready." from G29.cpp:769, but the new mesh is copied in at line 804. Real spikes
  in the new mesh are never found; NAN nodes of the old mesh get flagged. Run `ol_scan()` from `ExtUI::onLevelingDone()` (empty today, anycubic_dgus_lcd.cpp). S.
- **LV-10/11** A new mesh on the AUTO Z path (`mesh_finish` returns at `az_start_test(true)` before the clean-up) or from a host/slicer G29 does not clear `p5_cum` / `wz_bits`;
  a later 5-point RESET subtracts old corrections (up to 0.3 mm) from the fresh mesh and saves it. Do the clean-up before the AZ branch and in `onLevelingDone()`
  (or store a mesh checksum next to `p5_cum`). S.
- **LV-12** 5-point readings above 0.3 mm are clamped in `p5_model` but `p5_total` (-1.5..+3.0) is added raw to `p5_cum` (saturates +-1.27): two sessions of +0.5 leave +0.3 in
  the mesh after RESET. Clamp the reading at STORE and warn, record what was applied. S.
- **LV-13** Stale-check margin shrinks after 5-point corrections (raw G30 compared with the CORRECTED node): compare against `mesh - p5_model(x,y,cum)`. S.
- **LV-14** First K-test line starts 1 mm under-primed (purge ends `G1 E-2`, line 0 puts back only `E1`): put back E2 on line 0 or end the purge with E-1. S.
- **LV-15** First outline side of each square runs at ~3x flow: `FL_RETRACT` (2 mm) is folded into a 24 mm side that should carry 0.94 mm. Put the filament back with a short slow move
  in place or over the first few mm only. (Possibly part of why squares clog; see the 2026-11-07 photos.) S.
- **LV-16** AUTO Z and wizard step 1 run M48 on a cold bed with the nozzle heating (spread includes thermal drift): use the `z_heat_wait`/soak gate and `nozzle_late()`. S.
- **LV-17** Smaller: `nozzle_late_temp` dropped after 25 min (a slow bed waits forever on "Heat 25/200" with no message); `p5_leave_check` leaves heaters on / `nozzle_late_temp` set;
  "Mesh drift" text shows 0.996 as "0.00"; `az_line` not reset when listening starts; the soak now applies to EVERY G29 incl. a slicer's start gcode (+10 min per print unless
  the bed was hot 10 min): make it an option; `probe.cpp:763/830` `return true;` in a float function (upstream bug too, dead with this config).

### Marlin core (MC)
- **MC-3** A probe that never triggers drives the nozzle to `-offset + Z_PROBE_LOW_POINT` = 10 mm below the endstop plane physically (bed is 4+ mm below it): 4-6 mm into glass at
  1.5-4 mm/s. PB6 has no pull resistor and triggers LOW, so an unplugged probe likely floats. Set the low point from the deepest mesh node minus ~1.5 mm (static -7 otherwise); test `M119`
  unplugged (T3); if open, consider `ENDSTOPPULLDOWN_ZMIN_PROBE` after checking the amplifier output is push-pull. S/M.
- **MC-4** Runout auto-polarity (port of stock V2.8.7) swallows the first runout of a session and permanently flips polarity to "pin HIGH = runout" regardless of `FIL_RUNOUT_STATE`
  (LOW configured). If the sensor is really LOW = no filament, a boot with filament loaded swallows the first runout, the print continues with no filament, and re-inserting
  filament fires a false M600. Confirm with M119 (T3), then set `FIL_RUNOUT_STATE` to the truth and replace the trick with "ignore runout until the first filament-present reading
  after boot"; the display's pin comparisons need the same change. M.
- **MC-6/HW-7** Power-loss detection needs 4 strictly falling raw samples below 2200 counts and runs only from `idle()`; `volts_raw` is not `volatile`; blocking calls delay it
  (HW-1 tunes). A fast collapse that flattens may never reach 4. Count samples below threshold (or below for >= N ms), evaluate in the temperature ISR (zero heater PWM, set a flag;
  `idle()` does the SD save), make `volts_raw` volatile. M.
- **MC-7** G30 leaves bed leveling off (upstream too) - matters here because the mesh holds absolute heights. Make G30 restore the previous state (as M48 does) and keep the display's
  explicit `M420 S1 Z0`. S.
- **MC-9** Boot window ignoring temperature faults uses raw `millis() < 5000` (reopens every 49.7 days); use a static flag. S.
- **MC-10** Every T change becomes M600, even idle/host: only convert while `printingIsActive()`. S.
- **MC-13** (LOW-MED) upstream 0746ec4b "watchdog reset while parking after thermal error" (#28645): NOZZLE_PARK_FEATURE is on. 3 lines. S.
- **MC-17** TMC addressing does not match hardware: E0 TMC2208 configured at `E0_SLAVE_ADDRESS 3`; X and E share address 0 (E settings land on X). Make config match (E0 address 0, identical X/E
  settings) or document. `LIN_ADVANCE` with `STEALTHCHOP_E` is a poor combination.
- **MC-18** `EEPROM_AUTO_INIT` silently resets mesh, E-steps, PID and offset on any layout/CRC change (v56 did): show a display message before restoring defaults.

### Display driver (DR)
- **DR-2** M600 can leave the UI on the print page with no way to continue: `activeFilamentChange` set at M600 start; first Resume tap clears it and goes to STATUS2 while Marlin is still
  parking; `wait_for_user` is then set but no Resume button exists; PAUSE then injects `M25 P / M24` behind the blocking M600 into PAGE_WAIT_PAUSE (no keys, no exit). It also clears
  `wait_for_heatup` from the UI (can cut heating waits short). Drive the page from Marlin's real wait state (`wait_for_user || pause_menu_response == WAIT_FOR`), Resume key
  maps to `setPauseMenuResponse` / `setUserConfirmed` / `resumePrint`; never touch `wait_for_heatup`. M.
- **DR-4** (suspected) the power-loss resume prompt probably never appears: the outage page is shown only inside the REG_LCD_READY handler if state is already "resuming"; `M1000S` replaces
  Startup's pending `M420 S1 V1`. In `PowerLossRecovery()` show the outage page if `lcd_boot_synced` is already set. S. Needs a hardware check.
- **DR-5** Print Settings BACK can apply an old Z offset (`static z_change/z_orig` survive leaving the page another way; next visit, possibly mid-print, BACK babysteps to the old value). Reset
  on page entry. S.
- **DR-6** An SD print can start during a host print or with commands queued (page2 case 6 has no `isPrinting()` check); folders are listed but never opened (PRINT on a folder runs M23/M24 on a
  directory and shows "Print finished"); `char file_index` wraps at 256 files. `BlockedWhilePrinting()`, skip dirs, `uint16_t`. S.
- **DR-7** Z-offset SAVE during a pause is lost: `inject_after_P` injects directly while paused, `M500` replaces the pending `M24`, Resume's M24 replaces `M500`. The same replace-the-pending-command
  problem exists at many direct `injectCommands_P` sites (page8 G28, `term_run_P`, `es_poll`, the M108s, page171/173, `FilamentRunout`). Make `inject_after_P` the only entry (hold while
  `injected_commands_P` is non-null), or call `settings.save()` directly. M. Long term: one UI command FIFO (DR-24).
- **DR-14** Soft endstops are switched off for the whole print (`setSoftEndstopState(false)`, a Chiron workaround; also set by host M109/M190 auto-start): out-of-range slicer moves can hit the frame. Remove. S.
- **DR-15** Filament macros: `MEL_cmnd_auto_unload_filament` runs absolute `G1 Z20` (drives into a taller part; assumes Z=0 when unhomed); `MEL_cmnd_auto_load_Filament` runs a full `G28` (probes the bed
  centre, hits a part left on the bed) and has no `G90`. Lift relatively / only if Z < 20; drop the G28. S.
- **DR-16** The Move page jogs unhomed axes (clamps to soft limits relative to the assumed power-on 0) and G28 keys only check `isMoving()`. Add `isAxisPositionKnown` + `commandsInQueue()` guards. S.

### Hardware layer (HW)
- **HW-5** Main stack is nominally 1 KB directly above an 8 KB heap, unbounded; ISRs (step 0, temp 2, UART 3) share it. DDL 2.2.2 cannot change it; upstream pins DDL 2.2.3 which adds
  `board_build.stack_size/heap_size`. Move to 2.2.3, set 0x4000/0x4000 (157 KB RAM above `__StackTop` is unused). Optionally stack-paint and show the high-water mark on About. S.
- **HW-6** SD card at 400 kHz for every transfer (`sdio.cpp:87`; stock uses 16 MHz high speed): ~40x slower, matters for the power-loss write and dense SD prints; `SDIO_READ_RETRIES 16 x 100 ms`
  can block 1.6 s per bad block. Use 20 MHz normal / 16 MHz high speed, 4-5 retries; test several cards. S.
- **HW-S1** The flash data cache is not reset after erase/program (`FRMC.CRST`): possible false "flash write FAILED" or stale settings until reboot. Toggle `EFM_DataCacheRstCmd` after `EFM_Lock()`. S (suspected).
- **HW-S2** Flash wear: 10,000 erase cycles per sector (~20,000 saves with A/B). Every `write_data` sets dirty, so every PrintCounter save and UI M500 erases a sector even with identical data. `memcmp`
  against the current copy (or per-byte change tracking, as upstream) and skip. S.

---------------------------------------------------------------------------------------------------------------------------------------

## 3. LOW items and improvements (batch)

- **DR-8** pages with no way out (page25, page27 key 2/1, Print Settings `return_to_print_page`) - add a fallback page. **DR-9** statistics `int16_t(filamentUsed/100)` overflow above 3.28 km - `int32_t`.
  **DR-10** validate `lcd_info` language/audio after load (a bad byte kills the UI dispatch). **DR-11** handle REG_LCD_READY only before sync. **DR-12** default error page for kills with no page
  ("Homing Failed", M112, "Killed"/TEMP_MALFUNCTION). **DR-13** unmatched status messages clear the runout flag; "Media Removed" only handled while printing. **DR-17** leave the Filament page with heaters off
  (`heaters_off_when_idle()` on BACK; hotend stays at 230 C otherwise). **DR-18** Filament STOP: use `quickstop_stepper()` not `queue.clear()` + `planner.quick_stop()`. **DR-19** blocking `delay(3000)`/`PlayTune`
  inside IdleLoop and callbacks during prints: `safe_delay`, honour the mute setting.
- **DR-20/21/22/23** upstream: implement `onPauseMode` if 2.1.3+ is merged; restore the backlight on Main (upstream #26261); `getLongPath` hard-codes 64 for caller buffers: pass the size.
- **DR-24** one command FIFO for all UI injections (removes the replace-the-pending-command class). **DR-25** delete dead code (SelectFile with `command_len - 5` underflow, InjectCommandandWait, Findcmndpos,
  FakeChangePageOfTFT, SendReadNumOfTxtToTFT, CheckHeaters, page177_to_198_handle, page14/31/32, FileNavigator changeDIR/upDIR/sendFile, movespeed, live_Zoffset, TXT_BASE64, undefined declarations).
  **DR-26** duplicate code (page171/173, page7 vs 207/209, time formatting x5, ChangePageOfTFT vs DevicePage). **DR-27** header: parenthesise `TXT_PRINT_NAME..COMMENT` (lines 201-205), comment the intentional VP aliases,
  fix the 175/176 CHS/ENG comments, fix the misleading `.enHwFlow` comment. **DR-28** clamp the display feedrate input (10-300). **DR-29** send display values only on change (page211 every 500 ms, Terminal 13 rows/s).
- **HW-8** restore the HRC-16 MHz check removed from `sysclock.cpp` (upstream panics if the bootloader selected 20 MHz: 250 MHz would exceed spec). **HW-9** analog-mode cache in `adc_enable` removes self-healing:
  check `getPinMode(pin) == INPUT_ANALOG`; skip `SET_INPUT` for PC2. **HW-10** `#error` in SanityCheck if `ENDSTOP_INTERRUPTS_FEATURE` is enabled (X_MIN PA6 and probe PB6 share EXTI line 6).
- **HW-S3** put `seq` and length under the CRC. **HW-S4** guard against the image growing into the settings sectors (linker `ASSERT` or `extra_scripts` check + upstream's runtime `eeprom_sector_free()`).
  **HW-S5** bounds-check `read_data/write_data` (`settings.cpp:603` static_assert is commented out). **HW-S6** document: a save during a print lives in RAM until the print ends; UI reports success.
  **HW-S7** test whether the bootloader erases past the file size (T8); make the flash bus-hold assumption explicit (`EFM_SetBusState` or critical section, as upstream).
- **HW-I** improvements: hardware FPU (firmware is soft-float, 352 `__aeabi_fmul` call sites; needs framework + libs consistently, M); UART reliability (`UART_RX_IRQ_PRIO 1`, or DMA for the display port, `SERIAL_BUFFER_SIZE 256`);
  `build_release.py check_firmware_bin`: SP must equal `__StackTop`, all non-zero core vectors odd and inside 0x8000-0x3C000; remove the unused `MSerial3`; print raw RMU reset flags at boot (HW-1/2/5 are candidates for the open
  "random restarts"); `STEPPER_TIMER_TICKS_PER_US` is 3 but really 3.125; fix `platformio.ini` part-number comments (KCTA 256 K vs 512 K) and confirm which part is fitted.
- **MC-11** `DEBUG_POWER_LOSS_RECOVERY` also enables `M413 O` (a simulated outage that kills the print): off before a general release. **MC-19/20** dead/misleading config (`Z_MULTI_ENDSTOPS`, Z2/E1 on the same pins,
  `ANYCUBIC_LCD_DEBUG`/`TMC_DEBUG` cost flash at 88 %); confirm `HEATER_0_MAXTEMP 275` (260 C target: only for an all-metal hotend), `DEFAULT_STEPPER_TIMEOUT_SEC 0`, consider `HOTEND_IDLE_TIMEOUT`.
  **MC-15** align the custom soak with upstream `LEVELING_HEAT_SOAK_TIME` (#28520); `PLR_HEAT_BED_ON_REBOOT` (#26691) keeps a 400x400 part stuck while deciding to resume. **MC-22** (M/L, design) normalise the mesh: subtract a reference
  node into M206/home offset so the mesh holds sub-mm values (fade becomes usable, invalid mesh is no longer a multi-mm error, MC-1/MC-2/MC-7 mostly disappear; upstream recommends this for this design in #27680).
- **Upstream backports/PRs:** bugfix-2.1.x c27424fa (MC-12), 0746ec4b (MC-13), fd343a61 #28675 G30 requires homing, #25652 (G28/G30 return when probe deploy fails), `probe_at_point` safe-Z travel (LV-U2). From PR #28448 (Kobra Max beta port):
  adopt the dirty-only write, the `eeprom_sector_free()` check and `isr_off()`/`PAUSE_SERVO_OUTPUT` around erase; do NOT adopt its single-sector no-CRC store, its `BOARD_XTAL_FREQUENCY 16000000` (stock BSP says 8 MHz), its `IIC_BL24CXX_EEPROM`
  on PB7/PB6 (the probe pins) or its env comment "PETB 256K". Local fixes that upstream lacks and could be sent as PRs (after showing the texts to the owner): `HAL_timer_interrupt_enabled` inverted upstream, emergency-parser port filter,
  `SDIO_GetCardSize` `_MAX` vs `_MIN`, SDIO handle leak on init failure, SanityCheck checks `PANIC_USART3` twice, `set_pwm_duty` invert underflow.
- **LV-U1** upstream G30 report format changed (`Bed X:%.2f Y:%.2f Z:%.3f`); `term_rx_hook` matches `" Z: "`: after a rebase the gate would silently stop working (combined with LV-3 fail-open). Parse `"Z:"` and skip spaces.

---------------------------------------------------------------------------------------------------------------------------------------

## 4. Tools, release packaging and documentation (TL)

- **TL-1 HIGH** the repo cannot rebuild a display set: `.gitignore:34 *.bin` ignores `DWIN_SET/14ShowFile.base.bin`, `13TouchFile.base.bin`, `22_Config.base.bin`, `DWINOS.bin`; they exist only on this PC. Add `!DWIN_SET/*.base.bin`, `!DWIN_SET/DWINOS.bin`,
  commit them; make missing required files fatal in `build_release.py` (today only a "WARNING ... skipping").
- **TL-2 HIGH** a failed script-ICL build leaves a release folder that looks complete but holds the stale July IDE library (copy loop copies `DWIN_SET/16_68_.icl` first; exit on failure keeps the folder). Assemble into `<out>.tmp`, rename only after all
  checks pass, delete on failure, never copy `16_68_.icl` in script mode.
- **TL-3 HIGH** the IDE (non-script) path ships no `33_SPIN.icl`/`34_SEL.icl` although the show file points at them (garbage spinners, no highlights), and README STEP 0 says to save the spinner as `29_SPIN.icl` (would overwrite the icon library).
  Always build/ship 33/34 or fail; fix the text; add `--bmps-only` instead of recommending `--allow-stale-icl`.
- **TL-4 MEDIUM** `22_Config.bin` (131 KB) lands inside the picture library (slots 16-28): pictures 110-114, 117, 119 (boot frames, System audio-off, the 5-POINT page) sit in that range; `T5LCFG.CFG` byte 0x05 = 0x1B so the 22 file is never loaded;
  `check_icl.py` skips `.bin` in the overlap check. Stop shipping it or check fixed `.bin` slots (12/13/14/22) against an allow-list. (DISPLAY_NOTES:501 "22_Config regenerated -> display would not boot" is probably misattributed.)
- **TL-5 MEDIUM** mesh page 208 now has 85 display records (81 cells + 2 info + 2 status bar), above the guide's 64-per-page base mode (it was 53 before v56): bottom rows/info lines may not draw. Test T7; add an assert in `patch_14showfile.py` (warn > 64, fail > 128).
- **TL-6 MEDIUM** tool failures pass as success (`generate_screens.py` exits 0 after per-page exceptions; `patch_14showfile.py` prints "*** SOME CHECKS FAILED ***" and exits 0; `run_tool` shows only the last stdout line). `sys.exit(1)` on any error.
- **TL-7 MEDIUM** `--out` can delete the source tree (`shutil.rmtree` with no guard: `--out .` or `--out DWIN_SET`), and the default `release/` overwrite wipes the documented "last known-good set". Refuse anything but a new `release*` folder under the repo; make `--out` mandatory.
- **TL-8 MEDIUM** art depends on the fonts of this PC with a silent fallback to `ImageFont.load_default()` (`generate_screens.py:56-81`): put the TTFs in `tools/fonts`, fail if missing, pin Pillow (requirements.txt).
- **TL-9 MEDIUM** `check_icl.py` cannot see small text changes (thresholds PIXEL_TOL 60 / DIFF_PIXELS_MAX 120: "0.3 mm"->"0.5 mm", "190 C"->"180 C", "30 min"->"60 min" all pass as "current"): compare per 8x8 block, or store a hash of the source BMPs next to the library. M.
- **TL-10** a release cannot be traced to a commit (README always "-dirty" because the tagged About BMPs are rewritten before `git_info`; `git checkout -- DWIN_SET/013.bmp 133.bmp` only on success and can revert legitimate uncommitted About changes):
  render tagged About pages into a temp folder, warn/refuse on a dirty tree, same id in README/About/folder name.
- **TL-11** `check_release` skips every `.icl` and warns only on the renamed font; `NEW_COUNT = 218` is hard-coded in `patch_14showfile.py` (derive max(page)+1); stale artefacts next to the sources (`DWIN_SET/34_BootAnim.icl` tracked in slot 34, `auto_icl/32_SPIN.icl`,
  `33_SEL.icl`, `14ShowFile.bin.bak`, unrenamed 23_ICO/24_Font); one-off scripts with absolute paths that rewrite `dgus_tft.cpp` (`fix_mpc_save.py`, `fix_null_terminators.py`, `patch_page216.py`, `fix_eng_pages_and_term.py`; `generate_boot_animation.py` defaults to `C:\temp\boot_anim`) -> archive;
  `build_release.py` does not `chdir` to the repo root.
- **TL-12** stock pages 120 and 134 (unreachable) still have 7 text records using Font1_ID 24 / slot-23 icons: patch them to `[]`/STATUS_BAR. **TL-13** handler cases with no button (page2 case 5, page3/4 case 1, pages 21/22/26/29 case 2, page8 14/15/16): `cross_check` only checks zone -> case. **TL-14**
  strings name a removed button ("No mesh: run AUTO BED LEVEL" at ~4810 and ~1426; the button is "BED MESH"). **TL-15** `generate_dwin_controls.py` Move Axes comments say 0.1/1/10 mm (firmware/art: 1/10/50) and end up in `tools/DWIN_CONTROLS_README.md`.
  **TL-16** more cross-checks: shared constants (WZ_N, wizard key map, KEY_ADDRESS layout), VP window sizes vs the firmware's `char buf[N]` (derive each window from the next VP).
- **TL-17 HIGH (user safety)** generated `README.txt` (build_release.py:363-460) contradicts itself and the firmware: "same SD card" vs "separate card"; says settings are in `eeprom.dat` (they are in chip flash since v52, eeprom.dat only taken over once); no mention that firmware.bin is renamed to
  `firmware.cur` after boot (v62) or how to flash the same file again; expects ".ICL 2 or 3" (a script set has 4: 16, 29, 33, 34); "Power OFF" without the 15-20 s wait. DISPLAY_NOTES 3.7 repeats the eeprom.dat and ".ICL 2" text.
- **TL-18** `docs/SETUP.md` is stale against v53-v62: wizard order (now 1 PROBE CHECK, 2 BED MESH, 3 Z OFFSET, 4 5-POINT, 5 FIRST LAYER), menu names (BED MESH, MANUAL Z OFFSET), mesh "7x7 several minutes" (9x9, 45-60 min + 10 min soak), "BACK LEFT" (REAR LEFT), 0.3 mm threshold (0.5),
  "settings vanish: check the SD card" and "first boot resets all settings" (flash settings), step numbering, no mention of K TEST.
- **TL-19** `DISPLAY_NOTES.md`, `README.md`, `ui_features.py` describe the 2.0.8 era (M115 "2.0.8-hc32", `HAS_M1024`, "9 slots" (13), pressed pictures "35-84" (35-49 + 218-251), "143 BMPs" (201), `make_process_bar_record` (gone), boot frames "in 34_BootAnim.icl" (now inside 16_68_), 13/14/22 in a "configuration area"
  (fixed slots 13/14/22), IDE path as default, "ID 32 = slot 32" (33), wizard "from the main page" (System page)).
- **TL-20** reproducibility/CI: commit base binaries + fonts, pin Pillow, refuse dirty release builds, build twice and compare sha256 of the whole DWIN_SET; GitHub Actions (windows-latest): generators, `cross_check_display.py`, `build_icl.py --selftest`, library build+verify, flash-slot check including fixed `.bin` slots and the 256 KB limit for 13/14,
  records-per-page asserts, picture-library headroom report (~95 KB left below 3,407,872 bytes = ~2-4 pictures before slot 29), `git diff --exit-code DWIN_SET/*.bmp`; second job `pio run` + vector-table check.
- **TL-21** make the display set self-identifying: a release id in a hidden show-file record/VP that the firmware reads back at boot and compares ("display set vN != firmware vM"); today only the About page protects against key renumbering (v49, v54) in a mixed set.

---------------------------------------------------------------------------------------------------------------------------------------

## 5. Work order

Each step is its own release; hardware tests T1-T9 gate steps 1-2. Nothing is built or flashed without the owner's go.

**Step 0 (no code): run T1-T9** and record results in `docs/OPEN_ITEMS.md`. T2 and T1 decide how urgent HW-1 and DR-1 are.

**Step 1: safety hotfix (v63).** HW-1 (non-blocking tone), HW-3 (pristine framework + hash check), DR-1 (answer the purge prompt), LV-1, LV-2, LV-3 (+LV-U1 parse), MC-12 (thermal gap), MC-5 (power-loss home position),
MC-1/MC-2 (offset range + re-sync), LV-8. All small; each with its own hardware test.

**Step 2: stability (v64).** HW-2 (watchdog + dead-man), HW-4 + HW-S1 + HW-S2 (flash write gating, cache flush, skip identical), LV-4 + LV-5 (`ac_job_active()`), MC-8 (soak loop exit), DR-3, DR-2, DR-15, DR-16, DR-14, LV-6, LV-7, HW-5 (DDL 2.2.3 stack).

**Step 3: correctness (v65).** LV-9..LV-17, DR-4..DR-7, MC-3, MC-4 (after M119), MC-6/HW-7, MC-7, MC-9, MC-10, MC-17, MC-18, HW-6.

**Step 4: tools/release (parallel, no printer needed).** TL-1, TL-2, TL-3, TL-6, TL-7, TL-17 first (they can silently produce or lose a display set); then TL-4..TL-5, TL-8..TL-16, TL-18/19 (docs), TL-20/21 (CI, id check).

**Step 5: refactors and upstream hygiene.** DR-24..DR-29, MC-22 (mesh normalisation: design decision), HW-I (FPU, UART priorities), upstream PRs (texts shown to the owner first), merge 2.1.2.10 when released (vendor-deletion check + offset re-test first).

### Decisions needed from the owner
1. DR-1 auto-resume (no "purge more" prompt) is acceptable? 2. MC-22 normalise the mesh into a home offset (bigger change, fixes a class of bugs) or keep absolute meshes and add the guards? 3. Soak only for display-started G29, or for every G29 incl. slicer start G-code (LV-17)?
4. Keep `DEBUG_POWER_LOSS_RECOVERY` (M413 O) until power loss is proven, or disable now? 5. Runout sensor polarity (after M119): which is the real level? 6. Which MCU part is fitted (KCTA 256 K or 512 K)? 7. OK to commit the base `.bin` files and fonts to git (TL-1, TL-8)?
8. Upstream reports/PRs: show texts first, as agreed earlier.

### Not to do
- Do not adopt upstream's single-sector no-CRC settings store (weaker than the local A/B scheme), its 16 MHz crystal claim, or its I2C EEPROM on the probe pins.
- Do not fix the above by raising the watchdog or hiding symptoms; fix HW-1 first.
- Do not change anything in the squares/K-test geometry (v61/v59) until the owner reports the v61 print, except LV-14/LV-15 which are bugs in the same code.
