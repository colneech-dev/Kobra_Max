# Open items (2026-11-03, after release_v50)

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
