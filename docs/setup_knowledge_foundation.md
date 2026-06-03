# Setup Knowledge Foundation

Milestone 1 adds a local setup knowledge foundation under
`racelab_engine/knowledge/setup`.

The foundation contains typed schema models, JSON seed knowledge, a validator,
and a deterministic query matcher. It is intentionally separate from the UI,
telemetry import pipeline, public API schemas, and any AI runtime.

Seeded sections:

- Car capabilities
- Phase model
- Symptom vocabulary
- Effectiveness scale
- Setup areas
- Setup effects
- Package archetypes
- Evidence requirements
- Next Gen platform rules
- Shock interpretation rules

Next Gen rules preserve oval knowledge while disabling unsupported legacy areas:
`track_bar`, `truck_arm_mount`, `bump_stop`, and `packer`.

ARB constraints are modeled as separate setup areas for diameter, arm, preload,
and attach state. Next Gen diameter options are `1.375` and `2.000`; arm
positions are `P1` through `P5`.
