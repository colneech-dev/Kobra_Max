# Kobra Max (Marlin 2.1.2.9 port): first-time setup

For the printer with the Anycubic TriGorilla Pro A mainboard and the DWIN touch display, after flashing a release
(`release_vN`) from branch `kobra-max-hc32-2.1`. Everything below uses the printer's own touch screen; the Terminal page
(Tools > Terminal) takes the few G-code commands.

Not tested on the printer yet: treat every step as a first run, stay near the machine and keep a hand on the power switch for
the first homing.

## Before flashing

1. On the OLD firmware, keep your settings: send `M503` from the Terminal (or copy `eeprom.dat` from the printer's SD card).
   The first boot of this firmware resets all saved settings (Z offset, bed mesh, PID, language, sound).
2. Power the printer off completely and wait 15 to 20 seconds.
3. Flash the display files first (use a SEPARATE SD card for the display), then `firmware.bin` on the printer's own card, as the
   release README describes. Never format the printer's own SD card: it holds `eeprom.dat`.

## First boot

4. Settings are at their defaults. Open About: it should read `KobraMax 2.1.2.9...` and the display set name of the release.
5. The power-on jingle plays after the main screen appears (only if sound is on).
6. Terminal: send `M119`, press the Z input by hand and send `M119` again. The Z line must change between open and triggered.

## Set up the printer

The main page has a **SETUP WIZARD** button that does steps 8 to 12 below as four buttons with a status line under each:
1 Z OFFSET (the manual Z page; SAVE returns to the wizard), 2 BED MESH (the probe pre-check and G29, then back),
3 PROBE CHECK (the 5-probe test; the spread appears under the button), 4 FIRST LAYER TEST (see step 12). Do them in order; tap a
step again to redo it. Everything stays inactive while a print or another step is running. The manual steps below describe
the same things.

7. Home all axes (Prepare > Leveling > MANUAL Z ADJUST does it for you).
8. Z offset, once: Leveling menu > MANUAL Z ADJUST. The nozzle parks at the start height above the bed (1.0 mm by default; change it
   with the - / + row on the Leveling menu, minimum 0.3 mm). Lower it with the - buttons until a sheet of paper just drags, then SAVE.
   The offset is stored with the settings and applied at every home.
9. Bed mesh: Leveling menu > AUTO BED LEVEL. It heats and probes 7 x 7 points (several minutes). The mesh is stored and re-applied
   after every home.
10. Probe check: AUTO Z OFFSET runs a 5-probe test at the bed centre and shows the spread (OK up to 0.03 mm, FAIR up to 0.08 mm,
    NOISY above), then parks for the manual step. Noisy results mean the nozzle or the probe wiring needs attention.
11. Look at the mesh: Leveling menu > VIEW BED MESH (heights in 0.01 mm relative to the average, back of the bed at the top).

## First print

12. First layer test (wizard step 4, or print your own): the wizard heats to 200 C / 60 C (PLA), homes, draws a purge line and prints
    five 24 mm solid squares one layer high, at the corners and the centre of the bed (about 5 minutes). Tap step 4 again to stop it.
    It needs the bed mesh from step 9. Print one small flat layer (a single-layer square). The skirt should be lightly squished: not see-through (too close), not
    round and lifting (too far). Adjust the offset in steps of 0.02 mm on the manual Z page and SAVE.
13. Power-loss test, only when the first layer is good: start a short print and send `M413 O` from the Terminal. Then power-cycle and
    use the resume page.

## Tuning (after a first print works)

14. Hotend and bed PID: Prepare > THERMAL TUNING (about 5 and 8 minutes). The results save automatically.
15. E-steps: Prepare > E-STEPS. HEAT + EXTRUDE pushes 100 mm. Mark the filament 120 mm above the extruder first, measure what is
    left, enter 120 minus that, SAVE.
16. Linear advance: Prepare > ADVANCE K. Leave K at 0 until you have printed a K-factor test pattern, then enter the K of its cleanest
    corner line and SAVE. Bowden tubes often need roughly 0.5 to 1.5.

## When to redo what

* Z offset: after changing the nozzle, the bed or print plate, or the Z endstop / probe, and after a factory reset or `M502`.
* Bed mesh: when the bed's shape changes (adjusting the bed, a new plate). It is not needed before every print.
* Neither depends on the other: a new mesh keeps your offset, a new offset does not need a new mesh.

## If something is wrong

* The nozzle scrapes or squishes the first layer: the offset is too low; raise it (+ on the manual Z page) and SAVE.
* Settings vanish after a reboot: check the printer's SD card is in and not write-protected (a failed save beeps).
* Display shows the wrong labels after a flash: the display files and the firmware come from different releases. Flash both from the
  same release folder.
