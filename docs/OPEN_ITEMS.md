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
