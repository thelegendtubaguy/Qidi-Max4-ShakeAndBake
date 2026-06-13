## 1. Config Inspection Models

- [x] 1.1 Define typed summaries for printer limits, resonance tester config, LIS2DW config, input shaper config, and X/Y motor metadata.
- [x] 1.2 Implement Klipper config parsing without importing Klipper modules.
- [x] 1.3 Extract `[printer]`, `[resonance_tester]`, `[lis2dw]`, `[input_shaper]`, `[closed_loop x]`, and `[closed_loop y]` values.
- [x] 1.4 Normalize QIDI closed-loop X/Y fields into motor metadata used by reports and capture metadata.

## 2. Preflight Engine

- [x] 2.1 Define preflight request, result, finding, severity, and state snapshot models.
- [x] 2.2 Implement readiness checks for printer ready state, active print, pause state, virtual-SD activity, homing, and accelerometer availability.
- [x] 2.3 Implement planned X/Y motion envelope validation against configured bounds and safety margin.
- [x] 2.4 Implement host resource checks for load, free memory, and free disk with warning findings.
- [x] 2.5 Implement fan, heater, chamber, input-shaper, and velocity-limit snapshot collection from adapter data.
- [x] 2.6 Return a blocking finding for any Z-axis acquisition request.

## 3. Live-State Adapter Boundary

- [x] 3.1 Define an adapter interface that supplies live Klipper state as plain data structures.
- [x] 3.2 Add a test adapter for fixture-driven readiness scenarios.
- [x] 3.3 Keep preflight rule evaluation independent from Klipper imports.

## 4. Tests and Fixtures

- [x] 4.1 Add stock Max 4 config fixture with CoreXY, LIS2DW, resonance tester, input shaper, and QIDI closed-loop X/Y sections.
- [x] 4.2 Add optimized Max 4 config fixture if available in local project context.
- [x] 4.3 Test parsing of closed-loop X/Y metadata when standard X/Y TMC sections are absent.
- [x] 4.4 Test ready, active print, paused, virtual-SD active, homing, not-ready, accelerometer-missing, low-resource, and out-of-bounds scenarios.
- [x] 4.5 Test that supported axes are X and Y only and Z-axis requests are blocking failures.
