"""Frozen P22 prospective engineering predictions and server-owned outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel, canonical_hash
from racelab_engine.evaluation.learning_operations import (
    CampaignOperation,
    list_campaign_operations,
    operation_state,
)
from racelab_engine.services.run_intelligence_service import build_run_intelligence
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


class ProspectiveTestPrediction(EvidenceLabModel):
    prediction_id: str = Field(pattern=r"^ptp-[0-9a-f]{20}$")
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_version: str = Field(min_length=1)
    operation_id: str
    operation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_run_id: str = Field(min_length=1)
    session_id: str | None = None
    predicted_at: datetime
    code_hash: str = Field(min_length=7)
    reasoning_snapshot_id: str = Field(pattern=r"^rsn-[0-9a-f]{20}$")
    reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning_snapshot: dict[str, Any]
    context: dict[str, Any]
    predicted_mechanism: str = Field(min_length=1)
    predicted_control_response: str = Field(min_length=1)
    predicted_countereffects: tuple[str, ...]
    success_criteria: tuple[str, ...] = Field(min_length=1)
    failure_criteria: tuple[str, ...] = Field(min_length=1)
    prospective: Literal[True] = True
    ground_truth_available_at_prediction: Literal[False] = False
    authority: Literal["shadow_only"] = "shadow_only"

    @model_validator(mode="after")
    def frozen_identity_and_snapshot_match(self) -> ProspectiveTestPrediction:
        if canonical_hash(self.reasoning_snapshot) != self.reasoning_snapshot_sha256:
            raise ValueError("prospective prediction reasoning snapshot hash does not match")
        if self.reasoning_snapshot_id != f"rsn-{self.reasoning_snapshot_sha256[:20]}":
            raise ValueError("prospective prediction reasoning snapshot identity does not match")
        payload = self.model_dump(mode="json", exclude={"prediction_id", "prediction_hash"})
        digest = canonical_hash(payload)
        if self.prediction_hash != digest or self.prediction_id != f"ptp-{digest[:20]}":
            raise ValueError("prospective prediction identity does not match its content")
        return self


class ProspectiveTestOutcome(EvidenceLabModel):
    outcome_id: str = Field(pattern=r"^pto-[0-9a-f]{20}$")
    outcome_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_id: str
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    workflow_id: str = Field(min_length=1)
    observed_at: datetime
    stage_run_ids: dict[Literal["A", "B", "A2"], str]
    observed_mechanism: str
    observed_control_response: str
    observed_countereffects: tuple[str, ...]
    observed_policy_result: Literal["keep", "undo", "retest", "invalid", "unavailable"]
    protocol_valid: bool
    gradable: bool
    ungradable_reason: str | None = None
    p19_outcome_snapshot: dict[str, Any] | None = None
    evidence_artifact_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["p19_observation_shadow_evaluation_only"] = (
        "p19_observation_shadow_evaluation_only"
    )

    @model_validator(mode="after")
    def outcome_is_later_explained_and_immutable(self) -> ProspectiveTestOutcome:
        if set(self.stage_run_ids) != {"A", "B", "A2"}:
            raise ValueError("prospective outcome requires exact A/B/A2 run identity")
        if self.gradable == (self.ungradable_reason is not None):
            raise ValueError("prospective outcome gradability and reason disagree")
        payload = self.model_dump(mode="json", exclude={"outcome_id", "outcome_hash"})
        digest = canonical_hash(payload)
        if self.outcome_hash != digest or self.outcome_id != f"pto-{digest[:20]}":
            raise ValueError("prospective outcome identity does not match its content")
        return self


def _prediction(payload: dict[str, Any]) -> ProspectiveTestPrediction:
    constructed = ProspectiveTestPrediction.model_construct(
        prediction_id="ptp-" + "0" * 20,
        prediction_hash="0" * 64,
        **payload,
    )
    digest = canonical_hash(
        constructed.model_dump(mode="json", exclude={"prediction_id", "prediction_hash"})
    )
    return ProspectiveTestPrediction(
        prediction_id=f"ptp-{digest[:20]}",
        prediction_hash=digest,
        **payload,
    )


def _outcome(payload: dict[str, Any]) -> ProspectiveTestOutcome:
    constructed = ProspectiveTestOutcome.model_construct(
        outcome_id="pto-" + "0" * 20,
        outcome_hash="0" * 64,
        **payload,
    )
    digest = canonical_hash(
        constructed.model_dump(mode="json", exclude={"outcome_id", "outcome_hash"})
    )
    return ProspectiveTestOutcome(
        outcome_id=f"pto-{digest[:20]}",
        outcome_hash=digest,
        **payload,
    )


def _operation(
    operation_id: str,
    *,
    db_path: str | Path | None,
) -> CampaignOperation:
    operation = next(
        (
            item
            for item in list_campaign_operations(db_path=db_path)
            if item.operation_id == operation_id
        ),
        None,
    )
    if operation is None:
        raise ValueError(f"Campaign operation not found: {operation_id}")
    return operation


def prospective_runtime_code_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "analysis" / "test_director.py",
        root / "services" / "intelligence_service.py",
        root / "services" / "run_intelligence_service.py",
        Path(__file__).resolve(),
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def freeze_p19_controlled_prediction(
    operation_id: str,
    source_run_id: str,
    *,
    code_hash: str,
    session_id: str | None = None,
    predicted_at: datetime | None = None,
    db_path: str | Path | None = None,
) -> ProspectiveTestPrediction:
    operation = _operation(operation_id, db_path=db_path)
    if operation.campaign_kind != "controlled_setup_response":
        raise ValueError("prospective controlled predictions require that campaign kind")
    if operation_state(operation.operation_id, db_path=db_path) != "active":
        raise ValueError("prospective predictions require an active campaign operation")
    if source_run_id != operation.context.reference_run_id:
        raise ValueError("prediction baseline does not match the frozen operation run")
    repository = RaceLabRepository(db_path)
    workflows = repository.list_controlled_workflows()
    if any(
        source_run_id == workflow.source_run_id
        or source_run_id in workflow.stage_run_ids.values()
        for workflow in workflows
        if workflow.status in {"b_recorded", "a2_recorded", "scored"}
    ):
        raise ValueError("B or later ground truth already exists for this source run")
    bundle = build_run_intelligence(source_run_id, session_id=session_id, db_path=db_path)
    snapshot = bundle.report.reasoning_snapshot
    plan = snapshot.measurement_plan
    card = plan.controlled_test
    if plan.kind != "controlled_test" or not plan.setup_authorized or card is None:
        raise ValueError("P19 has not authorized one exact controlled setup test")
    snapshot_payload = snapshot.model_dump(mode="json")
    snapshot_sha = canonical_hash(snapshot_payload)
    top_cause = snapshot.causes[0] if snapshot.causes else None
    failure = tuple(dict.fromkeys((card.rollback_rule, card.stop_rule)))
    return _prediction(
        {
            "prediction_version": "p22-prospective-control-v1",
            "operation_id": operation.operation_id,
            "operation_hash": operation.operation_hash,
            "source_run_id": source_run_id,
            "session_id": session_id,
            "predicted_at": predicted_at or datetime.now(timezone.utc),
            "code_hash": code_hash,
            "reasoning_snapshot_id": f"rsn-{snapshot_sha[:20]}",
            "reasoning_snapshot_sha256": snapshot_sha,
            "reasoning_snapshot": snapshot_payload,
            "context": {
                "control_key": card.control_key,
                "direction_sign": card.direction_sign,
                "target_phase": card.target_phase,
                "current_value": card.current_value,
                "proposed_value": card.proposed_value,
                "operation_context": operation.context.model_dump(mode="json"),
            },
            "predicted_mechanism": (
                top_cause.hypothesis if top_cause is not None else card.hypothesis
            ),
            "predicted_control_response": card.expected_mechanism,
            "predicted_countereffects": card.countereffects,
            "success_criteria": card.success_metrics,
            "failure_criteria": failure,
            "prospective": True,
            "ground_truth_available_at_prediction": False,
            "authority": "shadow_only",
        }
    )


def save_prospective_prediction(
    prediction: ProspectiveTestPrediction,
    *,
    db_path: str | Path | None = None,
) -> bool:
    operation = _operation(prediction.operation_id, db_path=db_path)
    if operation.operation_hash != prediction.operation_hash:
        raise ValueError("prospective prediction operation identity changed")
    connection = initialize_database(db_path)
    try:
        with connection:
            pending = connection.execute(
                "SELECT prediction.prediction_id FROM prospective_test_predictions AS prediction "
                "LEFT JOIN prospective_test_outcomes AS outcome "
                "ON outcome.prediction_id = prediction.prediction_id "
                "WHERE prediction.source_run_id = ? AND outcome.outcome_id IS NULL "
                "AND prediction.prediction_id <> ? LIMIT 1",
                (prediction.source_run_id, prediction.prediction_id),
            ).fetchone()
            if pending is not None:
                raise ValueError(
                    "this baseline run already has an unscored prospective prediction"
                )
            row = connection.execute(
                "SELECT prediction_hash, prediction_json FROM prospective_test_predictions "
                "WHERE prediction_id = ?",
                (prediction.prediction_id,),
            ).fetchone()
            if row is not None:
                if row["prediction_hash"] != prediction.prediction_hash or (
                    ProspectiveTestPrediction.model_validate_json(row["prediction_json"])
                    != prediction
                ):
                    raise ValueError("immutable prospective-prediction identity collision")
                return False
            connection.execute(
                "INSERT INTO prospective_test_predictions "
                "(prediction_id, prediction_hash, operation_id, source_run_id, "
                "predicted_at, prediction_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    prediction.prediction_id,
                    prediction.prediction_hash,
                    prediction.operation_id,
                    prediction.source_run_id,
                    prediction.predicted_at.isoformat(),
                    prediction.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def attach_matching_outcome_after_score(
    workflow_id: str,
    baseline_run_id: str,
    *,
    db_path: str | Path | None = None,
) -> ProspectiveTestOutcome | None:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT prediction.prediction_id "
            "FROM prospective_test_predictions AS prediction "
            "LEFT JOIN prospective_test_outcomes AS outcome "
            "ON outcome.prediction_id = prediction.prediction_id "
            "WHERE prediction.source_run_id = ? AND outcome.outcome_id IS NULL "
            "ORDER BY prediction.predicted_at DESC, prediction.prediction_id DESC LIMIT 1",
            (baseline_run_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    outcome = attach_p19_workflow_outcome(str(row[0]), workflow_id, db_path=db_path)
    append_prospective_outcome(outcome, db_path=db_path)
    return outcome


def get_prospective_prediction(
    prediction_id: str,
    *,
    db_path: str | Path | None = None,
) -> ProspectiveTestPrediction | None:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT prediction_json FROM prospective_test_predictions WHERE prediction_id = ?",
            (prediction_id,),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else ProspectiveTestPrediction.model_validate_json(row[0])


def attach_p19_workflow_outcome(
    prediction_id: str,
    workflow_id: str,
    *,
    db_path: str | Path | None = None,
) -> ProspectiveTestOutcome:
    prediction = get_prospective_prediction(prediction_id, db_path=db_path)
    if prediction is None:
        raise ValueError(f"Prospective prediction not found: {prediction_id}")
    workflow = RaceLabRepository(db_path).get_controlled_workflow(workflow_id)
    if workflow is None:
        raise ValueError(f"Controlled workflow not found: {workflow_id}")
    if workflow.status != "scored" or set(workflow.stage_run_ids) != {"A", "B", "A2"}:
        raise ValueError("prospective outcome requires one completed scored A/B/A2 workflow")
    if workflow.updated_at <= prediction.predicted_at:
        raise ValueError("workflow outcome does not occur after the frozen prediction")
    if prediction.source_run_id not in {workflow.source_run_id, workflow.stage_run_ids["A"]}:
        raise ValueError("workflow baseline does not match the prospective prediction")
    p19_assessment = None
    try:
        bundle = build_run_intelligence(workflow.stage_run_ids["A2"], db_path=db_path)
        p19_assessment = next(
            (
                item
                for item in bundle.report.reasoning_snapshot.controlled_outcomes
                if item.workflow_id == workflow.workflow_id
            ),
            None,
        )
    except (ValueError, OSError):
        p19_assessment = None
    quality = workflow.quality
    protocol_valid = bool(
        quality is not None
        and quality.protocol_valid
        and quality.controlled_effect_eligible
        and workflow.learning_admitted is True
    )
    gradable = protocol_valid and p19_assessment is not None
    if p19_assessment is None:
        mechanism = "unavailable"
        response = "unavailable"
        countereffects: tuple[str, ...] = ()
        verdict: Literal["keep", "undo", "retest", "invalid", "unavailable"] = (
            "unavailable"
        )
    else:
        mechanism = p19_assessment.mechanism.state
        response = p19_assessment.control_response.result
        countereffects = p19_assessment.policy.countereffects
        verdict = p19_assessment.policy.verdict
    return _outcome(
        {
            "prediction_id": prediction.prediction_id,
            "prediction_hash": prediction.prediction_hash,
            "workflow_id": workflow.workflow_id,
            "observed_at": workflow.updated_at,
            "stage_run_ids": workflow.stage_run_ids,
            "observed_mechanism": mechanism,
            "observed_control_response": response,
            "observed_countereffects": countereffects,
            "observed_policy_result": verdict,
            "protocol_valid": protocol_valid,
            "gradable": gradable,
            "ungradable_reason": (
                None
                if gradable
                else "P19 did not produce one protocol-valid, learning-admitted outcome assessment."
            ),
            "p19_outcome_snapshot": (
                None if p19_assessment is None else p19_assessment.model_dump(mode="json")
            ),
            "evidence_artifact_ids": (
                workflow.workflow_id,
                workflow.stage_run_ids["A"],
                workflow.stage_run_ids["B"],
                workflow.stage_run_ids["A2"],
            ),
            "authority": "p19_observation_shadow_evaluation_only",
        }
    )


def append_prospective_outcome(
    outcome: ProspectiveTestOutcome,
    *,
    db_path: str | Path | None = None,
) -> bool:
    prediction = get_prospective_prediction(outcome.prediction_id, db_path=db_path)
    if prediction is None or prediction.prediction_hash != outcome.prediction_hash:
        raise ValueError("prospective outcome does not match a frozen prediction")
    if outcome.observed_at <= prediction.predicted_at:
        raise ValueError("prospective outcome must be observed after its prediction")
    connection = initialize_database(db_path)
    try:
        with connection:
            existing = connection.execute(
                "SELECT outcome_hash, outcome_json FROM prospective_test_outcomes "
                "WHERE prediction_id = ? OR workflow_id = ?",
                (outcome.prediction_id, outcome.workflow_id),
            ).fetchone()
            if existing is not None:
                if existing["outcome_hash"] == outcome.outcome_hash and (
                    ProspectiveTestOutcome.model_validate_json(existing["outcome_json"])
                    == outcome
                ):
                    return False
                raise ValueError("prediction and workflow outcomes are immutable and one-to-one")
            connection.execute(
                "INSERT INTO prospective_test_outcomes "
                "(outcome_id, outcome_hash, prediction_id, workflow_id, observed_at, "
                "outcome_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    outcome.outcome_id,
                    outcome.outcome_hash,
                    outcome.prediction_id,
                    outcome.workflow_id,
                    outcome.observed_at.isoformat(),
                    outcome.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


__all__ = [
    "ProspectiveTestOutcome",
    "ProspectiveTestPrediction",
    "append_prospective_outcome",
    "attach_matching_outcome_after_score",
    "attach_p19_workflow_outcome",
    "freeze_p19_controlled_prediction",
    "get_prospective_prediction",
    "prospective_runtime_code_hash",
    "save_prospective_prediction",
]
