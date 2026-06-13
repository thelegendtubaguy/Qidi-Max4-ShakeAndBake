## Why

Shake&Bake commands must verify the Max 4 is idle, configured as expected, and safe to move before any accelerometer acquisition begins. QIDI Max 4 configuration differs from generic Klipper assumptions, especially X/Y closed-loop sections and the toolhead-mounted LIS2DW accelerometer.

## What Changes

- Add Max 4 configuration inspection for `[printer]`, `[resonance_tester]`, `[lis2dw]`, `[input_shaper]`, `[closed_loop x]`, and `[closed_loop y]` data.
- Add a preflight result model that reports readiness, blocking failures, warnings, and captured machine state.
- Treat the Max 4 as CoreXY with stock toolhead LIS2DW acceleration capture.
- Exclude Z-axis calibration and Z vibration interpretation because the bed-moving Z axis is not belt-driven and the toolhead accelerometer does not measure Z bed motion.
- Add checks for printer idle state, active print/pause/virtual-SD/homing conditions, accelerometer availability, probe point bounds, planned X/Y move envelope, host load, free memory, free disk, and fan/heater/chamber state.

## Capabilities

### New Capabilities
- `max4-preflight`: QIDI Max 4 configuration inspection and safety preflight behavior for Shake&Bake data acquisition.

### Modified Capabilities

## Impact

- Affects new preflight/config inspection code under a Shake&Bake package and the Klipper plugin adapter that supplies live printer state.
- Affects tests and fixtures for Max 4 stock and optimized configuration snapshots.
- Provides required inputs to printer-side data-acquisition commands.
- Does not create capture files, execute printer motion, run numerical analysis, or write printer configuration.
