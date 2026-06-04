# Setup Knowledge Digest Report

Generated from reviewed local JSON records derived from the RacerZLab master setup matrix.

## Guide Sources
- iracing_setup_guide: iRacing Setup Guide (reviewed)
- nascar_nextgen_manual: NASCAR Next Gen Manual Notes (reviewed)
- shock_tuning_user_guide: Shock Tuning User Guide Concepts (reviewed)
- lowline_oval_setup_guide: Lowline Oval Setup Guide Concepts (reviewed)
- oval_setup_matrix_v4: Oval Setup Matrix v4 (reviewed)
- oval_setup_matrix_v5: Oval Setup Matrix v5 (reviewed)
- oval_setup_flowchart: Oval Setup Flowchart (reviewed)
- racerzlab_research_report: RacerZLab Research Report (reviewed)
- user_diffuser_front_feed_notes: User Diffuser Front Feed Notes (reviewed)
- racerzlab_master_setup_matrix_v1: RacerZLab Master Setup Matrix v1 (accepted)

## Accepted Principles
- Baseline first: Baseline first.
- One change at a time: One swing, then compare.
- Every change has a counter-effect: Show the tradeoff.
- Validate comparable windows: Compare like with like.
- Do not judge cold or out laps: Do not judge cold laps.
- Fast setups are packages: Read the whole package.
- Static is not dynamic: Static setup is not telemetry.
- Proxy is not measurement: Proxy is not downforce.
- Save the lesson: Save helped/hurt lessons.
- Exit grip first, entry balance second, driver feel last: Exit first, entry second, feel last.
- One small swing language: Effect, counter-effect, watch, validate.
- Tire pressure follows load and tire evidence: Pressure needs tire evidence.
- Brake bias can mask entry balance: Check chassis before bias.
- Driver preference levers are not first-response fixes: Preference levers need context.
- Spring changes require platform reset checks: Reset platform after springs.
- Legacy travel and rear-geometry levers stay gated: Legacy levers stay gated.
- Next Gen ARB P settings are small tuning swings: P-step small, diameter big.

## Terms
- Term definitions: 74

## Setup Areas
- Setup areas: 55
- alignment: 1
- anti_roll_bar: 8
- brakes: 1
- driveline: 2
- evidence: 9
- platform: 6
- rear_suspension: 2
- setup: 13
- shocks: 6
- springs: 2
- steering: 1
- tires: 2
- weights: 2

## Setup Area Types
- derived_proxy: 2
- live_telemetry: 8
- mixed: 6
- static_setup: 39

## Setup Effects By System
- alignment: 4
- anti_roll_bar: 14
- brakes: 2
- driveline: 5
- platform: 11
- rear_suspension: 3
- setup: 3
- shocks: 25
- springs: 10
- steering: 1
- tires: 12
- weights: 2

## Effect Strength Summary
- Strength 2: 19
- Strength 3: 48
- Strength 4: 20
- Strength 5: 5

## Counter-Effect Summary
- Effects with counter-effect text: 92

## Car Capability Gates
- Next Gen disabled areas: track_bar, truck_arm_mount, bump_stop, packer
- Legacy oval keeps those areas as car-specific knowledge.

## Next Gen ARB Constraints
- Diameter: 1.375, 2.000
- Arm positions: P1, P2, P3, P4, P5

## Next Gen Diffuser / Front Feed Rules
- Front and rear platform wording: Front ride-height platform helps define diffuser feed. Rear ride-height platform helps define diffuser outlet/expansion and scrape/choke behavior. Diffuser metrics are derived geometry proxies, not measured downforce.
- CFS and front feed matter: CFS/front ride-height platform evidence matters because the front platform helps define diffuser feed; read it with rear platform, scrape, speed loss, and derived diffuser proxy context.
- Rear height is not alone: Rear height alone does not determine rear aero behavior; read it with front feed, diffuser outlet/expansion context, scrape, and speed loss.
- Front higher is contextual: A front platform that is higher than the rear is not automatically wrong; the useful question is whether the feed, scrape margin, and speed trend agree.
- Lower is contextual: Lower is not automatically faster if it creates contact, unstable feed, or speed loss.
- Proxy is not downforce: Diffuser proxy channels are geometry-derived indicators for comparison and are not measured downforce.
- Inspect combined platform: Inspect CFS/front ride-height platform, rear ride-height platform, smooth rake, diffuser volume proxy, scrape, and speed loss together before naming a platform direction.
- Static rake is not enough: Do not suggest ride-height, collar, or spring changes from static rake alone; require platform trace, scrape, and speed context.
- Smooth rake context: Smooth rake is useful context only when combined with CFS/front platform, rear platform, diffuser volume proxy, scrape, and speed loss.
- Static rake sign is not the answer: Static rake sign does not decide if a setup is good; inspect dynamic traces by zone with speed loss and scrape context.
- Inspect dynamic traces by zone: Inspect platform, shock, tire, speed, and yaw traces in the same corner zone before naming a setup direction.

