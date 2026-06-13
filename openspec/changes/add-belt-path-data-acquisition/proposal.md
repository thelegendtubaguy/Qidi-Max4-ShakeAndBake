## Why

Max 4 CoreXY belt-path comparison requires raw accelerometer captures for the two motor-path diagonal directions. The printer-side responsibility is to run safe A/B acquisition and write portable raw data for external analysis.

## What Changes

- Add `SHAKEANDBAKE_CAPTURE_BELTS` to acquire CoreXY belt-path resonance data.
- Capture A direction `(1, -1, 0)` and B direction `(1, 1, 0)` with matched sweep parameters.
- Run Max 4 preflight, reject unsafe states, and validate planned X/Y motion envelopes before movement.
- Disable input shaper during acquisition and restore input-shaper and velocity-limit state through cleanup paths.
- Write one versioned raw capture artifact containing A and B measurement blocks plus command metadata.
- Keep belt comparison metrics, graphs, and mechanical-health labels in the external analyzer.

## Capabilities

### New Capabilities
- `belt-path-data-acquisition`: Printer-side Max 4 CoreXY A/B belt-path capture behavior for external belt analysis.

### Modified Capabilities

## Impact

- Affects the Shake&Bake Klipper extra command surface and acquisition lifecycle.
- Depends on capture artifacts and Max 4 preflight behavior.
- Adds tests for command parameters, CoreXY direction mapping, unsafe-state refusal, artifact metadata, and state restoration.
- Does not compare PSD curves, compute similarity, produce graphs, edit printer configuration, or support Z-axis belt behavior.
