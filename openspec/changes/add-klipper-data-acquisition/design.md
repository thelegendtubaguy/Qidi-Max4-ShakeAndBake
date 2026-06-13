## Context

Shake&Bake uses the Max 4 as a data-acquisition device. The printer-side plugin controls safe X/Y measurement, records raw LIS2DW accelerometer samples, and writes capture artifacts. Analysis commands run outside Klipper.

The plugin executes inside Klipper and must not import NumPy, SciPy, Matplotlib, plotting libraries, or external analyzer modules. It may import the lightweight capture artifact writer and the Max 4 preflight code. The plugin must use a narrow adapter around Klipper objects so API churn is localized.

The Max 4 is CoreXY for X/Y motion. The Z axis moves the bed and is not belt-driven. The toolhead accelerometer does not measure bed Z motion as toolhead resonance data. Plugin commands must not collect Z-axis resonance/shaper data, even when a user provides `AXIS=Z`.

## Goals / Non-Goals

**Goals:**

- Register `SHAKEANDBAKE_PREFLIGHT` and `SHAKEANDBAKE_CAPTURE_SHAPER` Klipper gcode commands.
- Execute Max 4 preflight before acquisition and refuse unsafe states.
- Capture raw X/Y accelerometer samples for input-shaper analysis.
- Write versioned capture artifacts using the capture artifact library.
- Disable input shaper during acquisition and restore all changed state through guaranteed cleanup paths.
- Restore velocity limits and other temporary motion settings after success, command error, sampling error, or motion error.
- Keep printer-side output focused on file paths, parameters, readiness, and warnings.

**Non-Goals:**

- No external shaper analysis, belt comparison, speed profiling, plotting, or report generation.
- No automatic config writes.
- No Z-axis acquisition.
- No generic printer support beyond QIDI Max 4 CoreXY with a toolhead LIS2DW accelerometer.
- No dependency installation into `klippy-env`.

## Decisions

### Command surface

Register two commands:

- `SHAKEANDBAKE_PREFLIGHT`: runs preflight and reports readiness, blocking failures, warnings, and relevant state.
- `SHAKEANDBAKE_CAPTURE_SHAPER AXIS=X|Y|ALL`: captures raw accelerometer data for X, Y, or both axes and writes one capture artifact per command invocation.

Alternative considered: command names that imply analysis such as `SHAKEANDBAKE_SHAPER`. Capture-oriented names prevent users from expecting printer-side recommendations.

### Supported axes

Support `AXIS=X`, `AXIS=Y`, and `AXIS=ALL` for shaper acquisition. Reject `AXIS=Z`, `AXIS=A`, `AXIS=B`, and arbitrary values for this command. Belt-path and static-frequency commands are separate capabilities and are not part of this command surface.

Alternative considered: accept Z and write a warning-only artifact. Rejection is safer because Z data would be misleading on Max 4.

### State restoration

Use a single acquisition context that snapshots input-shaper state, velocity limits, square-corner velocity, and supported motion settings before temporary changes. All state restoration runs from a `finally` path. Restoration failures are reported in command output and written to capture metadata when a partial artifact can be written.

Alternative considered: restore state at the end of the success path only. Success-path restoration leaves the printer in modified state after exceptions or user cancellation.

### Capture timing and writing

Record samples per requested axis as separate measurement blocks in the same capture artifact. Each block records axis, direction vector, configured parameters, start/end timestamps, sample count, and sensor identity. Capture writing uses the artifact library's atomic writer.

Alternative considered: one file per axis. A single command artifact keeps paired X/Y captures, shared state, and command parameters together.

### Klipper API adapter

Encapsulate access to `gcode`, `toolhead`, `resonance_tester`, `input_shaper`, accelerometer objects, virtual SD, and printer state behind a plugin-local adapter. The command handler coordinates preflight, acquisition lifecycle, and artifact writing without embedding low-level API details throughout the code.

Alternative considered: direct Klipper object access in command handlers. Direct access makes API changes harder to repair and makes forced-exception testing weaker.

### Motion parameters

Use active `[resonance_tester]` defaults unless command parameters explicitly override supported values. Supported parameters are `AXIS`, `FREQ_START`, `FREQ_END`, `HZ_PER_SEC`, `ACCEL_PER_HZ`, `TRAVEL_SPEED`, `ACCEL_CHIP`, and `OUTPUT_DIR`. Probe point comes from active config unless a supported safe override is added with envelope validation.

Alternative considered: many tuning knobs mirroring other tools. A small parameter surface is easier to validate and safer on constrained Max 4 hosts.

## Risks / Trade-offs

- [Risk] Klipper internal APIs differ across QIDI firmware builds → Mitigation: isolate calls in the adapter and feature-detect required capabilities during preflight.
- [Risk] Acquisition failure can leave input shaper disabled or limits modified → Mitigation: forced-exception tests must verify cleanup from each temporary state.
- [Risk] Writing large files during motion can affect timing → Mitigation: buffer samples in memory only within safe bounds and write after motion stops; include disk-space preflight.
- [Risk] Low-power host load can destabilize long tests → Mitigation: run preflight load checks and keep printer-side work free of analysis and plotting.
