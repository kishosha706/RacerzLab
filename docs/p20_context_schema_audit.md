# P20 context and control schema audit

Status: **Slice C backend verified**

Fixture: `stockcars chevycamarozl12022_atlanta 2022 oval 2026-02-17 14-41-23.ibt`

Source SHA-256: `3e347305740a5ad3d7831bec650727e49494dc28e4e031fd2820f677e7d6bccd`

The fixture is a 26,556-row Next Gen Camaro capability/running-telemetry file.
The channel declaration, units, count, and descriptions below come from its IBT
variable definitions. No absent channel or vehicle constant was inferred.

## Confirmed channel roles

| Role | Raw channels confirmed in fixture | Canonical handling |
|---|---|---|
| FFB configuration | `SteeringWheelMaxForceNm`, `SteeringWheelUseLinear`, `SteeringWheelPctIntensity`, `SteeringWheelPctSmoothing`, `SteeringWheelPctDamper`, `SteeringWheelLimiter` | Separate context aliases; values remain in their declared units/range. `SteeringWheelFFBEnabled` is absent, so the real fingerprint is limited and steering-effort comparison remains blocked. |
| Steering torque | `SteeringWheelTorque` (1 sample, N*m), `SteeringWheelTorque_ST` (6 sub-tick samples, N*m, count-as-time) | Existing 60 Hz and 360 Hz aliases remain distinct. Slice C does not flatten the sub-tick stream. |
| Raw driver control | `ThrottleRaw`, `BrakeRaw`, `ClutchRaw` | Separate raw aliases; never substituted for processed controls. |
| Processed driver control | `Throttle`, `Brake`, `Clutch`, `Shifter` | Existing processed aliases plus a shifter-input alias. Raw and processed samples remain simultaneously available. |
| Applied in-car control | `dcBrakeBias` | `applied_brake_bias`; material changes create `applied_state` mutations and split context revision. |
| Requested pit state | `dpLFTireColdPress`, `dpRFTireColdPress`, `dpLRTireColdPress`, `dpRRTireColdPress`, `dpLTireChange`, `dpRTireChange`, `dpFuelFill`, `dpFuelAddKg`, `dpFuelAutoFillEnabled`, `dpFuelAutoFillActive` | Explicit `requested_*` aliases. A request never proves applied service; confirmation requires independent artifact identities. |
| BOP compatibility | `PlayerCarWeightPenalty` (kg), `PlayerCarPowerAdjust` (%) | Exact compatibility context. A mismatch or missing value blocks setup/powertrain causal attribution but never erases observed telemetry. |
| Surface disturbance context | `PlayerTrackSurface`, `PlayerTrackSurfaceMaterial`, and four `Tire*_RumblePitch` channels (Hz) | Context aliases only. No track-surface physics or force inference is attached. |

## Real-fixture results

After a clean vectorized import, every confirmed target above materialized through
its canonical alias with row/vector parity. The file reports max FFB force
75.555557 N*m, linear mode enabled, intensity 0.5, smoothing 0.0, damper 0.0,
limiter 0.0, weight penalty 0 kg, and power adjustment 0%. FFB-enabled state is
not declared, so the fingerprint is intentionally `limited`. No applied brake-bias
or pit-request mutation occurred in this recording; stable state is not converted
into a fabricated event.

## Vehicle profile boundary

The first repository profile is identity-only. The fixture proves car path
`stockcars chevycamarozl12022`, car version `2026.01.30.02`, and iRacing build
`2026.02.02.02`. It does **not** prove wheelbase, front/rear track width, driven
axle semantics, steering conversion, sensor locations, shock sign, body axes,
damper bands, or supported setup controls, so those fields remain null/empty.

Profile hashes cover the exact immutable content. Resolution requires matching car
path, car-version range, and build range. A later profile version cannot silently
reinterpret an old artifact because profile-dependent artifacts retain both
profile ID and hash through the P20 state-frame contract.