## Shock Interpretation Rules
- Compression: Bump / compression means the shock is shortening.
- Rebound: Rebound (extension) means the shock is extending.
- Low-speed shock range: Low-speed shock movement is the driver/platform movement region.
- High-speed shock range: High-speed shock movement is the track/bump movement region.
- Shock histogram: A shock histogram is a live movement signature: the percent of valid samples in shaft velocity bins. It is evidence, not a command by itself.
- Shock change strength: Shock changes are often fine tuning unless selected-zone evidence points to bumps, transitions, or platform control.
- Shock comparison discipline: Use same bins, same selected zone, same lap window, and same scale when comparing shock histograms.

## Oval Matrix-Derived Condition Mapping
- loose_overall: cross_weight / add stability/security
- tight_overall: cross_weight / free balance/bind
- loose_entry: brake_bias / add front brake bias
- tight_entry: brake_bias / reduce front brake bias
- loose_center: rear_arb_arm / move rear ARB arm toward P5/stiffer/tighter or add rear security
- tight_center: cross_weight / reduce bind/free center
- loose_exit: cross_weight / add exit security
- tight_exit: diff_preload / free center-off/driveline bind
- low_straight_speed: toe / reduce scrub after normalizing exit speed
- long_run_falloff: tire_pressure / protect tire trend
- rear_scrape: rear_ride_height_platform / add rear scrape margin
- front_platform_contact: front_ride_height_platform / add front contact margin
- diffuser_instability: diffuser_platform / inspect platform/diffuser window
- shock_overactive: hs_compression / tune bump/compliance only with shock evidence
- tire_overwork: camber / protect tire contact and temperature trend
- poor_drive_off: diff_preload / tune connected throttle pickup
- loose_center: rear_toe_stability / inspect rear toe stability before changing larger balance levers
- brake_entry_instability: brake_bias / use brake bias only after checking chassis entry evidence
- tight_entry: caster / tune caster split as a driver/track feel lever
- tire_overwork: camber / read camber through contact patch and temperature spread
- platform_instability: spring_rate / recheck ride height and camber after spring changes
- tight_center: front_arb_arm / move front ARB arm one P-position toward P1/softer/looser
- loose_center: front_arb_arm / move front ARB arm one P-position toward P5/stiffer/tighter
- loose_exit: rear_arb_arm / move rear ARB arm one P-position toward P5/stiffer/tighter
- tight_exit: rear_arb_arm / move rear ARB arm one P-position toward P1/softer/looser

## Flowchart Process Logic
- Exit grip first, entry balance second, driver feel last.
- One change at a time with comparable-window validation.

## Package Archetypes
- low_platform_speed_package: Low platform speed package
- front_feed_diffuser_package: Front feed diffuser package
- high_front_low_rear_diffuser_feed_package: High-front low-rear feed package
- high_cross_stability_package: High cross stability package
- free_center_rotation_package: Free center rotation package
- long_run_tire_protection_package: Long-run tire protection package
- qualifying_speed_package: Qualifying speed package
- pack_stability_package: Pack stability package
- bumpy_track_compliance_package: Bumpy track compliance package
- shock_controlled_platform_package: Shock-controlled platform package
- spring_controlled_platform_package: Spring-controlled platform package
- arb_led_package: ARB-led package
- tire_pressure_support_package: Tire pressure support package
- toe_scrub_speed_package: Toe-scrub speed package
- legacy_track_bar_rotation_package: Legacy track-bar rotation package

## Needs-Review Items
- cfs_half_inch_opening_claim: User reports the CFS/front platform may include an approximately 0.5 inch opening/clearance feature that helps feed airflow toward the diffuser. Needs verification before being encoded as fact.

## Validation Status
passed
