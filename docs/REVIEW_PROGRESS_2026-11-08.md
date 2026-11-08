# Review plan: what was done (2026-11-08, release_v63)

Companion to `REVIEW_PLAN_2026-11-08.md`. Everything below is in the source and in `release_v63`; NOTHING has been run on the printer. Flash use 90.1 %
(191,948 of 212,992 bytes, about 21 KB left). The item IDs are the plan's.

Work was done in three streams: the hardware layer and Marlin core (branch `review/hw-mc`), tools / release / docs (branch `review/tools`) and the
display driver and levelling code (this branch). Both side branches are merged.

## Test on the printer first (plan section 0, T1-T9) and after flashing v63
The fixes below change behaviour that was never observed on hardware. In this order, heaters cold where noted:
1. Boot: no watchdog reset loop, no leftover beep, the power-on tune plays once at normal speed (the tone code no longer blocks; tunes are now about half as long as before).
2. `M300 S440 P200` (heaters off): returns at once, no freeze.
3. SD print, PAUSE, RESUME, and an `M600` in a file: after the purge the print must carry on by itself.
4. A glass plate (or a 3 mm shim) added after the mesh: first-layer test and AUTO Z OFFSET must REFUSE before lowering ("Mesh off by x.xx mm").
5. 9x9 mesh with the heat soak: the heaters stay on for the whole run (the warm window renews itself); then the outlier check should look at the NEW mesh.
6. Z page: lowering stops 0.3 mm under paper; SAVE re-homes Z; 5-point RESET after two sessions.
7. SD card at 12.5 MHz: M20, a large print, a power-loss save; if anything fails put `SdiocClk400K` back (`HAL/HC32/sdio.cpp`).
8. M500 twice with nothing changed ("settings unchanged"); M500 during a print ("held"), the About counter.
9. Flash the display set (no `22_Config.bin` any more: the blue screen should read `.ICL 4`, `.BIN 3`) and look at the 9x9 mesh page (85 records).
10. M119 with filament in/out and with the probe cable unplugged (runout polarity, MC-4, MC-3).

## Done
**Levelling / calibration (LV):** LV-1 gate before the purge; LV-2 AUTO Z checks the mesh; LV-3 gate fails closed (retry once, then refuses; text "No probe reading: redo") and LV-U1 parses both
G30 report formats; LV-4 / LV-5 `ac_job_active()` (bed-warm window renews during a job, `BlockedWhilePrinting()` refuses a second flow, K-test BACK stops the test; the soak-loop exit is MC-8);
LV-6 lift before the first stale-check probe; LV-7 lowering floors (Z page -0.3 mm, 5-point -0.5 mm); LV-8 Z-page SAVE homes Z again; LV-9 outlier scan and mesh save wait for `onLevelingDone`;
LV-10 / LV-11 `mesh_changed()` for every G29; LV-12 5-point readings limited to +-0.3 mm with a message and RESET removes the unlimited sum; LV-13 stale check compares with the mesh minus saved
corrections; LV-14 K-test first line re-primed with 2 mm; LV-15 unretract spread over two outline sides; LV-16 M48 waits for the temperatures; LV-17 partly (line buffer reset, drift text).
**Display driver (DR):** DR-1 the resume / M600 purge prompt is answered (`setPauseMenuResponse`); DR-2 M600 page logic (flag cleared by M600 itself, Resume answers what M600 waits for, back to the print
page afterwards); DR-3 state back to idle after the finish pages; DR-4 outage page shown whenever recovery is detected; DR-5 Print Settings BACK no longer undoes an old change; DR-6 print start refused during
host prints / jobs, folders refused, 16-bit file index; DR-7 pause-safe injection holding; DR-8 pages 25 / 27 have a way out; DR-9 statistics overflow; DR-10 settings validated on load; DR-15 filament
macros lift only when Z is homed and below 20 mm, no G28; DR-16 Move page guards; DR-17 Filament BACK cools; DR-18 quickstop; DR-27 VP macros parenthesised; DR-28 speed input clamp; TL-14 strings.
**Hardware layer and core (HW / MC, see the branch log for details):** HW-1 non-blocking tone; HW-2 watchdog 10.7 s, no `yield()` reload, heater dead-man in the temperature ISR; HW-4 flash writes held while the
printer moves; HW-5 DDL 2.2.3 with 16 KB stack and heap; HW-6 SD 12.5 MHz (untested); HW-7 / MC-6 outage detection in the temperature ISR; HW-8, HW-9, HW-10; HW-S1..S6; HW-I (no MSerial3, reset flags
printed at boot); MC-1 (M851 only), MC-2 (range -6..6), MC-3 (dynamic low point 2 mm under the lowest mesh node), MC-5, MC-7 (G30 restores the leveling state), MC-8, MC-9, MC-10, MC-12 (upstream
c27424fa), MC-13, G30 requires homing, MC-23 comments; HW-3 the diagnostic beep is out of the local PlatformIO package (verified identical to upstream 1.3.1) and the package hashes are recorded.
**Tools / release / docs (TL):** TL-1..TL-13, TL-15..TL-20, HW-I3 and the HW-3 hash check (see `git log review/tools`): base files tracked, atomic release folder, `--out` guard, hard errors, font requirement,
source-hash check for libraries, tagged About pages in a temp folder, exact file-set check, rewritten README / SETUP / DISPLAY_NOTES, CI workflow (never run on GitHub).

