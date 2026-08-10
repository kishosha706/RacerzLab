from __future__ import annotations

from datetime import datetime, timezone

from racelab_engine.evaluation.dataset_registry import (
    build_evidence_dataset,
    register_evidence_dataset,
)
from racelab_engine.evaluation.leakage import evaluate_dataset_leakage
from racelab_engine.evaluation.metric_evaluation import (
    NegativeControlEvaluation,
    SubgroupEvaluation,
    build_evaluation_artifact,
    freeze_evaluation_plan,
    get_evaluation_artifact,
    save_evaluation_artifact,
)
from racelab_engine.evaluation.reports import render_evaluation_report
from racelab_engine.evaluation.split_policy import build_split_policy


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)
SHA = "a" * 64


def _dataset(*, synthetic: bool = False):
    return build_evidence_dataset(
        {
            "dataset_kind": "synthetic_injection" if synthetic else "null_no_change",
            "created_at": NOW,
            "manifest": {
                "schema_version": "v1",
                "source_run_ids": ("run-1",),
                "source_session_ids": ("session-1",),
                "car_identities": ("nextgen",),
                "track_identities": ("atlanta",),
                "iracing_build_identities": ("build-1",),
                "analysis_artifact_versions": ("p20-v1",),
                "setup_identities": ("setup-1",),
                "context_distribution": {"atlanta": 1},
                "lap_count": 20,
                "independence_unit_count": 1,
                "ground_truth_type": (
                    "synthetic_known_signal" if synthetic else "same_setup_null"
                ),
                "allowed_evaluation_uses": ("change_point",),
                "forbidden_uses": ("setup_authority",),
            },
            "artifacts": (
                {
                    "artifact_id": "archive-1",
                    "artifact_kind": "telemetry_archive",
                    "content_sha256": SHA,
                    "source_file_fingerprint": SHA,
                    "source_run_ids": ("run-1",),
                    "artifact_version": "v1",
                },
            ),
            "units": (
                {
                    "unit_id": "stint-1",
                    "independence_level": "stint",
                    "source_artifact_ids": ("archive-1",),
                    "source_file_fingerprints": (SHA,),
                    "source_run_ids": ("run-1",),
                    "source_session_ids": ("session-1",),
                    "source_stint_ids": ("stint-1",),
                    "lap_numbers": tuple(range(1, 21)),
                    "synthetic": synthetic,
                },
            ),
            "splits": (
                {
                    "split_id": "evaluation",
                    "partition": "evaluation",
                    "unit_ids": ("stint-1",),
                },
            ),
            "qualification": {
                "state": "qualified",
                "qualified_real_world_units": 0 if synthetic else 1,
                "qualified_synthetic_units": 1 if synthetic else 0,
            },
        }
    )


def _policy():
    return build_split_policy(
        {
            "policy_version": "v1",
            "kind": "whole_stint",
            "required_independence_level": "stint",
        }
    )


def _plan(dataset, policy, *, code_commit: str = "abcdef123456"):
    return freeze_evaluation_plan(
        {
            "created_at": NOW,
            "capability_key": "change_point",
            "dataset_id": dataset.dataset_id,
            "dataset_hash": dataset.dataset_hash,
            "split_policy_id": policy.policy_id,
            "split_hash": policy.policy_hash,
            "code_commit": code_commit,
            "metric_version": "change-point-v1",
            "primary_metrics": ("false_positive_rate",),
            "thresholds": (
                {
                    "metric_key": "false_positive_rate",
                    "operator": "lte",
                    "value": 0.05,
                },
            ),
            "negative_control_ids": ("no_change",),
            "required_subgroups": ("atlanta",),
        },
        config={"penalty": 4.0},
    )


def _artifact(dataset, policy, plan, *, subgroup_passed: bool = True):
    leakage = evaluate_dataset_leakage(dataset, policy)
    return build_evaluation_artifact(
        plan,
        leakage_report=leakage,
        evaluation_mode="historical_real",
        independent_unit_count=1,
        metrics={"false_positive_rate": 0.04},
        subgroups=(
            SubgroupEvaluation(
                subgroup_key="atlanta",
                independent_unit_count=1,
                metrics={"false_positive_rate": 0.04},
                passed=subgroup_passed,
                blockers=() if subgroup_passed else ("Known-null stint fired.",),
            ),
        ),
        negative_controls=(
            NegativeControlEvaluation(
                control_id="no_change",
                passed=True,
                observed_value=False,
            ),
        ),
        created_at=NOW,
    )


def test_frozen_evaluation_is_reproducible_and_persistent(tmp_path):
    dataset = _dataset()
    policy = _policy()
    plan = _plan(dataset, policy)
    artifact = _artifact(dataset, policy, plan)
    assert artifact.state == "valid"
    assert artifact.eligible_for_activation_review
    assert register_evidence_dataset(dataset, db_path=tmp_path / "lab.sqlite")
    assert save_evaluation_artifact(artifact, db_path=tmp_path / "lab.sqlite")
    assert not save_evaluation_artifact(artifact, db_path=tmp_path / "lab.sqlite")
    assert get_evaluation_artifact(
        artifact.evaluation_id,
        db_path=tmp_path / "lab.sqlite",
    ) == artifact
    report = render_evaluation_report(artifact)
    assert "Authority: EVALUATION ONLY" in report
    assert "atlanta: pass" in report


def test_code_or_config_change_creates_new_evaluation_identity():
    dataset = _dataset()
    policy = _policy()
    first = _artifact(dataset, policy, _plan(dataset, policy))
    changed_code = _artifact(
        dataset,
        policy,
        _plan(dataset, policy, code_commit="fedcba654321"),
    )
    changed_config_plan = freeze_evaluation_plan(
        {
            **_plan(dataset, policy).model_dump(
                mode="python",
                exclude={"plan_id", "plan_hash", "config_hash"},
            ),
        },
        config={"penalty": 5.0},
    )
    changed_config = _artifact(dataset, policy, changed_config_plan)
    assert len(
        {first.evaluation_id, changed_code.evaluation_id, changed_config.evaluation_id}
    ) == 3


def test_subgroup_failure_locks_good_aggregate_result():
    dataset = _dataset()
    policy = _policy()
    artifact = _artifact(dataset, policy, _plan(dataset, policy), subgroup_passed=False)
    assert artifact.state == "invalid"
    assert not artifact.eligible_for_activation_review
    assert "At least one required subgroup failed." in artifact.blockers


def test_synthetic_only_dataset_invalidates_real_evaluation():
    dataset = _dataset(synthetic=True)
    policy = _policy()
    artifact = _artifact(dataset, policy, _plan(dataset, policy))
    assert artifact.state == "invalid"
    assert "Dataset leakage firewall failed." in artifact.blockers


def test_missing_metric_never_becomes_zero_or_neutral():
    dataset = _dataset()
    policy = _policy()
    plan = _plan(dataset, policy)
    leakage = evaluate_dataset_leakage(dataset, policy)
    artifact = build_evaluation_artifact(
        plan,
        leakage_report=leakage,
        evaluation_mode="historical_real",
        independent_unit_count=1,
        metrics={"false_positive_rate": None},
        subgroups=(
            SubgroupEvaluation(
                subgroup_key="atlanta",
                independent_unit_count=1,
                metrics={"false_positive_rate": None},
                passed=True,
            ),
        ),
        negative_controls=(
            NegativeControlEvaluation(control_id="no_change", passed=True),
        ),
        created_at=NOW,
    )
    assert artifact.state == "invalid"
    assert any("failed its frozen threshold" in item for item in artifact.blockers)
