"""Adversarial tests for the automatic handling-balance producer.

Synthetic scenarios per the milestone acceptance criteria. Every scenario
asserts what the producer must NOT claim as well as what it must.
"""

from __future__ import annotations

import math
import random


from racelab_engine.analysis.handling_balance import analyze_handling_balance
from racelab_engine.models.handling_balance import (
    HandlingAuthority,
    HandlingClassification,
)
from racelab_engine.models.lap import LapSummary

RUN_ID = "run-handling-synthetic"


def _lap_summary(lap_number: int, *, tags: tuple[str, ...] = ()) -> LapSummary:
    return LapSummary(
        lap_id=f"lap-{lap_number}",
        run_id=RUN_ID,
        lap_number=lap_number,
        lap_type="flying",
        is_complete=True,
        is_useful=True,
        lap_time=50.0 + 0.1 * lap_number,
        classification_tags=list(tags),
    )


def _eligible_summaries(count: int = 6, start: int = 1) -> list[LapSummary]:
    return [_lap_summary(number) for number in range(start, start + count)]


def _corner_rows(
    *,
    laps: int = 6,
    deficit_fn,
    seed: int = 7,
    with_yaw: bool = True,
    with_steering: bool = True,
) -> list[dict]:
    """Deterministic synthetic laps: one sustained corner at 40-60% lap.

    Speed 55 m/s, corner curvature 0.01 1/m, steering 5 deg. deficit_fn(lap,
    pct) returns the injected rotation deficit (rad/s): positive = rotates
    less than the path reference.
    """
    rng = random.Random(seed)
    rows: list[dict] = []
    for lap in range(1, laps + 1):
        base_time = lap * 100.0
        for step in range(200):
            pct = step * 0.5
            in_corner = 40.0 <= pct <= 60.0
            ramp_up = 40.0 <= pct < 45.0
            ramp_down = 55.0 < pct <= 60.0
            steering = 0.0
            if ramp_up:
                steering = 5.0 * (pct - 40.0) / 5.0
            elif in_corner and not ramp_down:
                steering = 5.0
            elif ramp_down:
                steering = 5.0 * (60.0 - pct) / 5.0
            curvature = 0.01 if in_corner else 0.0001
            speed = 55.0
            expected = speed * curvature
            deficit = deficit_fn(lap, pct)
            yaw = expected - deficit + rng.gauss(0.0, 0.003)
            row: dict = {
                "lap": lap,
                "lap_dist_pct_100": pct,
                "session_time": base_time + step * 0.01,
                "speed_mps": speed,
                "speed_mph": speed * 2.2369362920544,
                "yaw_rate": yaw if with_yaw else None,
                "steering_rad": math.radians(steering) if with_steering else None,
                "steering_deg": steering if with_steering else None,
                "lat_accel": speed * yaw,
                "throttle_pct": 50.0 if in_corner else 100.0,
                "brake_pct": 0.0,
                "curvature_1_per_m": curvature,
                "lat": None,
                "lon": None,
                "velocity_y": None,
            }
            rows.append(row)
    return rows


def _constant(deficit: float):
    return lambda _lap, _pct: deficit


def _two_corner_rows(*, laps: int = 6, seed: int = 11) -> list[dict]:
    """Two corners with opposite, phase-separated response signatures.

    Corner A (20-40%): sustained center steering at part throttle → deficit.
    Corner B (60-80%): brief turn-in then throttle pickup → excess rotation.
    """
    rng = random.Random(seed)
    rows: list[dict] = []
    for lap in range(1, laps + 1):
        base_time = lap * 100.0
        for step in range(200):
            pct = step * 0.5
            steering = 0.0
            throttle = 100.0
            curvature = 0.0001
            deficit = 0.0
            if 20.0 <= pct <= 40.0:
                if pct < 23.0:
                    steering = 5.0 * (pct - 20.0) / 3.0
                else:
                    steering = 5.0
                throttle = 50.0
                curvature = 0.01
                deficit = 0.045
            elif 60.0 <= pct <= 80.0:
                if pct < 63.0:
                    steering = 5.0 * (pct - 60.0) / 3.0
                else:
                    steering = 5.0
                if pct < 62.0:
                    throttle = 50.0
                elif pct < 66.0:
                    throttle = 50.0 + 50.0 * (pct - 62.0) / 4.0
                else:
                    throttle = 100.0
                curvature = 0.01
                deficit = -0.045
            speed = 55.0
            expected = speed * curvature
            yaw = expected - deficit + rng.gauss(0.0, 0.003)
            rows.append({
                "lap": lap,
                "lap_dist_pct_100": pct,
                "session_time": base_time + step * 0.01,
                "speed_mps": speed,
                "speed_mph": speed * 2.2369362920544,
                "yaw_rate": yaw,
                "steering_rad": math.radians(steering),
                "steering_deg": steering,
                "lat_accel": speed * yaw,
                "throttle_pct": throttle,
                "brake_pct": 0.0,
                "curvature_1_per_m": curvature,
                "lat": None,
                "lon": None,
                "velocity_y": None,
            })
    return rows


