## Why

Operators need a controlled way to excite one Max 4 X/Y or CoreXY belt-path direction at a fixed frequency so resonating components can be located by touch, sound, and optional accelerometer recording.

## What Changes

- Add `SHAKEANDBAKE_EXCITE AXIS=X|Y|A|B FREQUENCY=<hz> DURATION=<sec> RECORD=0|1`.
- Run preflight, validate bounds, disable input shaper, execute fixed-frequency excitation pulses, and restore state through cleanup paths.
- Support optional raw accelerometer recording into a versioned capture artifact.
- Add `shakeandbake analyze static-frequency <capture>` for optional external spectrogram and energy-over-time outputs.
- Reject Z-axis excitation.

## Capabilities

### New Capabilities
- `static-frequency-diagnostics`: Max 4 fixed-frequency excitation and optional external analysis for locating resonating components.

### Modified Capabilities

## Impact

- Affects the Shake&Bake Klipper extra command surface and external analyzer CLI.
- Depends on Max 4 preflight and capture artifact behavior.
- Adds tests for parameter validation, axis mapping, state restoration, optional recording, and static-frequency analysis output.
- Does not perform shaper recommendation, belt comparison, speed-profile analysis, config edits, or Z-axis excitation.
