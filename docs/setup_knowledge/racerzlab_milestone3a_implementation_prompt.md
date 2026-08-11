# RacerZLab Milestone 3A Implementation Prompt  
## Use with `racerzlab_master_setup_matrix.md`

> **Archived implementation prompt - non-production.** This records a completed
> historical milestone and is not an executable current product contract. Old
> directional query workflows are superseded: public Dial-In is non-directional
> and P19 is the sole setup, Keep/Undo, and stop-testing authority.

You are working inside RacerZLab. Read `docs/setup_knowledge/racerzlab_master_setup_matrix.md` first. Treat that markdown as the consolidated source of setup knowledge for this milestone. Do not expect setup information from any other source during implementation.

## Mission

Implement a source-backed setup guide digestion layer that converts the consolidated master setup matrix into structured, local, deterministic RacerZLab knowledge records.

This is **not** the crew-chief UI yet.  
This is **not** runtime AI.  
This is **not** API integration.  
This is the knowledge digestion layer that lets RacerZLab load, validate, query, and trace setup guide knowledge.

## Current state

Milestone 1 and Milestone 2 already created:

```text
racelab_engine/knowledge/setup/
  schema.py
  loader.py
  matcher.py
  validator.py
  data/*.json

scripts/validate_setup_knowledge.py
tests/test_setup_knowledge.py
docs/setup_knowledge_foundation.md
```

Milestone 2 added dynamic ranking, richer schema fields, evidence readiness, package archetypes, Next Gen gates, ARB constraints, effect/counter-effect language, and readable CLI output.

## Hard rules

- No runtime AI.
- No API keys.
- No external calls.
- No crew-chief chat UI.
- No telemetry formula changes.
- No import pipeline changes.
- No public API/schema changes.
- Do not copy guide source text verbatim into app UI.
- Use RacerZLab-owned wording from the master setup matrix.
- Do not recommend exact setup values as universal truth.
- Do not judge one setup value alone.
- Do not confuse static garage setup values with live telemetry.
- Do not claim measured downforce from diffuser/platform proxies.
- Do not recommend multiple major setup changes as one test.
- Every setup swing must include effect, counter-effect, evidence required, and validation targets.
- Runtime must remain local and deterministic.
- Driver-facing wording should sound like a crew chief, not a robotic AI report.

## Primary source file

Use:

```text
docs/setup_knowledge/racerzlab_master_setup_matrix.md
```

Also support optional local ingestion copy:

```text
data/knowledge/source_guides/racerzlab_master_setup_matrix.md
```

## Create / update files

```text
racelab_engine/knowledge/setup/source_loader.py
racelab_engine/knowledge/setup/source_digest.py
racelab_engine/knowledge/setup/source_mapper.py
racelab_engine/knowledge/setup/schema.py
racelab_engine/knowledge/setup/validator.py
racelab_engine/knowledge/setup/data/guide_sources.json
racelab_engine/knowledge/setup/data/guide_principles.json
racelab_engine/knowledge/setup/data/guide_term_definitions.json
racelab_engine/knowledge/setup/data/guide_setup_mappings.json
racelab_engine/knowledge/setup/data/guide_review_queue.json
racelab_engine/knowledge/setup/data/guide_digest_manifest.json
data/knowledge/source_guides/README.md
data/knowledge/source_guides/.gitkeep
scripts/digest_setup_guides.py
scripts/query_guide_knowledge.py
scripts/export_setup_knowledge_digest.py
tests/test_setup_guide_digest.py
docs/setup_guide_digest.md
docs/generated/setup_knowledge_digest_report.md
```

Do not break existing Milestone 1/2 files or query behavior.

---

# Phase 1 — Source/provenance schema

Add source-backed models.

## GuideSource

Fields:

```text
source_id
title
source_type: manual | guide | cheat_sheet | matrix | flowchart | user_note | research_report
domain: oval | road | general | shock | aero_platform | tires | setup_process
car_scope: next_gen | legacy_oval | road | all | unknown
file_name
local_path
page_refs
status: raw | extracted | reviewed | accepted | rejected
notes
```

## GuidePrinciple

