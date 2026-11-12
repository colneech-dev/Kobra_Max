# Code review and plan, 2026-11-12 (after release_v69)

Nothing in this file has been changed in the code. It follows `REVIEW_PLAN_2026-11-08.md` / `REVIEW_PROGRESS_2026-11-08.md`; items still open
from those are listed at the end.

## What was read
- Line by line: every difference from Marlin 2.1.2.9 outside the HAL and the display driver (36 files, 1,176 diff lines), `Configuration.h`,
  `Configuration_adv.h`, `platformio.ini`, `dgus_tft.cpp` (5,556 lines), `anycubic_dgus_lcd.cpp`, `eeprom_flash_ab.cpp`, `MarlinHAL.cpp`,
  `MarlinSerial.cpp/.h`, `sdio.cpp`, `timers.cpp`, `tone.cpp`, the pins file.
- Only searched, not read: `dgus_tft.h`, `dgus_tft_defs.h`, `dgus_Tunes.*`, `dgus_FileNavigator.*`, the other HAL files (`sysclock`, `endstop_interrupts`,
  `Servo`, `MinSerial`, `pinsDebug`, `HAL.cpp`), `tools/*.py` (reviewed on 2026-11-08; only the structure of `build_release.py` was looked at now).
- Compared with the hardware logs of 2026-11-12 (two menu meshes, the stale-check lines, the outlier re-probes, M503).

## Findings from the logs (they decide the order of the plan)

### F1. The bed centre sits on a 1 mm step, and the Z offset is measured there
G29 probes row by row and alternates the X direction (even rows left to right, odd rows right to left). In column 4 (X 200) the rows probed
left to right read 0.3 to 0.6 mm lower than the rows probed right to left, in both meshes; no other column shows that stripe. Columns 5 and 6
(X 247 to 295) are 1.0 to 1.5 mm lower than columns 1 to 3 in every row. So the surface the probe sees drops by about 1 mm close to X 200, and
half a millimetre of X position decides which side the nozzle lands on.
- The Z offset page, the AUTO Z probe test and the centre point of the stale-mesh check all use X 200 Y 200: the worst spot on this bed.
  That fits "the paper test fails, the offset is too high" (the page hit its -0.3 limit) and the stale check reading "centre 0.31 / 0.37".
- Whether the low strip is real (sheet or bed) or a probe artefact (the head giving way there) is NOT known. See the tests below.

### F2. A single probe does not repeat what G29 measured at the same node
- Node 4,0 (X 200 Y 10): G29 -0.75 and -0.80, the re-probe -0.22 and -0.19, in both meshes. G29 arrived from the left, the re-probe from the right.
- Stale check on a mesh that the next mesh reproduced within 0.1 mm: front-left 0.82 / 0.70, centre 0.37 / 0.31. That refusal ("Mesh off by 0.70")
  was very likely a false alarm; my explanation at the time (bed not at temperature) was wrong, the heat soak had run.
- Nodes approached from the same side as in G29 agreed within 0.02 to 0.13 mm.

### F3. The trigger point of the probe is 1.5 to 2.4 mm below first contact
`M851 Z` here is exactly that distance (motion.cpp shifts Z0 by it; the mesh holds trigger heights). History: 2.36 at 120 mm/min without glass,
1.9 at 120 with glass, 1.74 at 90, now below 1.61 at 90. 2.36 mm at 2.0 mm/s and 1.74 mm at 1.5 mm/s are both about 1.17 s: a fixed delay in
the strain-gauge module fits as well as bed flex does. Any part of it that depends on position goes straight into the mesh.

## Tests on the printer before any firmware change (about 20 minutes)
1. Steel ruler on edge across the bed at Y 200, sheet fitted, bed hot: is there a gap under it between X 200 and X 320?
2. Paper check with the mesh on, hot, homed: `M420 S1`, then at X 100 Y 200 and at X 270 Y 200 go to Z 3 and step down (2, 1.5, 1.0, 0.8, 0.6 ...)
   with paper under the nozzle. Note the Z where the paper drags at each. Same Z: the mesh is right and the strip is real. About 1 mm higher at
   X 270: the strip is a probe artefact and the mesh would drive the nozzle into the bed there.
