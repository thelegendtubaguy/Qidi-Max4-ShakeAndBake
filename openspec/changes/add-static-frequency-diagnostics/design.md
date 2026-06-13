## Context

Static-frequency diagnostics excite a supported direction at one frequency for a bounded duration. The operator can listen or touch printer components to locate resonance sources such as toolhead parts, belts, panels, gantry elements, fans, ducts, or cable chains. Optional recording writes raw accelerometer samples for external spectrogram and energy-over-time analysis.

The Max 4 supports X, Y, and CoreXY belt-path directions A and B. The Z axis is bed-driven and not a supported excitation axis for Shake&Bake diagnostics.

## Goals / Non-Goals

**Goals:**

- Register `SHAKEANDBAKE_EXCITE` with `AXIS=X|Y|A|B`, `FREQUENCY`, `DURATION`, and `RECORD=0|1`.
- Validate parameters, planned X/Y envelope, and printer readiness before excitation.
- Disable input shaper during excitation and restore state through cleanup paths.
- Optionally record accelerometer samples into a versioned raw capture artifact.
- Provide external static-frequency analysis for recorded captures.

**Non-Goals:**

- No Z-axis excitation.
- No automatic diagnosis claim from the printer-side command.
- No shaper, belt-comparison, or speed-profile recommendation.
- No config edits.

## Decisions

### Axis mapping

Map `X` and `Y` to toolhead axis directions. Map `A` to CoreXY direction `(1, -1, 0)` and `B` to `(1, 1, 0)`. Store the logical axis and direction vector when recording is enabled.

Alternative considered: allow arbitrary vector input. Named axes are easier to validate and safer from gcode.

### Fixed-frequency motion

Generate repeated acceleration pulses at the requested frequency for the requested duration, using configured acceleration-per-Hz behavior and validated travel bounds. Record actual planned values in command output and capture metadata.

Alternative considered: reuse sweep acquisition. Fixed-frequency excitation serves a different diagnostic workflow: localizing a known suspicious frequency.

### Optional recording

When `RECORD=1`, record accelerometer samples and write a capture artifact with `tool: static-frequency`. When `RECORD=0`, no capture artifact is written and command output reports only excitation completion and warnings.

Alternative considered: always record. Recording increases file I/O and is unnecessary when the operator only needs physical localization.

### External analysis

The external analyzer reads static-frequency captures and writes spectrogram plus cumulative energy-over-time outputs. It validates captures before analysis and handles graph failures separately from JSON output.

Alternative considered: generate spectrograms in Klipper. Plotting and FFT work do not belong in the printer process.

## Risks / Trade-offs

- [Risk] A fixed frequency can strongly excite a loose component → Mitigation: bound duration, validate motion envelope, and report operator-visible parameters before excitation.
- [Risk] User requests unsafe frequency or duration → Mitigation: parameter validation enforces configured limits.
- [Risk] Recording failure can occur after excitation → Mitigation: restore motion state independently and report recording failure distinctly.
