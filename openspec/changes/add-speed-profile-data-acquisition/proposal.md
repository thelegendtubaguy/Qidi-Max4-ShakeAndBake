## Why

Max 4 speed-profile analysis needs raw vibration captures across controlled CoreXY movement directions and speeds. The printer-side command must collect this data safely and defer heavy aggregation, projection, and graphing to the external analyzer.

## What Changes

- Add `SHAKEANDBAKE_CAPTURE_SPEED_PROFILE` for Max 4 CoreXY speed-profile acquisition.
- Capture the CoreXY main directions 45 degrees and 135 degrees across configured speed steps.
- Use preflight, motion-envelope validation, host-resource warnings, and cleanup-path state restoration.
- Store each speed/direction measurement as a named block in a versioned raw capture artifact.
- Record parameters such as `MAX_SPEED`, `SPEED_INCREMENT`, `ACCEL`, `TRAVEL_SPEED`, `SIZE`, `ACCEL_CHIP`, and probe point.
- Keep speed-vs-angle projection, avoid-band detection, preferred speed ranges, and graphs in the external analyzer.

## Capabilities

### New Capabilities
- `speed-profile-data-acquisition`: Printer-side Max 4 CoreXY speed/direction vibration capture for external speed-profile analysis.

### Modified Capabilities

## Impact

- Affects the Shake&Bake Klipper extra command surface and acquisition lifecycle.
- Depends on capture artifacts and Max 4 preflight behavior.
- Adds tests for parameter validation, speed grid construction, direction metadata, unsafe-state refusal, artifact writing, and state restoration.
- Does not perform speed-profile analysis, graphing, slicer recommendation generation, config edits, or Z-axis profiling.
