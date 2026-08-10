# P20 temporal mechanism fusion audit

Status: **Slice F backend verified**

The production path now binds qualified producer-owned observations to exact
`EngineeringStateFrame` windows using the same projected telemetry read already
owned by observation intelligence. Frames from the same run, setup, context, and
physical window may form temporal-only `StateTransition` edges and immutable
`MechanismEpisode` artifacts.

## Authority path

```text
qualified producer observation + exact telemetry citation
  -> EngineeringStateFrame
  -> temporal StateTransition
  -> observation-only MechanismEpisode
  -> typed episode MechanismObservation
  -> existing P19 evidence graph / cause ordering / planner
  -> ReasoningSnapshot.mechanism_episodes
```

The episode builder does not rank causes, select controls, create setup values,
evaluate Keep/Undo, or change authority. Its vocabulary is limited to `precedes`,
`co_occurs_with`, `responds_after`, `persists_into`, and `recovers_after`. The
existing P19 graph remains the only place episode evidence can affect cause
ordering or measurement planning.

Three deterministic mechanism-signature contracts define inspectable expected
patterns, contradictions, mind-change requirements, and measurement requirements
for center front response, brake-release/rotation response, and exit drive
response. They contain no probability or confidence field and do not match unless
all required producer mechanism kinds and the declared phase are present.

## State drift

The clean-stint drift ledger supports these per-window metrics:

- center steering demand;
- yaw-response delay;
- RF/RR slip exposure;
- throttle pickup;
- chassis response and platform clearance;
- tire surface-temperature response and running pressure;
- fuel-normalized phase time;
- driver control workload.

A finding requires three or more contiguous eligible laps, unchanged setup,
unchanged in-car control state, stable channel health, exact physical context,
comparable fuel/tire/weather/line/traffic context, an empirical noise floor, and a
same-direction shift persisting for the latest two laps. Formal statistical
change-point authority is structurally false. The output says `state_shift_observed`,
never that tire degradation or another mechanism caused the shift.

## Verification

Nine hostile tests cover exact frame binding, missing-channel denial, setup scope,
noncausal transition vocabulary, conservative independence clustering,
deterministic signatures, actual P19 graph/snapshot ingestion, persistent
above-noise drift, and fail-closed context/lap gaps. The surrounding reasoning,
observation, P3 bridge, API, and hardening suites pass (250 tests total in the
focused checkpoint).

On the 26,556-row Atlanta schema/capability fixture, the combined existing
observation plus awareness build took about 6.0 seconds cold and warm, produced 12
exact state frames, and correctly produced no transition or episode because no
qualified producer evidence repeated at one exact context. That file is not used
to validate temporal vehicle physics. Awareness remains lazy; cockpit startup is
not made dependent on this build. Slice G owns stale-safe caching and the bounded
public projection.