def _mixed(lap, pct):
    return 0.045 if pct < 50.0 else -0.045


def _assert_observation_only(report) -> None:
    assert report.authority == HandlingAuthority.OBSERVATION_ONLY
    assert report.setup_authorized is False
    for assessment in report.assessments:
        assert assessment.authority == HandlingAuthority.OBSERVATION_ONLY
        assert assessment.setup_authorized is False
        assert assessment.driver_feedback_source is False
        assert assessment.classification != HandlingClassification.UNAVAILABLE or assessment.blocker_reasons
        # The producer never emits tight/loose verdict words as claims.
        assert "understeer gradient" not in assessment.observation_text.lower()
        assert "oversteer gradient" not in assessment.observation_text.lower()


def _no_setup_language(report) -> None:
    text = " ".join(a.observation_text for a in report.assessments).lower()
    for banned in ("change the setup", "set the", "authorizes", "authorize a change", "keep/undo", "retest"):
        assert banned not in text


# ── Scenario 1: qualified understeer-like (reduced rotation) ────

def test_repeatable_rotation_response_deficit_is_described_not_labeled():
    rows = _corner_rows(deficit_fn=_constant(0.045))
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification in {
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        HandlingClassification.MIXED_PHASE_DEPENDENT,
    }
    _assert_observation_only(report)
    _no_setup_language(report)
    # An observation exists and is descriptive, not a tight/loose verdict.
    assert report.assessments
    for assessment in report.assessments:
        assert "tight" not in assessment.observation_text.lower()
        assert "loose" not in assessment.observation_text.lower()
        assert "understeer" not in assessment.observation_text.lower()


# ── Scenario 2: qualified oversteer-like (excess rotation) ─────

def test_repeatable_rotation_response_excess_is_described_not_labeled():
    rows = _corner_rows(deficit_fn=_constant(-0.045))
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification in {
        HandlingClassification.ROTATION_RESPONSE_EXCESS,
        HandlingClassification.MIXED_PHASE_DEPENDENT,
    }
    _assert_observation_only(report)
    for assessment in report.assessments:
        assert "oversteer" not in assessment.observation_text.lower()


# ── Scenario 3: mixed balance stays phase-local ────────────────

def test_mixed_phase_dependent_preserves_phase_distinctions():
    rows = _two_corner_rows()
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    phases = {assessment.phase for assessment in report.assessments}
    assert len(phases) >= 2
    kinds = {assessment.classification for assessment in report.assessments}
    assert HandlingClassification.ROTATION_RESPONSE_DEFICIT in kinds
    assert HandlingClassification.ROTATION_RESPONSE_EXCESS in kinds
    # No single global verdict may collapse the two directions.
    assert report.classification == HandlingClassification.MIXED_PHASE_DEPENDENT
    _assert_observation_only(report)


# ── Scenario 4: normal response under the reference ────────────

def test_no_imbalance_is_not_neutral_balance():
    rows = _corner_rows(deficit_fn=_constant(0.0))
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification == HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED
    # Honesty: the absence of a qualified imbalance is not "neutral".
    summary = " ".join(c.summary for c in report.conclusions)
    assert "not proof of neutral balance" in summary


# ── Scenario 5: weak signal below empirical noise ──────────────

def test_weak_signal_below_noise_floor_is_not_classified():
    rows = _corner_rows(deficit_fn=_constant(0.008))
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification == HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED
    assert not any(
        assessment.classification == HandlingClassification.ROTATION_RESPONSE_DEFICIT
        for assessment in report.assessments
    )


