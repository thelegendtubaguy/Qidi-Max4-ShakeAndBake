## 1. Plugin Skeleton

- [x] 1.1 Create the `shakeandbake` Klipper extra module with a `load_config` entry point.
- [x] 1.2 Register `SHAKEANDBAKE_PREFLIGHT` and `SHAKEANDBAKE_CAPTURE_SHAPER` commands.
- [x] 1.3 Add import checks or tests proving the plugin does not import NumPy, SciPy, Matplotlib, plotting modules, or the external analyzer package.

## 2. Klipper Adapter

- [x] 2.1 Implement an adapter for gcode responses, printer readiness, print state, pause state, virtual-SD state, homing state, and object lookup.
- [x] 2.2 Implement adapter methods for input-shaper snapshot, disable, and restore.
- [x] 2.3 Implement adapter methods for velocity-limit snapshot, temporary update, and restore.
- [x] 2.4 Implement adapter methods for accelerometer availability and raw sample acquisition.
- [x] 2.5 Implement feature detection with actionable errors when required Klipper/QIDI objects are unavailable.

## 3. Preflight Command

- [x] 3.1 Connect `SHAKEANDBAKE_PREFLIGHT` to the Max 4 preflight engine.
- [x] 3.2 Format ready status, blocking findings, warnings, probe point, accelerometer identity, supported axes, and relevant state snapshots in gcode output.
- [x] 3.3 Ensure preflight reports X and Y as supported acquisition axes and excludes Z.

## 4. Shaper Capture Command

- [x] 4.1 Parse `AXIS`, `FREQ_START`, `FREQ_END`, `HZ_PER_SEC`, `ACCEL_PER_HZ`, `TRAVEL_SPEED`, `ACCEL_CHIP`, and `OUTPUT_DIR` parameters with explicit validation errors.
- [x] 4.2 Reject `AXIS=Z` and all unsupported axis values before preflight motion checks.
- [x] 4.3 Run preflight and stop before motion if any blocking finding exists.
- [x] 4.4 Execute X and/or Y resonance acquisition with input shaper disabled during sampling.
- [x] 4.5 Record one measurement block per requested axis with sample rows and measurement metadata.
- [x] 4.6 Write a versioned raw capture artifact through the capture artifact library.
- [x] 4.7 Report the capture artifact path and measurement names in gcode output.

## 5. State Restoration

- [x] 5.1 Implement a single acquisition context that snapshots all temporary state before changes.
- [x] 5.2 Restore input-shaper state and velocity-limit state from a guaranteed cleanup path.
- [x] 5.3 Report restoration failures distinctly from acquisition failures.
- [x] 5.4 Include restoration status in capture metadata when a capture artifact is written.

## 6. Tests

- [x] 6.1 Test command registration through a fake Klipper config/gcode environment.
- [x] 6.2 Test preflight command output for ready and blocking states.
- [x] 6.3 Test capture command refusal for printing, paused, virtual-SD active, homing, not-ready, accelerometer-missing, out-of-bounds, and `AXIS=Z` states.
- [x] 6.4 Test successful `AXIS=X`, `AXIS=Y`, and `AXIS=ALL` capture artifact creation using fake accelerometer samples.
- [x] 6.5 Test forced exceptions during motion, sampling, and writing to verify input-shaper and velocity-limit restoration.
