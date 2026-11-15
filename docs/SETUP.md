# Kobra Max (Marlin 2.1.2.9 port): first-time setup

For the printer with the Anycubic TriGorilla Pro A mainboard and the DWIN touch display, after flashing a release
(`release_vN`) from branch `main` (development happens on `kobra-max-hc32-2.1`). Everything below uses the printer's own touch screen; the Terminal page
(System > TERMINAL) takes the few G-code commands.

The probe check, bed mesh, Z offset and first-layer test have been used on a printer; the 5-point page, K test, E-steps page and
power-loss resume have had little testing. Treat every step as a first run, stay near the machine and keep a hand on the power switch
for the first homing.

## Before flashing

1. On the OLD firmware, note your settings: send `M503` from the Terminal (or a USB host) and keep the output.
2. Flash the display first, then the mainboard, exactly as the release's `README.txt` says. You need one SD card (two work too):
   * formatted FAT32 with a 4096-byte allocation unit (with any other cluster size the display's blue update screen shows every
     count as 000 and flashes nothing);
   * the same card can hold the `DWIN_SET` folder (flashed from the slot on the back of the display) and `firmware.bin` (flashed from
     the printer's front slot). Move the card between the two slots.
3. Before each flash power the printer off completely and wait 15 to 20 seconds (a quick off/on does not reset the display).
4. Once the new firmware has started it renames `firmware.bin` on the card to `firmware.cur`, so the next power-up does not flash
   it again. To flash the same file again, copy `firmware.bin` onto the card again.

## Where the settings are kept

Bed mesh, Z offset, PID, E-steps, K, the 5-point corrections and the wizard's finished steps are stored in the printer's own chip
flash, not on the SD card; flashing a new firmware does not erase them. When a firmware with flash settings starts for the first
time and finds none in flash, it takes over `eeprom.dat` from the SD card ONCE (settings saved by the stock or 2.0.8 firmware do not
match this firmware's layout and come back as defaults). If a new release changes the settings layout, the firmware restores the
defaults: the release notes say so, and you redo the setup wizard.

## First boot

5. System > ABOUT: it should show the firmware build id and `display set: release_vN`, the name of the release you flashed. If the
   display set is from another release, flash both parts again from the SAME release folder (mixed sets mis-route buttons).
6. The power-on jingle plays after the main screen appears (only if sound is on).
7. Terminal: send `M119`, press the Z input by hand and send `M119` again. The Z line must change between open and triggered.
   Do this BEFORE the first homing of a new build, and keep a hand on the power switch for that first homing.

## Set up the printer: the setup wizard

System > **SETUP WIZARD** shows five steps, each a button with a status line under it. The first step that is not done yet is lit
orange; finished steps are remembered with the settings. Do them in this order (tap a step again to redo it; nothing starts while a
print or another step is running):

| Step | What it does | Same as |
|---|---|---|
| 1 PROBE CHECK | Five probe touches at the bed centre; the spread appears under the button (OK up to 0.03 mm, FAIR up to 0.08 mm, NOISY above: the nozzle or the probe wiring needs attention). | Leveling menu > AUTO Z OFFSET (probe test part) |
| 2 BED MESH | Heats the bed (60 C) and nozzle (190 C), waits out a 10 minute heat soak (the glass keeps moving after the sensor reads the target; SKIP HEAT SOAK on the heating page skips it; the nozzle only heats for the last minutes), then probes 9 x 9 points. Allow 45-60 minutes in total. The mesh is stored and applied after every home. | Leveling menu > BED MESH (G29) |
| 3 Z OFFSET | The paper test at the bed centre, hot (see below). SAVE returns to the wizard. | Leveling menu > MANUAL Z OFFSET |
| 4 5-POINT Z | Paper tests at the four corner squares (see below). | Leveling menu > 5-POINT Z |
| 5 FIRST LAYER TEST | Prints five squares one layer high (see below). | - |

**Mesh first, offset second.** The Z offset is only the small gap between the nozzle and the paper while the bed mesh is active
(the mesh already holds the distance from the Z endstop to the bed). Set before the mesh, it would be counted twice and the nozzle
would end up that much too low. For the same reason the 5-point page and the first layer test refuse to start without a mesh, and MANUAL Z OFFSET and AUTO Z OFFSET
ask to make one first.

**The stale-mesh check.** Before the Z offset page, the 5-point page or the first layer test lowers the nozzle, the printer probes the
bed (front-left mesh point and the centre) and compares with the mesh. If the bed is more than **0.5 mm** away from where the mesh
says (a glass plate added or removed, the bed adjusted) it says so and does not lower the nozzle: make a new mesh.

### Z offset (wizard step 3, or Leveling menu > MANUAL Z OFFSET)

**The paper test is done HOT**, at the same temperatures as the mesh (190 C nozzle, 60 C bed), so the offset matches what the
printer does when it prints. The page homes, parks the nozzle 5 mm up at the bed centre, shows `Heat 120/190  bed 45/60` while it
heats (BACK still works then; it switches the heaters off) and only then lowers to the start height (1.0 mm by default; change it with
the - / + row "Z OFFSET: START HEIGHT" on the Leveling menu, minimum 0.3 mm). The nozzle is HOT: use a strip of paper and keep your
fingers away from it. Lower it with the - buttons until the paper just drags, then SAVE. The offset is stored with the settings and
applied at every home. BACK or SAVE switch the nozzle heater off.

AUTO Z OFFSET on the Leveling menu makes the mesh if there is none, runs the 5-probe test and then continues as the manual page.

### 5-POINT Z (wizard step 4, or Leveling menu > 5-POINT Z)

The Z offset sets the height at the bed centre only; the mesh is supposed to take care of the rest, but a mesh can be wrong at one
side (the squares of the first layer test then fail there: rows that do not stick together). Do this after the Z offset, with the
same bed surface. Tap a corner button (REAR LEFT, REAR RIGHT, FRONT LEFT, FRONT RIGHT, as you look at the printer): the first tap
homes and heats (the nozzle is HOT), then the nozzle goes to that corner and lowers to 0.50 mm above the centre-calibrated level.
Lower it with the - buttons until the paper just drags and press STORE POINT. The number at paper contact is the mesh error there
(0.00 = right; -0.15 = the mesh was 0.15 mm too high). Do the corners that need it (at least the ones whose squares fail); the
line under each corner button shows what is stored. The four values become a smooth correction over the whole mesh (a tilt, a twist
and a bowl; zero at the centre; at most 0.3 mm; outside the corner squares it keeps the value at their edge). SAVE keeps it with
the settings; BACK throws the unsaved corrections away. RESET takes every saved 5-point correction out of the mesh again.
Redo this page after every new mesh and whenever the bed surface changes.

Without a bed mesh Z0 is NOT at the bed (the mesh holds the bed height, the offset only the gap above it): after a home the firmware
prints "Warning: no bed mesh" on the serial port (OctoPrint / USB prints have no screen warning). Make the mesh before any print.

### First layer test (wizard step 5)

Heats to 200 C / 60 C (PLA) with the heat soak (SKIP SOAK skips it), homes, checks the mesh (see above), primes and draws a purge line
along the front edge, then prints five 24 mm squares one layer high (two wall lines, then solid rows inside), at the corners and the
centre of the bed. To stop it, tap step 5 again or press BACK: it finishes the moves already planned (a few seconds), lifts the
nozzle and switches the heaters off. The squares should be lightly squished: not see-through (too close), not round and lifting (too
far). Adjust the offset in steps of 0.02 mm on the manual Z page and SAVE, or correct one corner on the 5-point page.

**Power-loss test**, only when the first layer is good: start a short print and send `M413 O` from the Terminal. Then power-cycle and
use the resume page.

## Tuning (after a first print works)

8. Hotend and bed PID: Prepare > THERMAL TUNING (about 5 and 8 minutes). The results save automatically.
9. E-steps: Prepare > E-STEPS. HEAT + EXTRUDE 100 MM pushes 100 mm. Mark the filament 120 mm above the extruder first, measure what
    is left, enter 120 minus that, SAVE.
10. Linear advance: Prepare > ADVANCE K. **K TEST** prints 11 lines from front to back (with K = 0: K 0.0 to 1.0; with a K set:
    K-0.10 to K+0.10 in steps of 0.02). Pick the line with even width and clean ends, enter its K with the - / + buttons and SAVE.
    Bowden tubes often need roughly 0.5 to 1.5.

## When to redo what

* Z offset: after changing the nozzle, the bed or print plate, or the Z endstop / probe, and after a factory reset or `M502`.
* Bed mesh: when the bed's shape changes (adjusting the bed, a new plate; the stale-mesh check tells you). Not needed before every
  print. After a new mesh redo the 5-point corrections.
* A new mesh keeps your offset, a new offset does not need a new mesh.

## If something is wrong

* The nozzle scrapes or squishes the first layer: the offset is too low; raise it (+ on the manual Z page) and SAVE.
* "Bed moved" / the mesh check refuses: make a new mesh (wizard step 2).
* Settings are back at their defaults after flashing: the new release changed the settings layout (see "Where the settings are kept").
* Display shows the wrong labels after a flash: the display files and the firmware come from different releases. Flash both from the
  same release folder.
* Display blank, frozen or garbled after a flash: power off, wait 15 to 20 seconds, flash the last set that worked.
* Factory reset: System > FACTORY RESET (M502 + M500): every setting back to its default, the mesh is gone.
