from __future__ import annotations

from racelab_engine.evaluation.calibration import (
    CalibrationObservation,
    CalibrationStabilityObservation,
    IntervalObservation,
    evaluate_calibration_stability,
    evaluate_interval_coverage,
    evaluate_probability_calibration,
)
from racelab_engine.evaluation.change_point import (
    StintSeries,
    build_change_point_config,
    evaluate_change_points,
)
from racelab_engine.evaluation.negative_transfer import (
    TransferCase,
    evaluate_negative_transfer,
)
from racelab_engine.evaluation.response_models import (
    ResponseWorkflowCase,
    evaluate_response_model,
)
from racelab_engine.evaluation.synthetic import (
    constant_signal,
    inject_gap,
    inject_shift,
)


def _change_config(*, tuned_on=("train",), method="robust_threshold"):
    return build_change_point_config(
        version="v1",
        method=method,
        threshold=1.0,
        minimum_segment_laps=3,
        localization_tolerance_laps=1,
        tuned_on_partitions=tuned_on,
    )


def test_known_lap_12_shift_and_null_stint_score_separately():
    null = constant_signal("null", length=20, value=0.0)
    shifted = inject_shift("shift", (0.0,) * 20, index=11, magnitude=2.0)
    evaluation = evaluate_change_points(
        _change_config(),
        (
            StintSeries(
                stint_id="null-stint",
                lap_numbers=tuple(range(1, 21)),
                values=tuple(value for value in null.values if value is not None),
                known_null=True,
                partition="evaluation",
            ),
            StintSeries(
                stint_id="shift-stint",
                lap_numbers=tuple(range(1, 21)),
                values=tuple(value for value in shifted.values if value is not None),
                known_change_lap=12,
                synthetic=True,
                partition="evaluation",
            ),
        ),
    )
    assert evaluation.state == "valid"
    assert evaluation.false_change_point_rate == 0.0
    assert evaluation.detection_recall == 1.0
    assert evaluation.median_localization_error_laps == 0.0
    assert evaluation.synthetic_stints == 1


def test_test_set_tuning_invalidates_change_point_evaluation():
    evaluation = evaluate_change_points(
        _change_config(tuned_on=("train", "evaluation")),
        (
            StintSeries(
                stint_id="null-stint",
                lap_numbers=tuple(range(1, 11)),
                values=(0.0,) * 10,
                known_null=True,
                partition="evaluation",
            ),
        ),
    )
    assert evaluation.state == "invalid"
    assert "selected on the evaluation set" in evaluation.blockers[0]


def test_unimplemented_pelt_remains_unavailable():
    evaluation = evaluate_change_points(_change_config(method="pelt"), ())
    assert evaluation.state == "unavailable"
    assert "unavailable" in evaluation.blockers[0]


def test_synthetic_gap_is_explicit_and_not_real_validation():
    signal = inject_gap("gap", tuple(float(index) for index in range(10)), index=4, width=2)
    assert signal.values[4:6] == (None, None)
    assert signal.synthetic
    assert signal.allowed_use == "mechanics_and_failure_behavior_only"


def _response_case(
    workflow_id: str,
    *,
    target: int,
    mechanism: int,
    policy: str,
    countereffect: bool,
    predicted_policy: str | None = None,
    restoration: bool = True,
):
    return ResponseWorkflowCase(
        workflow_id=workflow_id,
        partition="evaluation",
        complete_aba2=True,
        one_control=True,
        exact_context=True,
        restoration_passed=restoration,
        target_metric_sign=target,
        mechanism_response_sign=mechanism,
        policy_verdict=policy,
        countereffect_occurred=countereffect,
        predicted_target_metric_sign=target,
        predicted_mechanism_response_sign=mechanism,
        predicted_policy_verdict=predicted_policy or policy,
        predicted_countereffect=countereffect,
    )


def test_response_evaluation_keeps_mechanism_control_and_policy_separate():
    evaluation = evaluate_response_model(
        (
            _response_case(
                "workflow-undo",
                target=-1,
                mechanism=-1,
                policy="undo",
                countereffect=True,
                predicted_policy="keep",
            ),
            _response_case(
                "workflow-keep",
                target=1,
                mechanism=1,
                policy="keep",
                countereffect=False,
            ),
        )
    )
    assert evaluation.target_metric.accuracy == 1.0
    assert evaluation.mechanism_response.accuracy == 1.0
    assert evaluation.policy_verdict.accuracy == 0.5
    assert evaluation.countereffect.accuracy == 1.0
    assert evaluation.state == "invalid"


