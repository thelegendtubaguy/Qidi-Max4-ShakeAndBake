## Why

Shake&Bake needs a printer-resident component that safely performs Max 4 accelerometer measurements and writes portable raw captures while keeping Klipper free of heavy analysis dependencies. The printer-side responsibility is data acquisition, state restoration, and artifact creation only.

## What Changes

- Add a Klipper extra named `shakeandbake` that registers explicit Shake&Bake data-acquisition commands.
- Add `SHAKEANDBAKE_PREFLIGHT` to report Max 4 readiness and state before acquisition.
- Add an X/Y shaper data-acquisition command that measures CoreXY toolhead resonance along X and Y and writes raw capture artifacts.
- Disable input shaper during acquisition and restore input-shaper and velocity-limit state through guaranteed cleanup paths.
- Refuse acquisition when the printer is printing, paused, running virtual-SD work, homing, not ready, or when planned X/Y motion exceeds configured bounds.
- Do not acquire or interpret Z-axis resonance data because the Max 4 Z axis is bed-driven and not belt-driven, and the toolhead accelerometer does not measure bed Z movement.
- Do not import NumPy, SciPy, Matplotlib, or plotting libraries in the Klipper process.

## Capabilities

### New Capabilities
- `printer-data-acquisition`: Max 4 Klipper-side preflight and X/Y accelerometer capture commands that write versioned raw capture artifacts.

### Modified Capabilities

## Impact

- Affects new Klipper extra code under `klippy/extras/` or a deployable equivalent.
- Depends on the capture artifact contract and Max 4 preflight behavior from related changes.
- Affects tests for command registration, refusal states, motion-envelope validation, capture writing, and state restoration under exceptions.
- Does not perform external analysis, produce plots, recommend shaper settings, compare belts, run speed profiling, or edit `printer.cfg`.