Fields:

```text
principle_id
source_ids
title
racerzlab_wording
source_summary
domain
car_scope
setup_areas
phases
symptoms
evidence_links
confidence: low | medium | high
review_status: proposed | accepted | needs_review | rejected
cautions
do_not_overclaim
short_ui_wording
why_it_matters
mistakes_to_avoid
```

## GuideTermDefinition

Fields:

```text
term_id
term
aliases
canonical_term
definition
domain
phase_hint
symptom_hint
evidence_hint
car_scope
source_ids
review_status
clarification_question
```

## GuideSetupMapping

Fields:

```text
mapping_id
source_ids
setup_area
symptom
phase
direction
intended_effect
counter_effect
effect_strength
coupling_risk
evidence_required
validation_targets
applies_to
disabled_for
exact_value_policy
review_status
preferred_when
avoid_when
watch_for
```

## GuideReviewItem

Fields:

```text
review_id
item_type
source_ids
proposed_record
reason
risk
status
reviewer_notes
safe_wording
verification_needed
```

## GuideDigestManifest

Fields:

```text
digest_version
created_at
source_count
principle_count
term_count
mapping_count
accepted_count
needs_review_count
rejected_count
notes
```

---

# Phase 2 — Source guide policy

Create `data/knowledge/source_guides/README.md`.

Explain:

- Raw guide files are local development/reference inputs.
- Runtime uses reviewed JSON records under `racelab_engine/knowledge/setup/data`.
- Do not blindly copy source tables into the UI.
- The master matrix markdown is RacerZLab-owned consolidated knowledge.
- PDFs/images may stay local if desired.
- Commit reviewed derived knowledge, not raw copyrighted/unreviewed files unless intended.
- Future ingestion can read markdown/json/text extracts from this folder.

---

# Phase 3 — Guide source manifest

Create `guide_sources.json`.

Include at least:

1. `iracing_setup_guide`
2. `nascar_nextgen_manual`
3. `shock_tuning_user_guide`
4. `lowline_oval_setup_guide`
5. `oval_setup_matrix_v4`
6. `oval_setup_matrix_v5`
7. `oval_setup_flowchart`
8. `racerzlab_research_report`
9. `user_diffuser_front_feed_notes`
10. `racerzlab_master_setup_matrix_v1`

The master setup matrix source should point to:

```text
docs/setup_knowledge/racerzlab_master_setup_matrix.md
```

---

# Phase 4 — Guide principles

Create `guide_principles.json`.

Must include accepted principles from the master matrix:

1. Baseline first.
2. One change at a time.
3. Every change has a counter-effect.
4. Validate by comparable windows.
5. Do not judge cold/out laps.
6. Fast setups are packages.
7. Static is not dynamic.
8. Proxy is not measurement.
9. Save the lesson.
10. Exit grip first, entry balance second, driver feel last.
11. One small swing language.

Each principle must include:

```text
source_ids
racerzlab_wording
short_ui_wording
why_it_matters
mistakes_to_avoid
review_status
```

---

# Phase 5 — Term definitions

Create or enrich `guide_term_definitions.json`.

Must include terms from the master matrix:

## Driver language

```text
tight
push
loose
free
entry
center
exit
drive off
bound up
scrub
drag
falls off
bottoming
splitter hitting
rear scrape
pack unstable
```

## Platform / aero / diffuser

```text
platform
static ride height
dynamic ride height
front ride-height platform
rear ride-height platform
CFS / center front splitter / front rub-block reference
front feed
diffuser feed
diffuser outlet
diffuser expansion
diffuser proxy
front platform contact
rear scrape
```

## Setup systems

```text
cross weight
nose weight
ARB / sway bar
front_arb_diameter
front_arb_arm
front_arb_preload
rear_arb_diameter
rear_arb_arm
rear_arb_preload
spring rate
shock collar / perch
tire pressure
pressure gain
camber
caster
toe
brake bias
diff preload
final drive
track bar
truck arm
bump stop
packer
```

## Dampers

