"""Controlled A/B/A setup-test planning and execution scoring.

The director never invents a setup value and never treats a telemetry row as an
experiment.  It produces one legal control test or a concrete measurement
mission when the evidence is not ready.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    assess_setup_change,
    canonical_setup_value_key,
    expected_control_effect,
    format_setup_value,
    setup_control_values_equal,
    setup_target_increment_blocker,
    setup_value_numeric_representation,
)


class DirectorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MeasurementMission(DirectorModel):
    purpose: str
    procedure: tuple[str, ...]
    required_laps_or_passes: int = Field(ge=1)
    controlled_variables: tuple[str, ...]
    target_phase: str
    acceptance_thresholds: tuple[str, ...]
    stop_rule: str
    blockers: tuple[str, ...]


class TestEvidenceLink(DirectorModel):
    __test__: ClassVar[bool] = False

    event_id: str = Field(min_length=1)
    eligible_lap: bool
    valid_for_tuning: bool
    phase: str
    related_setup_keys: tuple[str, ...]


class TestStage(DirectorModel):
    stage: Literal["A", "B", "A2"]
    setup_instruction: str
    warmup_laps: int = Field(ge=0)
    required_flying_laps: int = Field(ge=1)
    purpose: str


class ControlledTestCard(DirectorModel):
    hypothesis: str
    control_key: str
    control_label: str
    direction_sign: Literal[-1, 1]
    current_value: Any = None
    proposed_value: str | None = None
    proposed_value_raw: Any = None
    proposed_value_provenance: tuple[str, ...] = ()
    exact_change: str
    change_size: str
    target_phase: str
    expected_mechanism: str
    success_metrics: tuple[str, ...]
    countereffects: tuple[str, ...]
    rollback_rule: str
    keep_rule: str
    stop_rule: str = (
        "Stop the stage after a pit entry, reset, caution, incident, simulator-integrity fault, "
        "unexpected contact, or unsafe handling; discard contaminated laps and restore A before continuing."
    )
    stages: tuple[TestStage, TestStage, TestStage]
    evidence_event_ids: tuple[str, ...]
    do_not_change: tuple[str, ...]

    @model_validator(mode="after")
    def require_aba_and_one_control(self) -> ControlledTestCard:
        if tuple(stage.stage for stage in self.stages) != ("A", "B", "A2"):
            raise ValueError("controlled test cards must use A/B/A2 order")
        if self.control_key not in SETUP_CONTROL_SPECS:
            raise ValueError("test cards must use a driver-changeable setup control")
        return self


class TestDirectorDecision(DirectorModel):
    ready: bool
    card: ControlledTestCard | None = None
    mission: MeasurementMission | None = None

    @model_validator(mode="after")
    def require_exactly_one_output(self) -> TestDirectorDecision:
        if self.ready != (self.card is not None):
            raise ValueError("ready decisions require a test card")
        if self.ready == (self.mission is not None):
            raise ValueError("blocked decisions require exactly one measurement mission")
        return self


class TestExecution(DirectorModel):
    __test__: ClassVar[bool] = False

    eligible_laps_a: int = Field(ge=0)
    eligible_laps_b: int = Field(ge=0)
    eligible_laps_a2: int = Field(ge=0)
    unrelated_setup_changes: int = Field(ge=0)
    control_key: str
    planned_b_value: Any
    observed_a_value: Any
    observed_b_value: Any
    observed_a2_value: Any
    unrelated_changed_controls: tuple[str, ...] = ()
    context_match_score: float = Field(ge=0.0, le=1.0)
    driver_match_score: float = Field(ge=0.0, le=1.0)
    sim_integrity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    phase_effect_b_vs_a_s: float | None = Field(default=None, allow_inf_nan=False)
    phase_effect_b_vs_a2_s: float | None = Field(default=None, allow_inf_nan=False)
    empirical_noise_s: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    empirical_noise_observations: int = Field(default=0, ge=0)
    minimum_alignment_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    countereffect_noise_by_phase_s: dict[str, float] = Field(default_factory=dict)
    target_effect_distributions_consistent: bool | None = None
    target_effect_distribution_state: Literal["faster", "slower", "inconclusive", "inconsistent"] | None = None
    countereffect_passed: bool | None = None
    control_guardrails_passed: bool | None = None
    control_guardrail_metrics: dict[str, float] = Field(default_factory=dict)


class TestQualityResult(DirectorModel):
    protocol_valid: bool
    score: float = Field(ge=0.0, le=100.0)
    verdict: Literal["keep", "undo", "retest", "invalid"]
    blockers: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    controlled_effect_eligible: bool


def _mission(target_phase: str, blockers: list[str]) -> TestDirectorDecision:
    procedures = [
        "Load the unchanged baseline setup and record two warm-up laps.",
        "Record at least three complete flying laps through the target phase.",
        "Keep fuel, tire set and age, weather, driving line, and nearby-car context comparable.",
        "Use Driver Marker at the start of each deliberate target-phase pass.",
    ]
    thresholds = [
        "Three eligible complete laps",
        "No pit, reset, caution, wreck, slowdown, or invalid-speed fragment",
        "Matched context and continuous telemetry",
    ]
    blocker_text = " ".join(blockers).casefold()
    required_laps = 3
    if any(term in blocker_text for term in ("long run", "tire conservation", "tire-life", "tire life")):
        required_laps = 10
        procedures = [
            "Load the unchanged baseline setup and complete a clean continuous baseline stint.",
            "Record at least ten complete consecutive flying laps without a setup, tire-set, pit, reset, or incident boundary.",
            "Keep fuel accounting, tire compound and set, weather, driving line, and nearby-car context traceable.",
            "Capture per-corner tire pressure, temperature, wear, distance, phase time, and fuel-normalized pace throughout the stint.",
        ]
        thresholds.extend([
            "At least ten clean continuous eligible laps after stabilization",
            "Complete per-corner tire-state and tire-distance history",
            "Enough repeated late-stint evidence to separate tire trend from fuel and driver variation",
        ])
    elif "driver confidence" in blocker_text:
        required_laps = 6
        procedures = [
            "Keep the baseline setup unchanged and record six deliberate passes through the target phase.",
            "Use the same line and entry conditions while preserving steering, brake, throttle, yaw, and correction traces.",
            "Use Driver Marker on every deliberate pass and stop after any incident or material context change.",
        ]
        thresholds.extend([
            "Six eligible repeated target-phase passes",
            "Complete driver-input and correction-demand traces",
            "Repeatable improvement in correction demand or input consistency beyond baseline variation",
        ])
    if "adjacent" in blocker_text and ("option" in blocker_text or "garage" in blocker_text):
        procedures.insert(0, "In the garage, save the complete current setup, select one adjacent option for the requested control, pass tech, and save that complete setup without changing anything else.")
        thresholds.append("Both complete setup snapshots pass tech and differ only at the requested control; the adjacent raw garage value and source run are archived")
    if "baseline value" in blocker_text or "setup snapshot" in blocker_text:
        procedures.insert(0, "Capture and save the complete baseline garage setup before leaving the garage.")
        thresholds.append("A complete comparable baseline setup snapshot contains the requested control value")
    if "telemetry event" in blocker_text or "linked" in blocker_text:
        procedures.append("Create a Driver Marker through the complaint phase so the evidence event and physical-position window can be linked.")
        thresholds.append("An eligible target-phase event links the symptom, source channels, and requested setup control")
    if "integrity" in blocker_text:
        procedures.append("Resolve simulator frame-rate, clock, latency, or continuity faults before the measured passes.")
        thresholds.append("The Sim Integrity Certificate is observed clear")
    return TestDirectorDecision(
        ready=False,
        mission=MeasurementMission(
            purpose="Collect enough matched evidence to justify one setup experiment.",
            procedure=tuple(dict.fromkeys(procedures)),
            required_laps_or_passes=required_laps,
            controlled_variables=(
                "setup snapshot",
                "fuel range",
                "tire age and compound",
                "weather and wind",
                "driver inputs and line",
                "nearby-car context",
            ),
            target_phase=target_phase,
            acceptance_thresholds=tuple(dict.fromkeys(thresholds)),
            stop_rule="Stop after any incident, reset, setup drift, simulator-integrity fault, or unsafe condition.",
            blockers=tuple(blockers),
        ),
    )


def build_controlled_test(
    *,
    control_key: str,
    current_value: Any,
    direction_sign: int,
    hypothesis: str,
    target_phase: str,
    success_metrics: list[str],
    countereffects: list[str],
    evidence_links: list[TestEvidenceLink],
    eligible_baseline_laps: int,
    context_matched: bool,
    driver_matched: bool,
    sim_integrity_clear: bool | None,
    legal_values: list[Any] | tuple[Any, ...] | None = None,
    legal_value_provenance: dict[str, list[str]] | None = None,
    external_blockers: list[str] | tuple[str, ...] | None = None,
) -> TestDirectorDecision:
    blockers: list[str] = list(external_blockers or ())
    if control_key not in SETUP_CONTROL_SPECS:
        blockers.append("The requested lever is not one of the supported driver-changeable setup controls.")
    if eligible_baseline_laps < 3:
        blockers.append("At least three eligible baseline flying laps are required.")
    if current_value is None:
        blockers.append("The recorded baseline value for the requested setup control is unavailable.")
    if not hypothesis.strip():
        blockers.append("A specific, evidence-linked hypothesis is required.")
    if not context_matched:
        blockers.append("Fuel, tires, weather, setup, or nearby-car context is not matched.")
    if not driver_matched:
        blockers.append("Driver inputs or racing line changed materially.")
    if sim_integrity_clear is not True:
        blockers.append("Simulator and telemetry integrity has not been observed clear.")
    if direction_sign not in {-1, 1}:
        blockers.append("Setup direction must be explicitly increase or decrease.")
    linked_events = [
        link
        for link in evidence_links
        if link.eligible_lap
        and link.valid_for_tuning
        and link.phase == target_phase
        and control_key in link.related_setup_keys
    ]
    if not linked_events:
        blockers.append("No eligible target-phase telemetry event is linked to this setup control.")
    if not success_metrics:
        blockers.append("No measurable success metric is defined.")
    if not countereffects:
        blockers.append("At least one countereffect or guardrail must be defined.")
    current_representation = setup_value_numeric_representation(control_key, current_value)
    legal_options: list[tuple[float, Any]] = []
    seen_options: set[str] = set()
    for raw_option in legal_values or []:
        represented = setup_value_numeric_representation(control_key, raw_option)
        if represented is None or current_representation is None or represented[0] != current_representation[0]:
            continue
        numeric_option = represented[1]
        option_key = canonical_setup_value_key(control_key, raw_option)
        if option_key not in seen_options:
            legal_options.append((numeric_option, raw_option))
            seen_options.add(option_key)
    legal_options.sort(key=lambda item: item[0])
    adjacent_numeric = None
    adjacent_raw = None
    if current_representation is not None:
        current_numeric = current_representation[1]
        directional = [
            option for option in legal_options
            if option[0] > current_numeric + 1e-9 if direction_sign > 0
        ] if direction_sign > 0 else [
            option for option in legal_options if option[0] < current_numeric - 1e-9
        ]
        if directional:
            adjacent_numeric, adjacent_raw = min(directional) if direction_sign > 0 else max(directional)
    if adjacent_numeric is None:
        blockers.append(
            "No adjacent tech-passing garage option was observed for this exact car, build, context, and surrounding setup."
        )
    normalized_provenance: dict[str, list[str]] = {}
    for raw_value, sources in (legal_value_provenance or {}).items():
        supplied_key = str(raw_value)
        option_key = supplied_key if supplied_key in seen_options else canonical_setup_value_key(control_key, raw_value)
        normalized_provenance.setdefault(option_key, []).extend(sources)
    adjacent_provenance = (
        normalized_provenance.get(canonical_setup_value_key(control_key, adjacent_raw), ())
        if adjacent_raw is not None else ()
    )
    if adjacent_numeric is not None and not adjacent_provenance:
        blockers.append("The adjacent garage option has no server-observed tech-passing provenance.")
    if adjacent_raw is not None:
        if increment_blocker := setup_target_increment_blocker(
            control_key, current_value, adjacent_raw,
        ):
            blockers.append(increment_blocker)
    if blockers:
        return _mission(target_phase, blockers)

    spec = SETUP_CONTROL_SPECS[control_key]
    direction: Literal[-1, 1] = 1 if direction_sign >= 0 else -1
    assert adjacent_numeric is not None and adjacent_raw is not None
    proposed = format_setup_value(control_key, adjacent_raw)
    transition = (
        f"{format_setup_value(control_key, current_value)} -> {proposed} "
        "(adjacent observed tech-passing option)"
    )
    assessment = assess_setup_change(control_key, current_value, adjacent_raw)
    mechanism = expected_control_effect(control_key, direction, current_value)
    do_not_change = tuple(
        item for item in SETUP_CONTROL_SPECS if item != control_key
    )
    baseline_instruction = f"Keep {spec.label} at the recorded baseline value."
    test_instruction = f"Change only {spec.label}: {transition}."
    return TestDirectorDecision(
        ready=True,
        card=ControlledTestCard(
            hypothesis=hypothesis,
            control_key=control_key,
            control_label=spec.label,
            direction_sign=direction,
            current_value=current_value,
            proposed_value=proposed,
            proposed_value_raw=adjacent_raw,
            proposed_value_provenance=tuple(adjacent_provenance),
            exact_change=transition,
            change_size=f"{assessment.label.title()} test input · adjacent observed garage option",
            target_phase=target_phase,
            expected_mechanism=mechanism,
            success_metrics=tuple(success_metrics),
            countereffects=tuple(countereffects),
            rollback_rule=f"Restore {spec.label} to the recorded A value immediately if any countereffect worsens.",
            keep_rule="Keep only if B beats both A and restored A2 beyond the empirical noise floor without a countereffect.",
            stop_rule=(
                "Stop the stage after a pit entry, reset, caution, incident, simulator-integrity fault, "
                "unexpected contact, or unsafe handling; discard contaminated laps and restore A before continuing."
            ),
            stages=(
                TestStage(stage="A", setup_instruction=baseline_instruction, warmup_laps=2, required_flying_laps=3, purpose="Measure baseline variability."),
                TestStage(stage="B", setup_instruction=test_instruction, warmup_laps=2, required_flying_laps=3, purpose="Test one hypothesis."),
                TestStage(stage="A2", setup_instruction=baseline_instruction, warmup_laps=2, required_flying_laps=3, purpose="Confirm reversibility and reject driver/track drift."),
            ),
            evidence_event_ids=tuple(dict.fromkeys(link.event_id for link in linked_events)),
            do_not_change=do_not_change,
        ),
    )


def score_test_execution(execution: TestExecution) -> TestQualityResult:
    blockers: list[str] = []
    if min(execution.eligible_laps_a, execution.eligible_laps_b, execution.eligible_laps_a2) < 3:
        blockers.append("A, B, and A2 each require three eligible flying laps.")
    if execution.unrelated_setup_changes or execution.unrelated_changed_controls:
        blockers.append("More than one unrelated setup control changed.")
    if not setup_control_values_equal(execution.control_key, execution.observed_a2_value, execution.observed_a_value):
        blockers.append("A2 did not restore the recorded baseline setup.")
    if setup_control_values_equal(execution.control_key, execution.observed_b_value, execution.observed_a_value):
        blockers.append("B did not change the planned setup control.")
    if not setup_control_values_equal(execution.control_key, execution.observed_b_value, execution.planned_b_value):
        blockers.append("The observed B setup value does not match the planned test value.")
    if execution.control_key not in SETUP_CONTROL_SPECS:
        blockers.append("The observed setup control is not supported.")
    if execution.context_match_score < 0.8:
        blockers.append("Context match is below the controlled-test threshold.")
    if execution.driver_match_score < 0.8:
        blockers.append("Driver-input or racing-line match is below the controlled-test threshold.")
    if execution.sim_integrity_score is None or execution.sim_integrity_score < 0.8:
        blockers.append("Simulator integrity is unavailable or below the controlled-test threshold.")
    if execution.minimum_alignment_confidence is None or execution.minimum_alignment_confidence < 0.8:
        blockers.append("Target-window alignment is incomplete or below the controlled-test threshold.")
    distribution_state = execution.target_effect_distribution_state
    distributions_consistent = execution.target_effect_distributions_consistent
    if distribution_state is None or distributions_consistent is None:
        blockers.append("The A/B and B/A2 lap-level effect distribution state is unavailable.")
    elif distributions_consistent != (distribution_state in {"faster", "slower"}):
        blockers.append(
            "The lap-level effect distribution consistency flag conflicts with its declared state."
        )
    elif distribution_state == "inconsistent":
        blockers.append("A/B and B/A2 medians are not supported by every lap-level effect beyond noise.")
    if execution.empirical_noise_observations < 3:
        blockers.append("At least three qualified within-baseline effects are required to establish noise.")
    if execution.control_guardrails_passed is None:
        blockers.append("The control-specific telemetry guardrails are unavailable.")
    if (
        execution.phase_effect_b_vs_a_s is None
        or execution.phase_effect_b_vs_a2_s is None
        or execution.empirical_noise_s is None
    ):
        blockers.append("Both A/B and B/A2 phase effects plus empirical noise are required.")

    repetition_score = min(1.0, min(execution.eligible_laps_a, execution.eligible_laps_b, execution.eligible_laps_a2) / 3.0)
    integrity = execution.sim_integrity_score or 0.0
    score = 100.0 * (
        0.15 * repetition_score
        + 0.15 * execution.context_match_score
        + 0.15 * execution.driver_match_score
        + 0.15 * integrity
        + 0.10 * float(setup_control_values_equal(execution.control_key, execution.observed_a2_value, execution.observed_a_value))
        + 0.10 * float(not execution.unrelated_changed_controls and execution.unrelated_setup_changes == 0)
    )
    supporting: list[str] = []
    contradictory: list[str] = []
    effects = (execution.phase_effect_b_vs_a_s, execution.phase_effect_b_vs_a2_s)
    if all(effect is not None for effect in effects) and execution.empirical_noise_s is not None:
        numeric_effects = tuple(float(effect) for effect in effects if effect is not None)
        if all(effect < -execution.empirical_noise_s for effect in numeric_effects):
            aggregate_state = "faster"
            supporting.append("B beat both A and restored A2 beyond the empirical noise floor.")
            score += 20.0
        elif all(effect > execution.empirical_noise_s for effect in numeric_effects):
            aggregate_state = "slower"
            contradictory.append("B was slower than A or restored A2 beyond the empirical noise floor.")
            score += 20.0
        else:
            aggregate_state = "inconclusive"
            contradictory.append("B did not beat both baselines beyond normal variation.")
        if distribution_state is not None and (
            distribution_state in {"faster", "slower", "inconclusive"}
            and distribution_state != aggregate_state
        ):
            blockers.append(
                "The aggregate A/B/A2 target effect conflicts with the lap-level distribution state."
            )
    if execution.countereffect_passed is False:
        contradictory.append("A declared countereffect worsened.")
    if execution.control_guardrails_passed is False:
        contradictory.append("A control-specific safety or durability guardrail worsened.")
    score = min(score, 49.0) if blockers else score

    if blockers:
        verdict: Literal["keep", "undo", "retest", "invalid"] = "invalid"
    elif contradictory and (
        execution.countereffect_passed is False
        or execution.control_guardrails_passed is False
        or all(
            effect is not None
            and execution.empirical_noise_s is not None
            and effect > execution.empirical_noise_s
            for effect in effects
        )
    ):
        verdict = "undo"
    elif (
        supporting
        and execution.countereffect_passed is True
        and execution.control_guardrails_passed is True
        and score >= 80.0
    ):
        verdict = "keep"
    else:
        verdict = "retest"
    replicated_target_direction = bool(
        execution.empirical_noise_s is not None
        and all(effect is not None and effect < -execution.empirical_noise_s for effect in effects)
        or execution.empirical_noise_s is not None
        and all(effect is not None and effect > execution.empirical_noise_s for effect in effects)
    )
    return TestQualityResult(
        protocol_valid=not blockers,
        score=round(score, 2),
        verdict=verdict,
        blockers=tuple(blockers),
        supporting_evidence=tuple(supporting),
        contradictory_evidence=tuple(contradictory),
        controlled_effect_eligible=(
            verdict in {"keep", "undo"}
            and not blockers
            and replicated_target_direction
        ),
    )


def driver_marker_bookmarks(rows: list[dict[str, Any]]) -> tuple[float, ...]:
    """Return rising-edge marker timestamps without inventing missing time."""
    result: list[float] = []
    previous = False
    for row in rows:
        active = bool(row.get("driver_marker") or row.get("DriverMarker"))
        timestamp = row.get("session_time") if row.get("session_time") is not None else row.get("SessionTime")
        if active and not previous and timestamp is not None:
            result.append(float(timestamp))
        previous = active
    return tuple(result)


def active_reset_attempt_groups(rows: list[dict[str, Any]]) -> tuple[tuple[int, int], ...]:
    """Group attempts only on a corroborated reset event/discontinuity.

    ``EnterExitReset`` is the action the reset key would take, not evidence that
    the action occurred, so its state alone must never split a lap.
    """
    if not rows:
        return ()
    starts = [0]
    previous_corroborated = False
    for index, row in enumerate(rows):
        state = row.get("enter_exit_reset_state")
        if state is None:
            state = row.get("EnterExitReset")
        previous_pct = _lap_pct(rows[index - 1]) if index > 0 else None
        current_pct = _lap_pct(row)
        inferred_mid_lap_jump = bool(
            previous_pct is not None
            and current_pct is not None
            and 0.1 < previous_pct < 0.9
            and current_pct < previous_pct - 0.1
        )
        corroborated = bool(
            row.get("reset_event")
            or row.get("active_reset_event")
            or row.get("reset_discontinuity")
            or inferred_mid_lap_jump
        )
        rising_edge = corroborated and not previous_corroborated
        if state == 2 and (inferred_mid_lap_jump or rising_edge) and index > starts[-1]:
            starts.append(index)
        previous_corroborated = corroborated
    return tuple(
        (start, starts[index + 1] - 1 if index + 1 < len(starts) else len(rows) - 1)
        for index, start in enumerate(starts)
    )


def _lap_pct(row: dict[str, Any]) -> float | None:
    value = row.get("lap_dist_pct")
    if value is None:
        value = row.get("LapDistPct")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number / 100.0 if number > 1.5 else number


__all__ = [
    "ControlledTestCard",
    "MeasurementMission",
    "TestDirectorDecision",
    "TestExecution",
    "TestEvidenceLink",
    "TestQualityResult",
    "active_reset_attempt_groups",
    "build_controlled_test",
    "driver_marker_bookmarks",
    "score_test_execution",
]
