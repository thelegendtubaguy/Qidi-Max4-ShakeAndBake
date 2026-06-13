## Why

Shake&Bake uses the QIDI Max 4 as a data-acquisition device and performs analysis outside Klipper. A stable, explicit capture artifact is required so raw accelerometer data remains reproducible, portable, and independent of analysis algorithm changes.

## What Changes

- Add a versioned Shake&Bake capture artifact contract for raw accelerometer measurements and run metadata.
- Add a lightweight pure-Python capture artifact library for writing, reading, and validating capture files without NumPy, SciPy, Matplotlib, or Klipper imports.
- Add validation states for empty, malformed, nonmonotonic, non-finite, constant, or insufficient-sample captures.
- Define metadata fields for QIDI Max 4 identity, Klipper/config fingerprints, command parameters, planned motion envelope, accelerometer identity, sample-rate estimate, input-shaper state, velocity-limit state, and fan/heater/chamber snapshots.
- Keep raw captures separate from derived analysis outputs.

## Capabilities

### New Capabilities
- `capture-artifacts`: Versioned raw capture artifacts, metadata, read/write behavior, and validation diagnostics for Shake&Bake data acquisition.

### Modified Capabilities

## Impact

- Affects new library code under `shakeandbake_capture/` or equivalent project package.
- Affects tests and fixtures for capture schema compatibility and validation behavior.
- Establishes file contracts consumed by the Klipper data-acquisition plugin and external analyzers.
- Does not add printer motion commands, Klipper plugin registration, plotting, or numerical analysis.