```text
bump / compression
rebound
low-speed damping
high-speed damping
shock shaft velocity
shock histogram
average rebound
average bump
load variation
overdamped
underdamped
digressive
linear
progressive
slope
HS slope
```

---

# Phase 6 — Guide setup mappings

Create or enrich `guide_setup_mappings.json`.

Use the master matrix to encode condition → setup area → direction family.

Do not paste tables. Create structured mappings.

Condition groups required:

```text
loose_overall
tight_overall
loose_entry
tight_entry
loose_center
tight_center
loose_exit
tight_exit
low_straight_speed
long_run_falloff
rear_scrape
front_platform_contact
diffuser_instability
shock_overactive
tire_overwork
poor_drive_off
```

Each mapping must have:

```text
setup_area
symptom
phase
direction
intended_effect
counter_effect
effect_strength
coupling_risk
evidence_required
validation_targets
applies_to
disabled_for
review_status
source_ids
```

---

# Phase 7 — Enrich setup areas

Update `setup_areas.json` using the master matrix.

Must include categories:

```text
tire_pressure
pressure_split
pressure_gain
tire_temp_spread
tire_wear
camber
caster
toe
front_toe_response
rear_toe_stability
ride_height
front_ride_height_platform
rear_ride_height_platform
CFS/front_splitter/rub_block_reference
shock_collar
spring_perch
diffuser_platform
platform_contact
rear_scrape
front_platform_contact
spring_rate
front_spring_support
rear_spring_support
spring_split
cross_weight
nose_weight
corner_weight
ballast
front_arb_diameter
front_arb_arm
front_arb_preload
front_arb_attach
rear_arb_diameter
rear_arb_arm
rear_arb_preload
rear_arb_attach
brake_bias
front_master_cylinder
rear_master_cylinder
ls_compression
hs_compression
hs_comp_slope
ls_rebound
hs_rebound
hs_reb_slope
shock_histogram
shock_velocity_rms
shock_deflection_delta
diff_preload
final_drive
gear_ratio
track_bar
truck_arm_mount
bump_stop
packer
```

Next Gen must disable:

```text
track_bar
truck_arm_mount
bump_stop
packer
```

Legacy oval generic may include those as `car_specific`.

---

# Phase 8 — Enrich setup effects

Update `setup_effects.json` from the master matrix.

Every effect must include:

```text
driver_phrase
effect
counter_effect
primary_effects
counter_effects
helps
can_hurt
helps_phases
can_hurt_phases
effect_strength
coupling_risk
evidence_required
validation_targets
watch_for_targets
one_change_test_template
exact_value_policy
applies_to
disabled_for
source_ids
review_status
```

Required effect families:

## Tires

```text
add_left_rear_pressure_small
reduce_left_front_pressure_small
add_right_front_pressure_support
reduce_right_front_pressure_grip
pressure_split_stability_swing
long_run_pressure_protection
```

## Springs/platform/collars

```text
add_crossweight_small
reduce_crossweight_small
add_rf_spring_small
reduce_rf_spring_small
add_lr_spring_support
reduce_lr_spring_for_drive
spring_package_platform_support
spring_package_compliance
add_front_platform_support
reduce_front_platform_support
add_rear_platform_support
reduce_rear_platform_support
improve_front_feed_window
inspect_diffuser_choke_or_scrape
reduce_platform_contact_small
avoid_static_rake_only_call
```

## ARB

```text
soften_front_arb_arm_one_position
stiffen_front_arb_arm_one_position
switch_front_arb_to_soft_bar
switch_front_arb_to_stiff_bar
soften_rear_arb_arm_one_position
stiffen_rear_arb_arm_one_position
adjust_front_arb_preload_small
adjust_rear_arb_preload_small
```

Rules:

- ARB diameter = package-level / high coupling.
- ARB arm = tuning swing.
- ARB preload = detail/load swing.
- ARB attach = procedure/diagnostic, not default recommendation.

## Brakes / diff / gearing

```text
add_front_brake_bias_small
reduce_front_brake_bias_small
increase_diff_preload
reduce_diff_preload
shorter_final_drive
taller_final_drive
```

## Shocks

