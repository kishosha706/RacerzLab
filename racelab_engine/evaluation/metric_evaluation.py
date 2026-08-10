"""Frozen, deterministic evaluation plans and immutable result artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel, canonical_hash
from racelab_engine.evaluation.leakage import LeakageReport
from racelab_engine.storage.db import initialize_database


EvaluationMode = Literal[
    "historical_real",
    "prospective_real",
    "synthetic",
    "real_fixture_uncontrolled",
    "controlled",
]
EvaluationState = Literal["valid", "invalid"]


class MetricThreshold(EvidenceLabModel):
    metric_key: str = Field(min_length=1)
    operator: Literal["lt", "lte", "gt", "gte", "eq"]
    value: float = Field(allow_inf_nan=False)
    subgroup_required: bool = True


class FrozenEvaluationPlan(EvidenceLabModel):
    plan_id: str = Field(pattern=r"^evp-[0-9a-f]{20}$")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    capability_key: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    split_policy_id: str = Field(min_length=1)
    split_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_commit: str = Field(min_length=7)
    metric_version: str = Field(min_length=1)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_hashes: tuple[str, ...] = ()
    primary_metrics: tuple[str, ...] = Field(min_length=1)
    thresholds: tuple[MetricThreshold, ...] = Field(min_length=1)
    negative_control_ids: tuple[str, ...] = Field(min_length=1)
    required_subgroups: tuple[str, ...] = Field(min_length=1)
    tuning_partitions: tuple[Literal["train", "calibration"], ...] = ("train",)
    evaluation_partition: Literal["evaluation", "prospective"] = "evaluation"
    authority_ceiling: Literal["evaluation_only"] = "evaluation_only"

    @model_validator(mode="after")
    def frozen_plan_is_canonical(self) -> FrozenEvaluationPlan:
        for values, label in (
            (self.profile_hashes, "profile hash"),
            (self.primary_metrics, "primary metric"),
            (self.negative_control_ids, "negative control"),
            (self.required_subgroups, "required subgroup"),
            (self.tuning_partitions, "tuning partition"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique")
        threshold_keys = [threshold.metric_key for threshold in self.thresholds]
        if len(threshold_keys) != len(set(threshold_keys)):
            raise ValueError("threshold metric keys must be unique")
        payload = self.model_dump(mode="json", exclude={"plan_id", "plan_hash"})
        expected = canonical_hash(payload)
        if self.plan_hash != expected or self.plan_id != f"evp-{expected[:20]}":
            raise ValueError("evaluation-plan identity does not match its frozen content")
        return self


class SubgroupEvaluation(EvidenceLabModel):
    subgroup_key: str = Field(min_length=1)
    independent_unit_count: int = Field(ge=0)
    metrics: dict[str, float | int | None]
    passed: bool
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def failed_subgroup_explains_failure(self) -> SubgroupEvaluation:
        if self.passed and self.blockers:
            raise ValueError("passing subgroups cannot retain blockers")
        if not self.passed and not self.blockers:
            raise ValueError("failed subgroups must explain their failure")
        return self


class NegativeControlEvaluation(EvidenceLabModel):
    control_id: str = Field(min_length=1)
    passed: bool
    observed_value: float | int | bool | None = None
    blocker: str | None = None

    @model_validator(mode="after")
    def failed_control_explains_failure(self) -> NegativeControlEvaluation:
        if self.passed == (self.blocker is not None):
            raise ValueError("negative-control pass state and blocker disagree")
        return self


class EvaluationArtifact(EvidenceLabModel):
    evaluation_id: str = Field(pattern=r"^eva-[0-9a-f]{20}$")
    evaluation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    plan_id: str
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_key: str = Field(min_length=1)
    dataset_id: str
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    split_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_commit: str = Field(min_length=7)
    metric_version: str
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_hashes: tuple[str, ...] = ()
    evaluation_mode: EvaluationMode
    state: EvaluationState
    independent_unit_count: int = Field(ge=0)
    metrics: dict[str, float | int | None]
    subgroups: tuple[SubgroupEvaluation, ...]
    negative_controls: tuple[NegativeControlEvaluation, ...]
    blockers: tuple[str, ...] = ()
    eligible_for_activation_review: bool = False
    authority_ceiling: Literal["evaluation_only"] = "evaluation_only"

    @model_validator(mode="after")
    def result_is_fail_closed_and_content_addressed(self) -> EvaluationArtifact:
        if self.state == "valid" and self.blockers:
            raise ValueError("valid evaluation artifacts cannot retain blockers")
        if self.state == "invalid" and not self.blockers:
            raise ValueError("invalid evaluation artifacts must explain their blockers")
        if self.eligible_for_activation_review and (
            self.state != "valid"
            or any(not subgroup.passed for subgroup in self.subgroups)
            or any(not control.passed for control in self.negative_controls)
        ):
            raise ValueError("activation review requires every validation group to pass")
        payload = self.model_dump(
            mode="json",
            exclude={"evaluation_id", "evaluation_hash"},
        )
        expected = canonical_hash(payload)
        if (
            self.evaluation_hash != expected
            or self.evaluation_id != f"eva-{expected[:20]}"
        ):
            raise ValueError("evaluation identity does not match its frozen inputs")
        return self


def freeze_evaluation_plan(
    payload: dict[str, Any],
    *,
    config: dict[str, Any],
) -> FrozenEvaluationPlan:
    if {"plan_id", "plan_hash", "config_hash"} & payload.keys():
        raise ValueError("evaluation-plan identity and config hash are derived")
    normalized = {
        "created_at": datetime.now(timezone.utc),
        "profile_hashes": (),
        "tuning_partitions": ("train",),
        "evaluation_partition": "evaluation",
        "authority_ceiling": "evaluation_only",
        **payload,
        "config_hash": canonical_hash(config),
    }
    normalized["thresholds"] = tuple(
        MetricThreshold.model_validate(item) for item in normalized["thresholds"]
    )
    identity_payload = FrozenEvaluationPlan.model_construct(
        plan_id="evp-" + "0" * 20,
        plan_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"plan_id", "plan_hash"})
    plan_hash = canonical_hash(identity_payload)
    return FrozenEvaluationPlan(
        plan_id=f"evp-{plan_hash[:20]}",
        plan_hash=plan_hash,
        **normalized,
    )


def build_evaluation_artifact(
    plan: FrozenEvaluationPlan,
    *,
    leakage_report: LeakageReport,
    evaluation_mode: EvaluationMode,
    independent_unit_count: int,
    metrics: dict[str, float | int | None],
    subgroups: tuple[SubgroupEvaluation, ...],
    negative_controls: tuple[NegativeControlEvaluation, ...],
    blockers: tuple[str, ...] = (),
    created_at: datetime | None = None,
) -> EvaluationArtifact:
    result_blockers = list(blockers)
    if leakage_report.dataset_id != plan.dataset_id:
        result_blockers.append("Leakage report does not match the frozen dataset.")
    if leakage_report.dataset_hash != plan.dataset_hash:
        result_blockers.append("Dataset mutation invalidated the leakage report.")
    if leakage_report.split_policy_id != plan.split_policy_id:
        result_blockers.append("Leakage report does not match the split policy.")
    if not leakage_report.valid:
        result_blockers.append("Dataset leakage firewall failed.")
    missing_subgroups = set(plan.required_subgroups) - {
        subgroup.subgroup_key for subgroup in subgroups
    }
    if missing_subgroups:
        result_blockers.append(
            "Missing required subgroups: " + ", ".join(sorted(missing_subgroups)) + "."
        )
    missing_controls = set(plan.negative_control_ids) - {
        control.control_id for control in negative_controls
    }
    if missing_controls:
        result_blockers.append(
            "Missing negative controls: " + ", ".join(sorted(missing_controls)) + "."
        )
    if any(not subgroup.passed for subgroup in subgroups):
        result_blockers.append("At least one required subgroup failed.")
    if any(not control.passed for control in negative_controls):
        result_blockers.append("At least one negative control failed.")
    for threshold in plan.thresholds:
        observed = metrics.get(threshold.metric_key)
        if not _threshold_passes(observed, threshold):
            result_blockers.append(
                f"Primary metric {threshold.metric_key} failed its frozen threshold."
            )
        if threshold.subgroup_required:
            failed = [
                subgroup.subgroup_key
                for subgroup in subgroups
                if not _threshold_passes(
                    subgroup.metrics.get(threshold.metric_key),
                    threshold,
                )
            ]
            if failed:
                result_blockers.append(
                    f"Metric {threshold.metric_key} failed in subgroups: "
                    + ", ".join(sorted(failed))
                    + "."
                )
    result_blockers = list(dict.fromkeys(result_blockers))
    normalized = {
        "created_at": created_at or datetime.now(timezone.utc),
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "capability_key": plan.capability_key,
        "dataset_id": plan.dataset_id,
        "dataset_hash": plan.dataset_hash,
        "split_hash": plan.split_hash,
        "code_commit": plan.code_commit,
        "metric_version": plan.metric_version,
        "config_hash": plan.config_hash,
        "profile_hashes": plan.profile_hashes,
        "evaluation_mode": evaluation_mode,
        "state": "invalid" if result_blockers else "valid",
        "independent_unit_count": independent_unit_count,
        "metrics": metrics,
        "subgroups": subgroups,
        "negative_controls": negative_controls,
        "blockers": tuple(result_blockers),
        "eligible_for_activation_review": not result_blockers,
        "authority_ceiling": "evaluation_only",
    }
    identity_payload = EvaluationArtifact.model_construct(
        evaluation_id="eva-" + "0" * 20,
        evaluation_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"evaluation_id", "evaluation_hash"})
    evaluation_hash = canonical_hash(identity_payload)
    return EvaluationArtifact(
        evaluation_id=f"eva-{evaluation_hash[:20]}",
        evaluation_hash=evaluation_hash,
        **normalized,
    )


def save_evaluation_artifact(
    artifact: EvaluationArtifact,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            row = connection.execute(
                "SELECT evaluation_hash, evaluation_json FROM evaluation_artifacts "
                "WHERE evaluation_id = ?",
                (artifact.evaluation_id,),
            ).fetchone()
            if row is not None:
                if (
                    row["evaluation_hash"] != artifact.evaluation_hash
                    or EvaluationArtifact.model_validate_json(row["evaluation_json"])
                    != artifact
                ):
                    raise ValueError("immutable evaluation identity collision")
                return False
            connection.execute(
                "INSERT INTO evaluation_artifacts "
                "(evaluation_id, evaluation_hash, capability_key, dataset_id, "
                "created_at, evaluation_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    artifact.evaluation_id,
                    artifact.evaluation_hash,
                    artifact.capability_key,
                    artifact.dataset_id,
                    artifact.created_at.isoformat(),
                    artifact.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def _threshold_passes(
    observed: float | int | None,
    threshold: MetricThreshold,
) -> bool:
    if observed is None:
        return False
    value = float(observed)
    target = threshold.value
    return {
        "lt": value < target,
        "lte": value <= target,
        "gt": value > target,
        "gte": value >= target,
        "eq": value == target,
    }[threshold.operator]


def get_evaluation_artifact(
    evaluation_id: str,
    *,
    db_path: str | Path | None = None,
) -> EvaluationArtifact | None:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT evaluation_json FROM evaluation_artifacts WHERE evaluation_id = ?",
            (evaluation_id,),
        ).fetchone()
        return None if row is None else EvaluationArtifact.model_validate_json(row[0])
    finally:
        connection.close()


__all__ = [
    "EvaluationArtifact",
    "EvaluationMode",
    "FrozenEvaluationPlan",
    "MetricThreshold",
    "NegativeControlEvaluation",
    "SubgroupEvaluation",
    "build_evaluation_artifact",
    "freeze_evaluation_plan",
    "get_evaluation_artifact",
    "save_evaluation_artifact",
]
