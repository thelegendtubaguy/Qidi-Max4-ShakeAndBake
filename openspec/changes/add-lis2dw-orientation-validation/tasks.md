## 1. Validation Models

- [ ] 1.1 Define orientation validation request, per-axis result, diagnostics, and summary models.
- [ ] 1.2 Include configured axes map, dominant channel, polarity hint, dominance ratio, noise metric, sample-rate estimate, and status fields.
- [ ] 1.3 Define statuses for `valid`, `ambiguous`, `insufficient_signal`, `noisy`, `mismatch`, and `unavailable`.

## 2. X/Y Validation Acquisition

- [ ] 2.1 Plan short bounded X and Y toolhead moves for orientation validation.
- [ ] 2.2 Reject Z-axis validation requests before motion.
- [ ] 2.3 Run preflight and stop before motion on blocking findings.
- [ ] 2.4 Capture accelerometer samples for X and Y validation moves.
- [ ] 2.5 Restore input-shaper and velocity-limit state through cleanup paths when validation changes motion state.

## 3. Signal Analysis

- [ ] 3.1 Remove DC/gravity offset from validation samples.
- [ ] 3.2 Compute dominant accelerometer channel and polarity hint for X and Y moves.
- [ ] 3.3 Compute dominance ratio, noise metric, and sample-rate estimate.
- [ ] 3.4 Compare observations with configured axes map and record mismatch diagnostics.
- [ ] 3.5 Return ambiguity or insufficient-signal diagnostics when thresholds are not met.

## 4. Integration

- [ ] 4.1 Include configured axes map and latest orientation validation summary in preflight output.
- [ ] 4.2 Include configured axes map and latest orientation validation summary in capture metadata when available.
- [ ] 4.3 Ensure no code path reports a measured Z-axis toolhead response from Max 4 bed Z movement.

## 5. Tests

- [ ] 5.1 Add fixtures for stock axes map, inverted axes, ambiguous X/Y response, missing signal, noisy signal, and invalid Z validation requests.
- [ ] 5.2 Test X and Y dominant channel and polarity hint calculations.
- [ ] 5.3 Test mismatch diagnostics without config mutation.
- [ ] 5.4 Test preflight and capture metadata integration.
- [ ] 5.5 Test forced failures during validation acquisition to verify state restoration.