# ── Scenario 6: missing yaw fails closed ───────────────────────

def test_missing_yaw_returns_unavailable_with_requirements():
    rows = _corner_rows(deficit_fn=_constant(0.045), with_yaw=False)
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification == HandlingClassification.UNAVAILABLE
    assert report.assessments[0].blocker_reasons
    assert not report.gate.eligible


# ── Scenario 7: missing steering fails closed ──────────────────

def test_missing_steering_returns_unavailable():
    rows = _corner_rows(deficit_fn=_constant(0.045), with_steering=False)
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification == HandlingClassification.UNAVAILABLE


# ── Scenario 8: insufficient repetitions fail closed ───────────

def test_single_eligible_lap_is_blocked():
    rows = _corner_rows(deficit_fn=_constant(0.045), laps=1)
    report = analyze_handling_balance(
        rows, _eligible_summaries(count=1), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification == HandlingClassification.UNAVAILABLE
    assert any("repetition" in blocker.lower() for blocker in report.gate.blocker_reasons)


# ── Scenario 9: junk laps never participate ────────────────────

def test_junk_laps_are_excluded_from_reference():
    rows = _corner_rows(deficit_fn=_constant(0.045), laps=3)
    summaries = [
        _lap_summary(1),
        _lap_summary(2, tags=("WRECK_OR_SPIN",)),
        _lap_summary(3),
    ]
    report = analyze_handling_balance(
        rows, summaries, run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    if report.classification != HandlingClassification.UNAVAILABLE:
        for assessment in report.assessments:
            assert 2 not in assessment.lap_numbers
            assert 2 not in assessment.phase_observations[0].reference_lap_group


# ── Scenario 10: sim-integrity uncertainty fails closed ────────

def test_unclear_sim_integrity_blocks_classification():
    rows = _corner_rows(deficit_fn=_constant(0.045))
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=None, sim_integrity_confidence_cap=0.9,
    )
    assert report.classification == HandlingClassification.UNAVAILABLE
    assert report.assessments[0].blocker_reasons


# ── Scenario 11: setup change spanning the lap group blocks ────

def test_unisolated_setup_change_blocks():
    rows = _corner_rows(deficit_fn=_constant(0.045))
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
        setup_change_isolated=False,
    )
    assert report.classification == HandlingClassification.UNAVAILABLE
    assert any("setup change" in blocker.lower() for blocker in report.gate.blocker_reasons)


# ── Idempotence ────────────────────────────────────────────────

def test_repeated_analysis_is_idempotent():
    rows = _corner_rows(deficit_fn=_constant(0.045))
    first = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    second = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert first.model_dump() == second.model_dump()
    assert first.assessments[0].assessment_id == second.assessments[0].assessment_id


# ── Canonical symptom bridge ───────────────────────────────────

def test_qualified_signature_maps_to_vocabulary_symptom_never_driver_testimony():
    from racelab_engine.knowledge.setup.handling_symptom_bridge import (
        resolve_canonical_symptom,
    )
    symptom, blocker = resolve_canonical_symptom(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT, "center",
    )
    assert symptom == "tight_center"
    assert blocker is None
    symptom, _blocker = resolve_canonical_symptom(
        HandlingClassification.ROTATION_RESPONSE_EXCESS, "initial_throttle",
    )
    assert symptom == "loose_exit"
    symptom, blocker = resolve_canonical_symptom(
        HandlingClassification.MIXED_PHASE_DEPENDENT, "center",
    )
    assert symptom is None
    assert blocker

    rows = _corner_rows(deficit_fn=_constant(0.045))
    report = analyze_handling_balance(
        rows, _eligible_summaries(), run_id=RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    mapped = {assessment.canonical_symptom_id for assessment in report.assessments}
    assert mapped and all(symptom is not None for symptom in mapped)
    for assessment in report.assessments:
        if assessment.canonical_symptom_id:
            assert assessment.driver_feedback_source is False
            assert any(
                "not driver testimony" in evidence
                for evidence in assessment.supporting_evidence
            )


def test_unknown_phase_family_has_no_symptom_mapping():
    from racelab_engine.knowledge.setup.handling_symptom_bridge import (
        resolve_canonical_symptom,
    )
    symptom, blocker = resolve_canonical_symptom(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT, "bump_curb",
    )
    assert symptom is None
    assert blocker
