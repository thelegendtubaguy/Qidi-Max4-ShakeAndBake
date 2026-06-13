## 1. Plugin Skeleton

- [ ] 1.1 Create the `shakeandbake` Klipper extra module with a `load_config` entry point.
- [ ] 1.2 Register `SHAKEANDBAKE_PREFLIGHT` and `SHAKEANDBAKE_CAPTURE_SHAPER` commands.
- [ ] 1.3 Add import checks or tests proving the plugin does not import NumPy, SciPy, Matplotlib, plotting modules, or the external analyzer package.

## 2. Klipper Adapter

- [ ] 2.1 Implement an adapter for gcode responses, printer readiness, print state, pause state, virtual-SD state, homing state, and object lookup.
- [ ] 2.2 Implement adapter methods for input-shaper snapshot, disable, and restore.
- [ ] 2.3 Implement adapter methods for velocity-limit snapshot, temporary update, and restore.
- [ ] 2.4 Implement adapter methods for accelerometer availability and raw sample acquisition.
- [ ] 2.5 Implement feature detection with actionable errors when required Klipper/QIDI objects are unavailable.

## 3. Preflight Command

- [ ] 3.1 Connect `SHAKEANDBAKE_PREFLIGHT` to the Max 4 preflight engine.
- [ ] 3.2 Format ready status, blocking findings, warnings, probe point, accelerometer identity, supported axes, and relevant state snapshots in gcode output.
- [ ] 3.3 Ensure preflight reports X and Y as supported acquisition axes and excludes Z.

## 4. Shaper Capture Command

- [ ] 4.1 Parse `AXIS`, `FREQ_START`, `FREQ_END`, `HZ_PER_SEC`, `ACCEL_PER_HZ`, `TRAVEL_SPEED`, `ACCEL_CHIP`, and `OUTPUT_DIR` parameters with explicit validation errors.
- [ ] 4.2 Reject `AXIS=Z` and all unsupported axis values before preflight motion checks.
- [ ] 4.3 Run preflight and stop before motion if any blocking finding exists.
- [ ] 4.4 Execute X and/or Y resonance acquisition with input shaper disabled during sampling.
- [ ] 4.5 Record one measurement block per requested axis with sample rows and measurement metadata.
- [ ] 4.6 Write a versioned raw capture artifact through the capture artifact library.
- [ ] 4.7 Report the capture artifact path and measurement names in gcode output.

## 5. State Restoration

- [ ] 5.1 Implement a single acquisition context that snapshots all temporary state before changes.
- [ ] 5.2 Restore input-shaper state and velocity-limit state from a guaranteed cleanup path.
- [ ] 5.3 Report restoration failures distinctly from acquisition failures.
- [ ] 5.4 Include restoration status in capture metadata when a capture artifact is written.

## 6. Tests

- [ ] 6.1 Test command registration through a fake Klipper config/gcode environment.
- [ ] 6.2 Test preflight command output for ready and blocking states.
- [ ] 6.3 Test capture command refusal for printing, paused, virtual-SD active, homing, not-ready, accelerometer-missing, out-of-bounds, and `AXIS=Z` states.
- [ ] 6.4 Test successful `AXIS=X`, `AXIS=Y`, and `AXIS=ALL` capture artifact creation using fake accelerometer samples.
- [ ] 6.5 Test forced exceptions during motion, sampling, and writing to verify input-shaper and velocity-limit restoration.