## Not done (and why)
- **DR-11** (REG_LCD_READY only before sync): a display restart sends the same report and needs the page redraw; the two cannot be told apart. **DR-12** (default error page for kills): needs new display art.
  **DR-13** (runout flag cleared by unmatched messages) and **DR-14** (soft endstops switched off during prints): inherited upstream behaviour, changing it needs a test on the printer first.
  **DR-19** (blocking delays / tunes in callbacks), **DR-20..23**, **DR-24** (one UI command FIFO), **DR-25 / DR-26** (dead and duplicate code, the 8 dead handler cases cross_check warns about),
  **DR-29** (send display values only on change): refactors, not done, no behaviour risk in leaving them.
- **LV-17** rest: `nozzle_late_temp` timeout message, `p5_leave_check` leaving heaters on, the soak for every G29 (decision 3 in the plan), `probe.cpp` `return true` in a float function (upstream bug).
- **MC-4** runout polarity (needs M119), **MC-11** `M413 O` debug (kept on until power loss is proven), **MC-17** E0 address (documented only, check with M122), **MC-18** message before defaults are restored,
  **MC-22** mesh normalisation, the static -7 low point, `ENDSTOPPULLDOWN_ZMIN_PROBE`, FPU, UART IRQ priorities, **TL-21** (display release id read back by the firmware).

## Decisions still open (plan section 5)
Soak for every G29 or only the display's; keep absolute meshes or normalise; runout polarity after M119; which MCU part is fitted (256 K or 512 K); posting the upstream reports (texts first).

## Follow-up, release_v64 (same day, after the owner's answers)
Done: the soak only for G29 started from the display menu (LV-17); MC-22 mesh normalisation; DR-12 halted page; DR-24 one injection FIFO; DR-19 background tunes and no delay(3000); DR-25 / DR-26 dead and duplicate code;
LV-17 leftovers (late-nozzle timeout message, 5-point heaters, `run_z_probe` tare failure returned 1.0 mm).
Not done, on purpose: DR-14 (soft endstops stay off during prints: remove after the normalised mesh is proven), DR-29 (the 500 ms resend repairs text the display dropped at a redraw).
Still open: DR-11, DR-13, DR-20..23, MC-4 (needs the M119 readings), MC-11, MC-17, MC-18, the static Z_PROBE_LOW_POINT (needs the measured bed depth: M206 Z after a normalised mesh), ENDSTOPPULLDOWN_ZMIN_PROBE, FPU, UART priorities, TL-21.