```text
add_lf_ls_rebound
reduce_lf_ls_rebound
add_rf_ls_compression
reduce_rf_ls_compression
add_rear_ls_rebound
reduce_rear_ls_rebound
add_rear_ls_compression
reduce_rear_ls_compression
add_hs_compression_for_bumps
reduce_hs_compression_for_compliance
add_hs_rebound_control
reduce_hs_rebound_recovery
slope_more_linear_bumpy
slope_more_digressive_smooth
```

## Toe/camber/caster

```text
reduce_front_toe_scrub
add_front_response_toe_swing
add_rear_toe_stability
reduce_rear_toe_bind
camber_for_center_grip
reduce_camber_for_long_run
caster_driver_feel_entry
```

## Legacy oval only

```text
raise_track_bar_legacy
lower_track_bar_legacy
truck_arm_mount_legacy_swing
bump_stop_or_packer_legacy_support
packer_height_legacy_swing
```

These must not return for Next Gen.

---

# Phase 9 — Next Gen platform / diffuser / CFS rules

Update `nextgen_platform_rules.json`.

Must include:

```text
front ride-height platform helps define diffuser feed
CFS/front feed matters
rear ride-height platform helps define diffuser outlet/expansion/scrape/choke context
rear height alone does not determine rear aero behavior
front higher than rear is not automatically wrong
lower is not automatically faster
static rake sign does not decide if a setup is good
diffuser proxy is not measured downforce
inspect dynamic traces by zone
```

Use exact safe wording:

```text
Front ride-height platform helps define diffuser feed. Rear ride-height platform helps define diffuser outlet/expansion and scrape/choke context. Diffuser metrics are derived geometry proxies, not measured downforce.
```

Create `guide_review_queue.json` item for CFS:

```text
User reports the CFS/front platform may include an approximately 0.5 inch opening/clearance feature that helps feed airflow toward the diffuser. Needs verification before being encoded as fact.
```

Status: `needs_review`.

Do not accept as fact.

---

# Phase 10 — Shock interpretation rules

Update `shock_interpretation.json`.

Must encode:

```text
bump/compression = shock shortening
rebound = shock extending
low-speed = driver-input/body-motion region
high-speed = bumps/track-impact region
shock histogram = percent of valid samples in shaft velocity bins
whole-lap histogram should not overrule selected-zone evidence
shock changes are often fine tuning unless evidence points to bumps/transitions/platform control
```

Guardrails:

```text
Histogram is evidence, not a command.
Do not say the histogram proves the shock is wrong.
Do not say add rebound because the bar is tall.
Use same bins, same zone, same lap window, same scale.
```

---

# Phase 11 — Package archetypes

Update `package_archetypes.json`.

Must include:

```text
low_platform_speed_package
front_feed_diffuser_package
high_front_low_rear_diffuser_feed_package
high_cross_stability_package
free_center_rotation_package
long_run_tire_protection_package
qualifying_speed_package
pack_stability_package
bumpy_track_compliance_package
shock_controlled_platform_package
spring_controlled_platform_package
arb_led_package
tire_pressure_support_package
toe_scrub_speed_package
legacy_track_bar_rotation_package
```

Each archetype must include:

```text
what_it_looks_like
why_fast
common_risks
compensators
failure_modes
likely_driver_complaints
diagnostic_questions
recommended_evidence_order
setup_areas_involved
driver_facing_explanation
applies_to
disabled_for
source_ids
```

---

# Phase 12 — Evidence requirements

Update `evidence_requirements.json`.

Evidence groups:

```text
driver complaint
selected lap/window
track map zone
setup snapshot
compare baseline/test
front ride-height platform
CFS/front feed
rear ride-height platform
diffuser proxy
rear scrape/scrub
tire temps
tire pressure gain
tire wear
shock histogram
shock RMS/activity
yaw/scrub/steering
speed loss
brake trace
throttle pickup
RPM/gear/limiter
driver survey result later
```

Readiness labels:

```text
ready
partially_ready
missing_key_evidence
```

Human messages:

