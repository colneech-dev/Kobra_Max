> **HISTORICAL.** Written during development (see the file name and the release it mentions) and not maintained. For the current state read the [README](../../README.md), [MANUAL](../MANUAL.md) and [SETUP](../SETUP.md).

# Open items (updated 2026-11-08, after release_v62)

The full history of decisions and results is in `PLAN_REVIEW_2026-10-31.md`. This file is only what is still open.

## Needs the printer (nothing here can be done by changing code)
1. **v50 first run**: flash the display files AND `firmware.bin` of the same release (power off 15-20 s first). Check About, `M119`, then
   the wizard: mesh, Z offset, 5-POINT Z, first layer test. Watch the stale-mesh check and the corner page on a good mesh (it must pass).
2. **5-POINT Z**: the smooth correction (tilt, twist, bowl, limit 0.3 mm) has never run. Try it on the left corners; run the squares after.
3. **Thermal protection** was tightened to Marlin's default (hotend 40 s / 4 C, was 10 s / 10 C). Watch the first real prints; if a
   part-cooling fan causes false "thermal runaway" errors, set `THERMAL_PROTECTION_PERIOD` / `_HYSTERESIS` back (Configuration_adv.h).
4. **Power loss**: `M413 O` during a print and resume; then a real power pull; then a long print with bed and hotend at full power, watching
   for false triggers. `DEBUG_POWER_LOSS_RECOVERY` stays on until this is proven (powerloss.h).
5. **Linear advance** (K above 0) with the extruder: X and E share driver address 0, so only both-stealthChop or both-spreadCycle exist.
6. Boot tune, mesh viewer legibility, E-steps and K pages, AUTO Z limits (0.03 / 0.08 mm are guesses): confirm or tune.

