# P20 whole-car response and exposure audit

Status: **Slice E backend verified**

Fixture: `stockcars chevycamarozl12022_atlanta 2022 oval 2026-02-17 14-41-23.ibt`

Source SHA-256: `3e347305740a5ad3d7831bec650727e49494dc28e4e031fd2820f677e7d6bccd`

The six metrics in this slice are immutable, exact-window, observation-only
artifacts. Each carries a formula version, producer provenance, explicit allowed
outputs, and forbidden claims. A junk lap, unhealthy clock, incomplete coverage,
or missing continuous input blocks production.

## Authority boundaries

| Artifact | It may describe | It cannot claim |
|---|---|---|
| Chassis response matrix | ride-height motion response proxies and four-corner shock-velocity distributions | load transfer, wheel load, dynamic crossweight, spring/ARB/tire force |
| Relative slip-distance exposure | integrated expected-versus-observed wheel-speed difference | tire force, grip, friction, wear, energy, or power loss |
| Brake pressure-velocity exposure | integrated line pressure times absolute wheel velocity | brake torque/force/energy, rotor temperature, or pad friction |
| Tire thermal response | continuously updating surface-temperature, pressure, and odometer changes | exact thermal energy/heat flux/friction, optimum pressure, safe threshold, or snapshot trend |
| Combined-acceleration occupancy | observed body-axis acceleration distributions | friction circle, grip utilization, friction coefficient, or compensated available grip |
| Track disturbance signature | repeated position-locked input/response sequence | track cause, damper recommendation/regime, wheel load, or setup cause |

Corner slip correction is fail-closed. Straights can use vehicle speed as the
declared straight-line reference. Corner windows require source-backed front/rear
track widths plus verified wheel-speed and body-axis conventions. Disturbance
signatures require two or more distinct eligible laps at the same backend-owned
physical window and preserve track-input, vehicle-response, driver-response, and
performance-consequence statements separately.

## Next Gen schema/capability fixture result

The production vectorized import produced 26,556 rows. This low-speed Atlanta file
is classified as a **schema/capability fixture**, not a controlled performance or
physics-validation run. An executable-path check on an exact 40.0-41.0%
lap-distance window on canonically eligible lap 4 showed:

- chassis response produced a limited descriptor with four-corner distributions;
  classification remained unavailable because the identity-only Next Gen profile
  contains no proven shock sign or damper bands;
- straight-line relative slip-distance, brake pressure-velocity, and raw combined
  acceleration descriptors were ready;
- tire thermal response was limited but usable from continuous surface,
  pressure, and odometer channels; carcass and wear snapshots were excluded;
- corner-corrected slip stayed blocked because track widths and channel/body-axis
  semantics are not proven by the fixture;
- the same position window on eligible laps 4 and 5 exercised repeated-signature
  construction without generating a damper action or setup cause. Because the
  track input is not directly measured, the signature says so explicitly.

These results validate archive capability, channel/update-semantic gates, exact
scope, and fail-closed behavior. They do **not** validate corner dynamics, tire
behavior, powertrain pull, chassis response, aero/platform behavior, or the
physical significance of the calculated values. Those require a declared running
telemetry or controlled fixture role.

Nine hostile tests cover these authority boundaries, profile gates, snapshot
exclusion, row/frame parity, repeated-lap identity, and junk-lap denial. Focused
Ruff and model compilation also pass.