def test_failed_a2_restoration_is_excluded_from_response_evidence():
    evaluation = evaluate_response_model(
        (
            _response_case(
                "workflow-failed",
                target=1,
                mechanism=1,
                policy="keep",
                countereffect=False,
                restoration=False,
            ),
        )
    )
    assert evaluation.evaluated_workflows == 0
    assert evaluation.excluded_workflows == 1
    assert evaluation.state == "invalid"


def test_probability_calibration_stays_shadow_and_reports_subgroups():
    evaluation = evaluate_probability_calibration(
        (
            CalibrationObservation(
                unit_id="session-1",
                predicted_probability=0.8,
                outcome=1,
                subgroup="atlanta",
                partition="evaluation",
            ),
            CalibrationObservation(
                unit_id="session-2",
                predicted_probability=0.2,
                outcome=0,
                subgroup="bristol",
                partition="prospective",
            ),
        ),
        bins=5,
    )
    assert evaluation.state == "valid"
    assert evaluation.brier_score == 0.04
    assert evaluation.probability_authority is False
    assert set(evaluation.subgroup_metrics) == {"atlanta", "bristol"}


def test_duplicate_calibration_unit_invalidates_evaluation():
    observation = CalibrationObservation(
        unit_id="session-1",
        predicted_probability=0.5,
        outcome=1,
        subgroup="atlanta",
        partition="evaluation",
    )
    evaluation = evaluate_probability_calibration((observation, observation))
    assert evaluation.state == "invalid"


def test_conformal_coverage_uses_only_untouched_evaluation_units():
    evaluation = evaluate_interval_coverage(
        (
            IntervalObservation(
                unit_id="calibration-1",
                lower=0.0,
                upper=100.0,
                actual=50.0,
                subgroup="atlanta",
                partition="calibration",
            ),
            IntervalObservation(
                unit_id="evaluation-1",
                lower=0.0,
                upper=1.0,
                actual=2.0,
                subgroup="atlanta",
                partition="evaluation",
            ),
        ),
        nominal_coverage=0.9,
    )
    assert evaluation.independent_units == 1
    assert evaluation.actual_coverage == 0.0
    assert evaluation.public_intervals_allowed is False


def test_negative_transfer_in_any_subgroup_keeps_transfer_locked():
    evaluation = evaluate_negative_transfer(
        (
            TransferCase(
                unit_id="session-1",
                subgroup="same_driver_same_track",
                no_transfer_error=1.0,
                transfer_error=0.8,
            ),
            TransferCase(
                unit_id="session-2",
                subgroup="different_driver_different_track",
                no_transfer_error=1.0,
                transfer_error=1.4,
            ),
        )
    )
    assert evaluation.state == "locked"
    assert evaluation.negative_transfer_subgroups == (
        "different_driver_different_track",
    )


def test_dense_samples_from_one_lap_cannot_unlock_calibration() -> None:
    observation = CalibrationStabilityObservation(
        unit_id="session-1:lap-4",
        session_id="session-1",
        lap_number=4,
        effect_sign=1,
        bootstrap_block_signs=(1, 1, 1, 1, 1),
        context_id="context-a",
        context_drifted=False,
        countereffect_occurred=False,
        partition="evaluation",
    )
    evaluation = evaluate_calibration_stability((observation,))
    assert evaluation.state == "collecting"
    assert evaluation.independent_eligible_laps == 1
    assert evaluation.independent_sessions == 1
    assert evaluation.confidence_activation_allowed is False
    assert any("sample count is not an independence unit" in item for item in evaluation.blockers)


def test_calibration_stability_records_held_out_context_and_countereffects() -> None:
    observations = tuple(
        CalibrationStabilityObservation(
            unit_id=f"session-{session}:lap-{lap}",
            session_id=f"session-{session}",
            lap_number=lap,
            effect_sign=1,
            bootstrap_block_signs=(1, 1, 1),
            context_id=f"context-{session}",
            context_drifted=session == 2 and lap == 3,
            countereffect_occurred=session == 2 and lap == 2,
            partition="evaluation" if session == 2 else "calibration",
        )
        for session in (1, 2)
        for lap in (1, 2, 3)
    )
    evaluation = evaluate_calibration_stability(observations)
    assert evaluation.state == "eligible_for_shadow_evaluation"
    assert evaluation.independent_eligible_laps == 6
    assert evaluation.independent_sessions == 2
    assert evaluation.held_out_laps == 3
    assert evaluation.block_bootstrap_stability == 1.0
    assert evaluation.context_drift_rate == 1 / 6
    assert evaluation.countereffect_rate == 1 / 6
    assert evaluation.confidence_activation_allowed is False