## Decisions waiting for the owner
- Push `kobra-max-hc32-2.1` (about 25 commits exist only on this PC; agreed: after Phases 1-4).
- Phase 2 (settings in the chip's flash, two-sector, power-safe), Phase 3 (thumbnail preview), Phase 4 (reports to Marlin: texts shown first).
- Whether host prints without a mesh should be refused (today: serial warning only).

## Known limits
- Host prints (OctoPrint / USB) are not stopped when no mesh exists.
- The Terminal wraps long replies over two rows; it still shows only 13 rows.
- A bed surface change needs a new mesh AND a new Z offset (the stale check catches it before the nozzle goes down, not in a print).

## v51 (2026-11-03)
- Fixed: first layer test stopped after the clearing line and parked at back centre. Cause: the stale-mesh check (G30 at the centre) leaves the bed mesh OFF (G30 never re-enables it). v51 sends M420 S1 Z0 after the check (first layer test, Z page, 5-point page, test tail). Threshold 0.3 -> 0.5 mm; message now shows the measured difference ("mesh off 0.62 mm"). Untested on hardware.

## Levelling review (2026-11-04, plan only, nothing changed)
Evidence-based leads for the "front squares drag" fault (last two squares printed, both front, pattern moves between runs):
1. No heat soak. G29 preheats only to 190/60 and starts at once (Probe::preheat_for_probing waits for the setpoint, nothing more); the
   mesh takes ~18 min (estimate: 49 points x 4 probes), front row FIRST. The first-layer test then starts at bed 58 C after a few minutes,
   with the glass not soaked (the wizard switches the heaters off after the mesh). Early (front) nodes were probed on a cooler bed than
   the one printed on. Test: G30 at the front-left node after a 10 min soak versus that mesh node.
2. The strain probe measures with force: the lag (2.3 mm without glass, 1.8 mm with) changed by 0.44 mm with a stiffer bed, so part of it
   is bed/gantry compliance, which differs by position. Paper (zero force) is the only ground truth: a denser mesh does not remove it.
3. The stale check only compares the centre node (probed mid-run, so thermal drift hardly shows there) and only refuses above 0.5 mm.
Improvements, ranked: heat soak (timed, bed stays on between wizard steps); stale check at the first-probed corner + show the number
always; mesh outlier check after G29 (node versus neighbour mean) with automatic re-probe; DELAY_BEFORE_PROBING 200 (tare happens
400 ms after arrival while the bed may still ring); slower final approach if lag depends on speed; 3x3 paper grid instead of 4 corners
(9 points); UBL only if all of these fail (flash 85.6 %). 9x9 only if two meshes agree and the shape has structure under 120 mm.

## Settings in flash (Phase 2, built 2026-11-04 as v52, UNTESTED on hardware)
Mesh, Z offset and all settings are now stored in the chip flash (sectors 0x3C000 / 0x3E000, header + CRC32, newest valid copy wins,
the other sector is written on each save). An existing eeprom.dat on the SD card is taken over once. Saves during a print are held
until the print ends (erasing stalls the CPU). Test order: (1) M500 in the Terminal: expect "EEPROM: saved to flash"; (2) power off 15 s, on,
M420 V1 / M503: mesh and M851 still there with the SD card REMOVED; (3) first boot after flashing with the old card in: expect
"settings taken over from the SD card file"; (4) M500 during an SD print: expect "held until the print is over". If a flash write
FAILS (message "flash write FAILED") the sectors may be write-protected by the bootloader: tell me, nothing is lost (previous copy kept).
Unknown until tested: whether the bootloader protects 0x3C000-0x3FFFF; whether flash erase upsets the display link (a touch may be lost).

## v53 (2026-11-05, UNTESTED on hardware): levelling batch from the 2026-11-04 review
- Heat soak: LEVELING_SOAK_SECONDS 600 (Configuration.h). G29 waits inside its preheat (probe.cpp; Terminal shows "Heat soak: n s left", M108 skips; the
  display shows the Preheating page and has no cancel button); the Z-offset page, the 5-point page and the first layer test wait with a countdown in
  their status line (BACK leaves / STOP). A bed that has been hot 10 min without a break does not wait again. The bed stays on for 25 min between
  steps of one job (bed_warm), so the wizard soaks once; the idle timeout / window expiry switches it off.
- Stale check now probes the front-left node (first one G29 probes) AND the centre, prints "Mesh check: front-left x mm, centre y mm" in the Terminal
  every time, and the first layer test shows "Mesh drift f0.12 c0.03" while it starts. Still refuses above 0.5 mm.
- Outlier check after G29: nodes more than 0.25 mm from the mean of their neighbours (worst 4) are probed again; a node that differs by more than
  0.08 mm from its first reading is replaced, otherwise kept (real bump). Wizard says "Mesh saved, n re-probed". Adds ~25 s per odd node.
- PROBE_SETTLE_MS 250: pause after the XY move before the probe is tared (DELAY_BEFORE_PROBING does nothing here: it needs quiet probing).
- About page: the SUPPORT line alternates build id / "Cfg flash #N A" (save counter and sector), "Cfg FLASH SAVE FAILED", "Cfg held until print".
- First layer test: FL_AHEAD 6 -> 12 planner blocks (BLOCK_BUFFER_SIZE 16).
Watch: the soak adds 10 min to the first G29 of a cold bed; false outlier hits on a real glass-edge bump (check the Terminal lines); the Z/5-point pages
refusing nothing but now waiting before lowering.

## v54 (2026-11-05, UNTESTED on hardware): button review + SKIP SOAK
Negative review of every page's buttons (touch zone vs drawn button vs handler: all matched except the overhangs below). All findings fixed:
- SKIP SOAK: a button on the G29 Preheating page (175/176, "SKIP HEAT SOAK"), the Z offset page and the 5-point page (footer middle) and the wizard
  (footer right, ends the first layer test's soak). It sets the start of the soak back (soak_skip(): every waiter reads ac_bed_hot_ms()), also when tapped
  while the bed is still heating (it counts once hot). Heating itself is never skipped. Status line says "Soak skipped" / "Soak is over" / "Bed is off: no soak".
- Every way into a mesh run (BED MESH, MANUAL / AUTO Z OFFSET with no mesh) now asks first on page 33/153 ("Takes up to 30 minutes", BACK / START MESH);
  that page was unreachable before (FIX_MOUNTED_PROBE only).
- Filament STOP ends a running sequence: queue and injected lines dropped, an extruder-only move is quick-stopped (never a move of X/Y/Z), M82 / G92 E0 / M84
  afterwards. Status text said 10 mm for the 30 mm EXTRUDE.
- Pages 9 / 10: SET removed (it was BACK). Print Settings: row label "Z-OFFSET (mm)  SAVE keeps" (BACK only undoes the Z offset; temperatures, speed, fan are live).
- Terminal: M502 RESET replaced by M503 SHOW (M502 wiped the mesh in RAM, next to M500 SAVE, no confirm). M502 can still be typed on the keyboard.
- Wizard order: 1 PROBE CHECK, 2 BED MESH, 3 Z OFFSET, 4 5-POINT, 5 FIRST LAYER. Touch key of a step = 2 + its number; WZ_ constants renumbered (literals fixed).
- Leveling menu: BED MESH, VIEW BED MESH, AUTO Z OFFSET, MANUAL Z OFFSET, start height row (belongs to the two above), 5-POINT Z. Same names as the wizard.
- Cancel / failure of a mesh run that started in the wizard goes back to the wizard (pages 201, 203, 187/188/199/200 via wz_back()).
- 5-point corners are REAR LEFT / REAR RIGHT / FRONT ..., the mesh viewer says "REAR of the bed" (BACK is only the footer button).
- File browser: RESUME button removed (power loss has its own pop-up 171/173), PRINT with no file tapped says "SELECT A FILE FIRST".
- MOTORS OFF (Tools, both variants) refuses during a print. Page 214 (thumbnail, unreachable) hidden. Move Axes / temp / speed + zones now as wide as their buttons.
- tools/DWIN_CONTROLS_README.md regenerated (was stale).
Not changed: the wizard does not force the Z offset before the 5-point step (the 5-point maths assumes the centre reads 0.00 after the normal offset: do step 3 first).
Test: Preheating page SKIP HEAT SOAK on a cold bed (the Terminal should stop printing "Heat soak"); the same on the Z page; BED MESH from the menu shows the confirm page;
Filament LOAD then STOP mid-feed (the extruder should stop within a second); wizard order and that each step's status line sits under its own button.

## v55-v62 (2026-11-06 to 2026-11-08, ALL UNTESTED on hardware unless noted; the user ran v59 on the printer)
- v55: the mesh stale check and the outlier re-probe lift the nozzle (Z10) after every G30 (it dragged across the bed between nodes).
- v56: 9x9 mesh (81 probes, about 45-60 min), final probe approach 90 mm/min, multi-probe clearance 3, mesh viewer 28 px cells at VP 0x3400, confirm page says 60 minutes. A grid-size change makes old saved settings reject (defaults): redo the mesh. Fade height stays 0 (refused on purpose).
- v57: 5-point Z: a corner is measured against the mesh as it was when the page opened and STORE replaces its value (it stacked on the earlier one).
- v58: the nozzle heats only for the last 4 minutes of the heat soak (G29, Z pages, 5-point, first layer test): LEVELING_NOZZLE_LEAD_SECONDS 240.
- v59: K pattern test on the Linear Advance page (K TEST + SKIP SOAK): 11 lines, K 0.0-1.0 step 0.1 (or K +-0.10 step 0.02 when a K is entered); two wall lines on the first layer squares.
- v60: the wizard lights the first step not done (orange overlay icon, library 34 ids 3-7); finished steps are remembered in the settings ("Done (saved earlier)"); a new mesh clears the 5-point and first layer steps; 5-POINT page RESET button removes every saved correction from the mesh (needs 34_SEL.icl: flash the display set).
- v61: first layer squares: 5 % more flow, 0.18 mm layer, 2 mm retract + 3 mm wipe, mesh check probes in front of the centre (a hot nozzle touching the bed at the centre left a blob under the first square). Watch: gaps between rows closed? strings gone? nozzle clean (if it clogs, set Z to 0.19)?
- v62: firmware.bin on the card in the front slot is renamed to firmware.cur once the new firmware has booted (once per boot, only with the card in at power-up), so the bootloader does not flash it again.
- Not possible in firmware: a built-in CaliCat print (flash is 88 % full, about 25 KB left; the G-code is megabytes). A pre-sliced file for the SD card would work.

## v64 (2026-11-08, built from the review follow-up; ALL UNTESTED on hardware)
- Heat soak only for the display's own mesh run (BED MESH in the menus, wizard, first layer test, AUTO Z): `ac_soak_take()` in probe.cpp; a G29 from a slicer start G-code or the Terminal heats and waits for the temperatures only.
- MC-22 mesh normalised (`MESH_NORMALIZE_TO_HOME_OFFSET`, Configuration.h): after every G29 the mean node height is moved into the Z home offset (M206 Z, saved by M500). Nodes are small deviations; the bed is at `node - home_offset.z`.
  Soft Z minimum follows the home offset, the probe's dynamic low point and the stale-plate check use the same formula. An old absolute mesh (home_offset.z = 0) still works. Do not set M206 Z by hand.
- DR-12: the halted page (page 21 / 141) shows "PRINTER HALTED", the reason in its status line and "Power-cycle the printer" (no button: nothing answers after a kill). Kills with a page of their own still use it.
- DR-24: one FIFO for every injected command (`ui_inject_P` / `ui_inject` / `inject_after_P`), `ui_busy()` counts what is still waiting; Filament STOP empties it.
- DR-19: tunes play in the background (`TuneService()` in IdleLoop) and not when sound is off; the 3 s `delay(3000)` before a mesh run is a timer.
- DR-25 / DR-26: dead code removed (SelectFile, InjectCommandandWait, Findcmndpos, FakeChangePageOfTFT, SendReadNumOfTxtToTFT, CheckHeaters, page177_to_198, pages 14 / 31 / 32 handlers, FileNavigator changeDIR / upDIR / sendFile,
  movespeed, live_Zoffset, TXT_BASE64, the 8 dead handler cases); page173 = page171; the elapsed-time text is one helper.
- LV-17 rest: late-nozzle timeout message, 5-point page left without BACK/SAVE switches its heaters off, `Probe::run_z_probe` returned 1.0 (`true`) when the tare failed in the slow pass: now NAN.
- Not done on purpose: DR-29 (the display forgets text at every page redraw; the 500 ms resend is what repairs it), DR-14 (soft endstops stay off during prints until the normalised mesh is proven).
Test: M206 after a mesh (Z about +4.4 and a mesh range of a few tenths: `M420 V1`), then the first layer test and a hand-checked Z0 with paper; `M112` from the Terminal (halted page); a SKIP-less mesh from the menu (soak) and a plain `G29` from the Terminal (no soak).
