## 1. Package Structure

- [x] 1.1 Create the capture artifact package module, keeping it independent from Klipper and analysis packages.
- [x] 1.2 Define public read, write, and validate entry points with typed result objects.
- [x] 1.3 Add constants for supported `schema_version`, required root fields, required metadata fields, and required sample columns.

## 2. Artifact Writer

- [x] 2.1 Implement writer input models for root metadata, measurement metadata, and sample blocks.
- [x] 2.2 Implement atomic file writing through a temporary path and final rename.
- [x] 2.3 Emit optional metadata sidecar JSON when requested by the caller.
- [x] 2.4 Preserve sensor identity, axes map, planned motion envelope, input-shaper state, velocity-limit state, and fan/heater/chamber snapshots in metadata.

## 3. Artifact Reader

- [x] 3.1 Implement capture artifact parsing with explicit unsupported-schema handling.
- [x] 3.2 Preserve unknown metadata fields during read/write round trips.
- [x] 3.3 Return measurement blocks with named `time`, `accel_x`, `accel_y`, and `accel_z` columns.

## 4. Validation

- [x] 4.1 Validate required root fields and required measurement fields.
- [x] 4.2 Validate sample shape, sample count, monotonic timestamps, finite values, and nonconstant signal.
- [x] 4.3 Validate sample-rate estimate presence or derive it from timestamps when possible.
- [x] 4.4 Return structured diagnostics with status code, message, field path, and measurement name.
- [x] 4.5 Reject Z-axis calibration semantics for Max 4 capture artifacts.

## 5. Tests and Fixtures

- [x] 5.1 Add a valid Max 4 X/Y capture fixture with LIS2DW metadata.
- [x] 5.2 Add invalid fixtures for empty data, one-sample data, nonmonotonic time, non-finite samples, constant signal, missing metadata, and unsupported schema.
- [x] 5.3 Test writer atomicity by simulating a write failure before final rename.
- [x] 5.4 Test that importing the capture package does not import NumPy, SciPy, Matplotlib, zstandard, or Klipper modules.
- [x] 5.5 Test that raw capture artifacts contain no analyzer summary, graph path, report path, or proposed config content.
