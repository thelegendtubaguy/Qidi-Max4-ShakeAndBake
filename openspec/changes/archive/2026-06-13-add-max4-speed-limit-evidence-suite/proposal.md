## Why

Shake&Bake needs a Max 4-specific way to produce evidence-backed motion-limit recommendations without asking users to run several separate printer-side commands. Users need one printer-side capture command that gathers the raw evidence needed to report observed safe motion ceilings and conservative recommended limits on another host.

## What Changes

- Add one Max 4 printer-side command, `SHAKEANDBAKE_CAPTURE_SPEED_LIMITS`, that performs the complete speed-limit evidence acquisition run and writes one raw artifact.
- Capture X/Y homing repeatability baseline, X/Y and CoreXY stress-motion candidate results, missed-step/endstop-drift evidence, available QIDI closed-loop status/coder observations, and speed/direction vibration measurements needed for downstream recommendations.
- Keep all limit classification, graphing, and recommendation generation outside Klipper.
- Add external analysis for speed-limit evidence artifacts that reports observed tested ceilings and recommended operating limits for `max_velocity`, `max_accel`, and slicer motion speed guidance.
- Report recommendation evidence, derating rationale, first failing candidates, planner settings, input-shaper state, speed-profile PSD energy, CoreXY angular projection, vibration avoid bands, and preferred speed ranges.
- Do not mutate `printer.cfg`, slicer profiles, or runtime printer configuration beyond temporary state changes restored during acquisition.
- Do not solve material, nozzle, cooling, extrusion-flow, or filament-specific limits.

## Capabilities

### New Capabilities
- `max4-speed-limit-evidence`: Single-command Max 4 speed-limit evidence acquisition and external analysis for observed and recommended motion limits.

### Modified Capabilities

## Impact

- Affects the Shake&Bake Klipper extra command surface, acquisition planner, preflight use, state restoration, and raw artifact writing.
- Affects external analyzer CLI and analysis libraries with a new speed-limit evidence analysis mode.
- Depends on Max 4 preflight, capture artifact validation, speed-profile capture semantics, and QIDI closed-loop metadata when available.
- Adds fixtures and tests for safe-state refusal, bounded motion planning, endstop-repeatability baseline, missed-step classification, closed-loop status capture, coupled velocity/accel candidate grids, speed-profile grid/projection/range detection, conservative recommendations, and raw/derived output separation.
