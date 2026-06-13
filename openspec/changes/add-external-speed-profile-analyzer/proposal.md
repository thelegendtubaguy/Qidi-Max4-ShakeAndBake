## Why

Speed-profile captures need external analysis to convert speed/direction accelerometer data into vibration-energy summaries, avoid bands, and preferred speed ranges without loading the Max 4 host during acquisition.

## What Changes

- Add `shakeandbake analyze speed-profile <capture>` for external speed-profile analysis.
- Validate measurement completeness, timestamps, samples, speed grid, and direction metadata before analysis.
- Compute PSD energy per speed/direction measurement.
- Project CoreXY 45 degree and 135 degree measurements into 0-360 degree vibration guidance using motor-speed decomposition.
- Produce analysis JSON, human-readable summary, speed/angle graph files, avoid bands, preferred speed ranges, and angle-energy summaries.
- Report LIS2DW sample-rate, noise, aliasing, and insufficient-data warnings.

## Capabilities

### New Capabilities
- `external-speed-profile-analysis`: Offline Max 4 CoreXY speed-profile analysis from Shake&Bake capture artifacts.

### Modified Capabilities

## Impact

- Affects external analyzer CLI and analysis library code.
- Depends on speed-profile capture artifacts.
- Adds fixtures for valid speed grids, missing directions, missing speeds, degenerate samples, noisy LIS2DW-like traces, known energy peaks, and preferred valleys.
- Does not collect printer data, run inside Klipper, edit slicer profiles, edit printer configuration, or analyze Z-axis motion.