```text
Need a clean center-zone window before calling this a setup swing.
Need live shock histogram before ranking shock changes high.
Need setup snapshot before comparing static garage levers.
Need Compare baseline before saying it worked.
Need front/rear ride-height traces before making platform/diffuser calls.
```

---

# Phase 13 — Query scripts

## `query_guide_knowledge.py`

Support:

```text
--source-id
--topic
--setup-area
--symptom
--car-family
--json
```

Example:

```bash
python -B scripts/query_guide_knowledge.py --setup-area ls_rebound --car-family next_gen
python -B scripts/query_guide_knowledge.py --topic diffuser --car-family next_gen
```

Output:

```text
term definitions
related principles
setup effects
source_ids
cautions
car applicability
review status
```

## `export_setup_knowledge_digest.py`

Generate:

```text
docs/generated/setup_knowledge_digest_report.md
```

Sections:

```text
guide sources
accepted principles
terms
setup areas
setup effects by system
effect strength summary
counter-effect summary
car capability gates
Next Gen disabled/available areas
Next Gen ARB constraints
Next Gen diffuser/front-feed rules
shock interpretation rules
oval matrix-derived condition mapping
flowchart process logic
package archetypes
needs-review items
validation status
```

---

# Phase 14 — Validator updates

Validator must fail if:

```text
any source_id referenced does not exist
any accepted principle lacks RacerZLab-owned wording
any accepted record contains long copied source text
any setup effect lacks source_ids
any exact numeric delta lacks exact_value_policy small_swing or reference_only
any Next Gen effect references track_bar/truck_arm_mount/bump_stop/packer
any disabled legacy area lacks car-specific availability
any record claims measured downforce from diffuser/proxy
any record says guaranteed fix
any record says always except safe phrases like not always
CFS 0.5 feature is accepted without verification
shock histogram is sole proof of setup change
Next Gen ARB diameter options are not exactly 1.375 and 2.000
Next Gen ARB arms are not exactly P1-P5
any effect lacks counter-effect
any effect lacks validation target
any effect lacks evidence requirement
any effect returns multiple major package changes as one test
```

---

# Phase 15 — Tests

Create/update `tests/test_setup_guide_digest.py`.

Required tests:

1. guide sources load
2. every referenced source_id exists
3. guide principles load
4. term definitions load
5. setup mappings/effects link to setup areas
6. no accepted record has forbidden guarantee wording
7. no accepted diffuser record claims measured downforce
8. CFS 0.5 inch claim is needs_review unless verified
9. Next Gen disabled areas remain disabled
10. legacy oval can keep legacy areas
11. ARB discrete options remain exact
12. query guide knowledge by setup area returns source-backed records
13. export digest report runs
14. setup knowledge validator validates guide digest files
15. oval matrix condition groups exist for loose/tight entry/center/exit
16. setup flowchart principles exist for exit-first / entry-second / driver-feel-last
17. every setup effect has source_ids
18. every setup effect has effect/counter-effect
19. generic loose/tight asks clarification
20. Next Gen query never returns track_bar/truck_arm/bump_stop/packer

---

# Validation commands

Run all:

```bash
python -B scripts/validate_setup_knowledge.py
python -B scripts/query_guide_knowledge.py --setup-area ls_rebound --car-family next_gen
python -B scripts/query_guide_knowledge.py --topic diffuser --car-family next_gen
python -B scripts/export_setup_knowledge_digest.py
python -B -m pytest tests/test_setup_knowledge.py tests/test_setup_guide_digest.py -q
python -B -m pytest -m "not slow and not integration" -q --durations=25
powershell -ExecutionPolicy Bypass -File scripts/audit_local_only.ps1
```

---

# Final report required

Report:

```text
files changed
guide source model added
source records added
guide principles added
oval matrix concepts added
flowchart concepts added
term definitions added
setup mappings/effects enriched
effect/counter-effect expansion summary
package archetypes enriched
Next Gen capability gates confirmed
Next Gen ARB constraints confirmed
CFS 0.5 inch handled as verified or needs_review
source traceability behavior
new query examples
digest report generated
validation results
skipped/risky items
recommended commit message
```

Recommended commit message:

```text
Add source-backed setup guide digestion layer
```
