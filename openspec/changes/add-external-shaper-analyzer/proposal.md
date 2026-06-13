## Why

Shake&Bake analysis belongs outside Klipper so Max 4 data acquisition stays safe and lightweight. Users need an external command that reads raw X/Y captures, validates signal quality, computes resonance summaries, and emits explicit shaper recommendations without modifying printer configuration.

## What Changes

- Add an external Shake&Bake analyzer CLI that reads versioned capture artifacts from printer-side acquisition.
- Validate captures before analysis and return explicit diagnostics for invalid, insufficient, degenerate, noisy, or non-finite data.
- Compute X/Y PSD summaries from raw accelerometer samples using an offline numerical dependency set isolated from Klipper.
- Produce machine-readable analysis JSON, human-readable summary text, graph image files, and a proposed `[input_shaper]` config snippet when signal quality supports a recommendation.
- Report LIS2DW sample-rate estimates, aliasing/noise warnings, detected resonance peaks, selected shaper type/frequency, residual vibration estimate, smoothing estimate, and acceleration guidance.
- Do not analyze Z-axis motion because the Max 4 Z axis is bed-driven and the toolhead accelerometer does not provide meaningful Z movement data.
- Do not edit `printer.cfg` or issue printer commands.

## Capabilities

### New Capabilities
- `external-shaper-analysis`: Offline X/Y input-shaper analysis for Shake&Bake raw capture artifacts.

### Modified Capabilities

## Impact

- Affects new CLI/library code under `shakeandbake_analyze/` or equivalent project package.
- Depends on the capture artifact contract produced by printer-side acquisition.
- Adds offline numerical/plotting dependencies outside Klipper only.
- Adds fixtures for valid captures, empty captures, nonmonotonic time, non-finite samples, constant signals, noisy LIS2DW-like traces, and synthetic resonance cases.
- Does not add Klipper commands, collect printer data, perform belt comparison, run speed profiling, or write printer configuration.