3. Direction: `G1 Z10`, `G1 X150 Y200 F3000`, `G30 X200 Y200`, `G1 Z10`, `G1 X250 Y200 F3000`, `G30 X200 Y200`. Repeat at X 100 (X50 / X150).
**Until test 2 is done do not run 5-POINT Z, the first layer test or the K test:** they lower the nozzle to 0.2 to 0.5 mm above the mesh at
X 240 to 312.

## Changes, in order

### Priority 1: correctness and safety
1. **Reference point off the step.** Z offset page, AUTO Z M48 and the stale check's second point use the flattest mesh node near the centre
   (smallest difference to its four neighbours) instead of X 200 Y 200; the page shows where it is.
2. **Same approach as G29 for every single probe** (stale check, outlier re-probe): pre-position 15 mm to the side G29 came from for that row.
   Outlier check: replace a node only when two re-probes agree with each other and differ from the first reading; a node on a real step is
   left alone.
3. **Z offset page must not edit the stored offset while lowering.** Today every tap writes `probe.offset.z`; the wizard's deferred `M500`
   (`wz_save_pending`) or an `M500` from a host can store the half-lowered value (up to 1.3 mm low with the v69 limit). Keep a working value
   and write the offset at SAVE only; hold deferred saves while the Z page or the 5-point page is open.
4. **Page change that is not taken** (the stuck "Probing 0/81" screen, cause not found: the settings save is not it, the page frame is sent a
   second before): read the display's page back after each change and resend up to three times. Show "Re-checking n/4" during the re-probes.
5. **Trace of the offset.** `M851 Z` went from 1.74 to 1.90 with no cause found (`EEPROM_INIT_NOW` is off, no code path found that resets only
   the offset). Print `M851` and `M206` at boot and print a line whenever either changes.

### Priority 2: robustness
6. **Probe speed experiment**: a run-time slow probe speed (one G-code parameter) so M48 can be run at 60 / 90 / 120 / 180 mm/min at one spot.
   The slope gives the delay, the rest is flex. Decides whether a slower probe or a fixed-delay correction is worth it.
7. **Host serial loses characters** (`Unknown command: "105"` twice): UART receive interrupts run at the lowest priority and the port has a
   one-byte buffer. Set `UART_RX_IRQ_PRIO 1` (below the step timer, above the temperature timer) and count overruns in the boot / M115 output.
8. **Settings save stalls the CPU for about 0.1 s** (sector erase and 1,028 word writes): flush both serial ports first; touches and host
   bytes that arrive during it are lost (document it).
9. **5-point correction** can only model tilt, twist and bowl, limited to 0.3 mm. Decide after the tests: drop it, or replace it by paper
   offsets on a 3 x 3 grid.

### Priority 3: housekeeping
10. Stale comments ("SD card" in `onSettingsStored`, "Marlin 2.0.8" in three places), `ANYCUBIC_LCD_DEBUG` in `Configuration.h` (check that it
    does nothing), `TMCStepper@^0.7.3` pinned to an exact version.
11. 11 release folders (about 900 MB, not tracked by git) on this PC: delete the old ones after asking.
12. 30 commits exist only on this PC (the last push was `4c36aab`).

## Still open from 2026-11-08
DR-11 (display restart versus first sync), DR-13 (any status message clears the runout flag), DR-14 (soft endstops off during prints), DR-20..23,
MC-11 (`M413 O` debug stays on until power loss is proven), MC-17 (E0 driver address), MC-18, TL-21. Untested on hardware: SD card at 12.5 MHz,
thermal protection 40 s / 4 C on real prints, power-loss recovery, linear advance, the 5-point page, v69's -1.0 mm limit.
