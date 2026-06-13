## Why

Max 4 data acquisition depends on the configured toolhead LIS2DW axes map. Shake&Bake needs a safe validation path that checks X/Y accelerometer response and records orientation metadata without treating bed-driven Z motion as useful toolhead data.

## What Changes

- Add accelerometer orientation validation for the stock Max 4 LIS2DW using X and Y toolhead moves only.
- Preserve configured `axes_map`, detected dominant response axes, polarity hints, sample-rate estimate, noise metrics, and validation diagnostics.
- Report when X/Y response is insufficient, ambiguous, saturated, or noisy.
- Explicitly mark Z-axis movement validation unsupported on Max 4.
- Use validation results in preflight output and capture metadata.

## Capabilities

### New Capabilities
- `lis2dw-orientation-validation`: Max 4 toolhead accelerometer orientation and signal validation using X/Y movement only.

### Modified Capabilities

## Impact

- Affects Max 4 preflight output and optional validation command behavior.
- Depends on capture artifacts and safe X/Y acquisition primitives.
- Adds fixtures for stock axes map, inverted axes, ambiguous X/Y response, missing signal, noisy signal, and invalid Z validation requests.
- Does not perform full three-axis calibration, Z-axis validation, shaper analysis, or config edits.
