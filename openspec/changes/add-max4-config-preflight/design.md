## Context

Shake&Bake data acquisition targets QIDI Max 4 printers with CoreXY X/Y motion and a stock toolhead LIS2DW accelerometer. The Max 4 uses QIDI `[closed_loop x]` and `[closed_loop y]` sections for X/Y motor metadata instead of standard `[tmcXXXX stepper_x]` and `[tmcXXXX stepper_y]` sections. Stock resonance configuration uses `[resonance_tester] accel_chip: lis2dw` and `probe_points: 195,195,10`.

The Max 4 Z axis moves the bed and is not belt-driven. The toolhead accelerometer does not measure bed Z movement as a toolhead resonance signal. Preflight must reject Z-axis acquisition requests and avoid presenting Z as a calibration target.

Preflight receives data from two sources: parsed configuration files and live Klipper state. Configuration parsing can run in regular Python tests. Live state inspection runs through a narrow Klipper adapter that queries printer readiness, print state, homing state, virtual-SD state, accelerometer object availability, host load, memory, disk, fans, heaters, chamber state, and current toolhead limits.

## Goals / Non-Goals

**Goals:**

- Parse Max 4 configuration values needed for safe X/Y acquisition.
- Normalize QIDI closed-loop X/Y metadata into Shake&Bake motor metadata.
- Build a preflight result with readiness, blocking failures, warnings, and state snapshots.
- Validate X/Y planned motion envelope against configured limits and resonance probe point.
- Report host resource warnings before long acquisition commands.
- Treat Z-axis acquisition and Z-axis interpretation as unsupported behavior.

**Non-Goals:**

- No printer motion or accelerometer sampling.
- No capture artifact writing.
- No external numerical analysis.
- No automatic edits to Max 4 configuration files.
- No generic non-Max-4 kinematics support.

## Decisions

### Max 4 explicit profile

Use a `qidi_max_4` preflight profile with CoreXY X/Y behavior, LIS2DW defaults, expected config sections, and conservative safety margins. The profile accepts active config values when present and reports missing optional fields as warnings rather than inventing values.

Alternative considered: generic Klipper profile with kinematics plugins. Generic support increases parser complexity and does not improve Max 4 safety.

### Config parser boundary

Parse INI-like Klipper config sections into typed summaries for `[printer]`, `[resonance_tester]`, `[lis2dw]`, `[input_shaper]`, `[closed_loop x]`, and `[closed_loop y]`. Keep parsing independent from Klipper imports so fixtures can exercise stock and optimized Max 4 configs.

Alternative considered: query all values from live Klipper objects. Live-only parsing weakens fixture coverage and makes command failures harder to diagnose.

### Live-state adapter

Use a narrow adapter interface for live printer state. The preflight engine accepts adapter output as plain data structures and returns a plain preflight result. This keeps most preflight logic unit-testable outside Klipper.

Alternative considered: embed preflight logic directly in gcode command handlers. Command handlers would become harder to test and easier to couple to Klipper API churn.

### Failure severity

Represent findings as `blocking`, `warning`, or `info`. Blocking findings prevent acquisition. Warnings are included in command output and capture metadata. Info records state snapshots used by analyzers and operators.

Alternative considered: boolean pass/fail. A boolean loses useful state such as hot chamber, active fans, low but acceptable disk, or missing motor-current annotations.

### Z-axis handling

Return a blocking preflight finding for Z-axis acquisition requests and omit Z from supported acquisition axes. Preserve the configured accelerometer axes map as metadata because LIS2DW orientation matters for X/Y interpretation.

Alternative considered: attempt Z extrapolation through axes-map calibration. The Max 4 bed-driven Z motion does not produce a toolhead accelerometer signal suitable for Z resonance calibration.

## Risks / Trade-offs

- [Risk] QIDI firmware config names can differ across releases → Mitigation: parse by section names and field names with clear missing-field diagnostics.
- [Risk] Live Klipper APIs can change → Mitigation: isolate live calls behind the adapter and keep preflight rules pure-Python.
- [Risk] Host load checks vary across Debian builds → Mitigation: return warnings when a metric is unavailable and blocking findings only for known unsafe states.
- [Risk] A configured probe point may be inside bounds but too near travel limits for a sweep → Mitigation: validate the full planned X/Y envelope with a configurable margin.
