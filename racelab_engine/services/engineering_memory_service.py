"""Immutable internal engineering memory and presentation-only driver context.

This module never participates in evidence eligibility or setup authorization.
It records what the server predicted before a test, grades that frozen prediction
after a controlled result, and assembles an auditable session narrative.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.engineering_memory import (
    DriverPresentationObservation,
    DriverPresentationProfile,
    EngineeringEvidenceReference,
    EngineeringNarrativeEntry,
    NarrativeEntryType,
    PredictionCalibrationSummary,
    PredictionContract,
    PredictionGrade,
    RecurringSymptom,
)
from racelab_engine.services.session_service import get_session, list_sessions
from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.storage.db import initialize_database


_CONTEXT_KEYS = (
    "car_id",
    "car_path",
    "car_version",
    "track_id",
    "track_configuration_name",
    "track_version",
    "iracing_build_version",
    "session_type",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _dedupe_refs(
    references: Iterable[EngineeringEvidenceReference],
) -> tuple[EngineeringEvidenceReference, ...]:
    seen: set[tuple[str, str]] = set()
    result: list[EngineeringEvidenceReference] = []
    for reference in references:
        key = (reference.kind, reference.reference_id)
        if key not in seen:
            seen.add(key)
            result.append(reference)
    return tuple(result)


def _ref(kind: str, reference_id: str) -> EngineeringEvidenceReference:
    return EngineeringEvidenceReference(kind=kind, reference_id=reference_id)


_REFERENCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@\-\[\]]*")


def _narrative_references_are_valid(entry: EngineeringNarrativeEntry) -> bool:
    for reference in entry.evidence_references:
        reference_id = reference.reference_id
        if _REFERENCE_ID_PATTERN.fullmatch(reference_id) is None:
            return False
        if reference.kind == "run" and reference_id not in entry.run_ids:
            return False
        if reference.kind == "workflow" and reference_id != entry.workflow_id:
            return False
        if reference.kind == "lap" and not any(
            reference_id.startswith(f"{run_id}:") for run_id in entry.run_ids
        ):
            return False
    return True


def _workflow_run_ids(workflow: ControlledWorkflow) -> tuple[str, ...]:
    return tuple(dict.fromkeys([workflow.source_run_id, *workflow.stage_run_ids.values()]))


def _workflow_references(workflow: ControlledWorkflow) -> tuple[EngineeringEvidenceReference, ...]:
    packet = workflow.packet
    card = packet.primary_test
    references: list[EngineeringEvidenceReference] = [
        _ref("workflow", workflow.workflow_id),
        *(_ref("run", run_id) for run_id in _workflow_run_ids(workflow)),
        *(_ref("event", event_id) for event_id in packet.opportunity.evidence_event_ids),
        *(_ref("channel", channel) for channel in packet.opportunity.source_channels),
    ]
    if card is not None:
        references.extend(
            _ref("setup", provenance) for provenance in card.proposed_value_provenance
        )
    for stage, run_id in workflow.stage_run_ids.items():
        references.extend(
            _ref("lap", f"{run_id}:{lap_number}")
            for lap_number in workflow.stage_eligible_lap_numbers.get(stage, ())
        )
    return _dedupe_refs(references)


def _prediction_references(workflow: ControlledWorkflow) -> tuple[EngineeringEvidenceReference, ...]:
    packet = workflow.packet
    card = packet.primary_test
    references: list[EngineeringEvidenceReference] = [
        _ref("workflow", workflow.workflow_id),
        _ref("run", workflow.source_run_id),
        *(_ref("event", event_id) for event_id in packet.opportunity.evidence_event_ids),
        *(_ref("channel", channel) for channel in packet.opportunity.source_channels),
    ]
    if card is not None:
        references.extend(
            _ref("setup", provenance) for provenance in card.proposed_value_provenance
        )
    return _dedupe_refs(references)


def _insert_immutable(
    *,
    table: str,
    id_column: str,
    record_id: str,
    payload_column: str,
    payload: Any,
    columns: Mapping[str, Any],
    db_path: str | Path | None,
) -> None:
    payload_json = _canonical_json(payload)
    connection = initialize_database(db_path)
    existing = connection.execute(
        f"SELECT {payload_column} FROM {table} WHERE {id_column} = ?",
        (record_id,),
    ).fetchone()
    if existing is not None:
        if _canonical_json(json.loads(existing[payload_column])) != payload_json:
            connection.close()
            raise ValueError(
                f"Immutable engineering-memory record {record_id} conflicts with persisted history."
            )
        connection.close()
        return
    with connection:
        names = [id_column, *columns, payload_column]
        placeholders = ", ".join("?" for _ in names)
        connection.execute(
            f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders})",
            (record_id, *columns.values(), payload_json),
        )
    connection.close()


def save_prediction_contract(
    contract: PredictionContract,
    *,
    db_path: str | Path | None = None,
) -> PredictionContract:
    existing = get_prediction_contract(contract.workflow_id, db_path=db_path)
    if existing is not None:
        if existing != contract:
            raise ValueError(
                f"Workflow {contract.workflow_id} already has a different immutable prediction contract."
            )
        return existing
    _insert_immutable(
        table="engineering_prediction_contracts",
        id_column="contract_id",
        record_id=contract.contract_id,
        payload_column="contract_json",
        payload=contract,
        columns={
            "workflow_id": contract.workflow_id,
            "created_at": contract.created_at.isoformat(),
            "source_run_id": contract.source_run_id,
        },
        db_path=db_path,
    )
    return contract


def get_prediction_contract(
    workflow_id: str,
    *,
    db_path: str | Path | None = None,
) -> PredictionContract | None:
    connection = initialize_database(db_path)
    row = connection.execute(
        "SELECT contract_json FROM engineering_prediction_contracts WHERE workflow_id = ?",
        (workflow_id,),
    ).fetchone()
    connection.close()
    return PredictionContract.model_validate_json(row["contract_json"]) if row else None


def save_prediction_grade(
    grade: PredictionGrade,
    *,
    db_path: str | Path | None = None,
) -> PredictionGrade:
    contract = get_prediction_contract(grade.workflow_id, db_path=db_path)
    if contract is None or not _grade_matches_contract(grade, contract):
        raise ValueError(
            "A prediction grade must match the exact immutable workflow prediction contract."
        )
    existing = get_prediction_grade(grade.workflow_id, db_path=db_path)
    if existing is not None:
        if existing != grade:
            raise ValueError(
                f"Workflow {grade.workflow_id} already has a different immutable prediction grade."
            )
        return existing
    _insert_immutable(
        table="engineering_prediction_grades",
        id_column="grade_id",
        record_id=grade.grade_id,
        payload_column="grade_json",
        payload=grade,
        columns={
            "contract_id": grade.contract_id,
            "workflow_id": grade.workflow_id,
            "created_at": grade.created_at.isoformat(),
        },
        db_path=db_path,
    )
    return grade


def _grade_matches_contract(
    grade: PredictionGrade,
    contract: PredictionContract,
) -> bool:
    contract_digest = hashlib.sha256(
        _canonical_json(contract).encode("utf-8")
    ).hexdigest()
    if contract.expected_direction is None or grade.actual_direction == "unavailable":
        expected_direction_result = "unavailable"
    elif grade.actual_direction == "inconclusive":
        expected_direction_result = "inconclusive"
    elif grade.actual_direction == contract.expected_direction:
        expected_direction_result = "matched"
    else:
        expected_direction_result = "missed"
    if (
        not grade.protocol_valid
        or contract.expected_range_s is None
        or grade.actual_effect_s is None
    ):
        expected_range_result = "unavailable"
    elif grade.actual_direction == "inconclusive":
        expected_range_result = "inconclusive"
    elif contract.expected_range_s[0] <= grade.actual_effect_s <= contract.expected_range_s[1]:
        expected_range_result = "inside"
    else:
        expected_range_result = "outside"
    if not grade.protocol_valid:
        expected_label = "not_gradable_protocol_invalid"
    elif grade.actual_direction in {"inconclusive", "unavailable"}:
        expected_label = "inconclusive"
    elif contract.expected_direction is None:
        expected_label = "outcome_recorded_without_quantified_prediction"
    elif expected_direction_result == "missed":
        expected_label = "missed_prediction"
    elif expected_range_result == "inside":
        expected_label = "matched_direction_and_range"
    else:
        expected_label = "matched_direction"
    return (
        grade.contract_id == contract.contract_id
        and grade.workflow_id == contract.workflow_id
        and grade.prediction_contract_sha256 == contract_digest
        and contract.contract_id == _stable_id("prediction", contract.workflow_id, "v1")
        and grade.grade_id == _stable_id("prediction_grade", grade.workflow_id, "v1")
        and grade.direction_result == expected_direction_result
        and grade.range_result == expected_range_result
        and grade.grade_label == expected_label
        and (grade.protocol_valid or grade.actual_effect_s is None)
    )


def get_prediction_grade(
    workflow_id: str,
    *,
    db_path: str | Path | None = None,
) -> PredictionGrade | None:
    connection = initialize_database(db_path)
    row = connection.execute(
        "SELECT grade_json FROM engineering_prediction_grades WHERE workflow_id = ?",
        (workflow_id,),
    ).fetchone()
    connection.close()
    return PredictionGrade.model_validate_json(row["grade_json"]) if row else None


def get_prediction_calibration(
    *,
    run_id: str | None = None,
    session_run_ids: Iterable[str] | None = None,
    context: Mapping[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> PredictionCalibrationSummary:
    """Return an exact-scope tally of genuinely gradable frozen predictions.

    This is a historical count, not a probability calibration. Invalid,
    inconclusive, unavailable, or direction-free predictions are excluded.
    """
    scope_requested = session_run_ids is not None or run_id is not None
    requested_runs = (
        session_run_ids
        if session_run_ids is not None
        else (() if run_id is None else (run_id,))
    )
    scope_run_ids = tuple(dict.fromkeys(str(item) for item in requested_runs))
    scope = set(scope_run_ids)
    expected_context = _normalized_context(context or {})
    expected_driver = str((context or {}).get("driver_user_id") or "").strip() or None
    connection = initialize_database(db_path)
    rows = connection.execute(
        "SELECT c.contract_id AS stored_contract_id, "
        "c.workflow_id AS stored_contract_workflow_id, "
        "c.source_run_id AS stored_source_run_id, "
        "g.grade_id AS stored_grade_id, "
        "g.contract_id AS stored_grade_contract_id, "
        "g.workflow_id AS stored_grade_workflow_id, "
        "c.contract_json, g.grade_json "
        "FROM engineering_prediction_contracts AS c "
        "JOIN engineering_prediction_grades AS g ON g.contract_id = c.contract_id "
        "ORDER BY g.created_at, g.grade_id"
    ).fetchall()
    context_rows = connection.execute(
        "SELECT workflow_id, observation_json FROM driver_presentation_observations "
        "WHERE kind = 'controlled_test_outcome'"
    ).fetchall() if expected_context or expected_driver else []
    connection.close()
    context_by_workflow: dict[str, DriverPresentationObservation] = {}
    for row in context_rows:
        try:
            observation = DriverPresentationObservation.model_validate_json(
                row["observation_json"]
            )
        except ValueError:
            continue
        if _presentation_observation_identity_is_valid(observation):
            context_by_workflow[row["workflow_id"]] = observation
    admitted: list[tuple[PredictionContract, PredictionGrade]] = []
    for row in rows:
        try:
            contract = PredictionContract.model_validate_json(row["contract_json"])
            grade = PredictionGrade.model_validate_json(row["grade_json"])
        except ValueError:
            continue
        if (
            contract.contract_id != row["stored_contract_id"]
            or contract.workflow_id != row["stored_contract_workflow_id"]
            or contract.source_run_id != row["stored_source_run_id"]
            or grade.grade_id != row["stored_grade_id"]
            or grade.contract_id != row["stored_grade_contract_id"]
            or grade.workflow_id != row["stored_grade_workflow_id"]
            or not _grade_matches_contract(grade, contract)
        ):
            continue
        if scope_requested and not scope:
            continue
        if scope and contract.source_run_id not in scope:
            continue
        if expected_context or expected_driver:
            observation = context_by_workflow.get(contract.workflow_id)
            if observation is None:
                continue
            if expected_context != observation.context_scope:
                continue
            if expected_driver is not None and expected_driver != observation.driver_id:
                continue
        if (
            not grade.protocol_valid
            or contract.expected_direction is None
            or grade.actual_direction not in {"decrease", "increase"}
            or grade.direction_result not in {"matched", "missed"}
        ):
            continue
        admitted.append((contract, grade))
    return PredictionCalibrationSummary(
        scope_run_ids=scope_run_ids,
        source_run_ids=tuple(dict.fromkeys(contract.source_run_id for contract, _grade in admitted)),
        workflow_ids=tuple(contract.workflow_id for contract, _grade in admitted),
        graded_predictions=len(admitted),
        matched_predictions=sum(grade.direction_result == "matched" for _contract, grade in admitted),
        score_is_probability=False,
    )


def build_prediction_contract(workflow: ControlledWorkflow) -> PredictionContract:
    packet = workflow.packet
    card = packet.primary_test
    components = packet.recommendation_score_components
    predicted = _finite(components.get("personal_model_prediction_s"))
    uncertainty = _finite(components.get("personal_model_uncertainty_s"))
    expected_range: tuple[float, float] | None = None
    expected_direction: str | None = None
    support = "unavailable"
    basis = "No evidence-qualified setup prediction was available before this workflow."

    if card is not None and predicted is not None and uncertainty is not None and uncertainty >= 0.0:
        expected_range = (round(predicted - uncertainty, 6), round(predicted + uncertainty, 6))
        if expected_range[1] < 0.0:
            expected_direction = "decrease"
        elif expected_range[0] > 0.0:
            expected_direction = "increase"
        support = "exact_context_model"
        basis = (
            "Qualified exact-context controlled response history produced this target-window range; "
            "it is not a promised gain or a probability."
        )
    elif card is not None and card.evidence_event_ids and packet.opportunity.source_channels:
        expected_direction = "decrease"
        support = "mechanism_evidence"
        basis = (
            "Eligible mechanism evidence supports testing for lower target-phase time, but no "
            "qualified numeric response range is available."
        )

    if card is not None:
        thresholds = list(card.success_metrics)
        noise = packet.opportunity.empirical_noise_s
        if noise is not None:
            thresholds.insert(
                0,
                "Every matched B-vs-A and B-vs-A2 target-phase effect must be lower than "
                f"-{noise:.6f} s (the frozen empirical noise floor).",
            )
        stop_rule = card.stop_rule
        rollback_rule = card.rollback_rule
        target_phase = card.target_phase
        mechanism = card.expected_mechanism
    else:
        mission = packet.measurement_mission
        thresholds = list(mission.acceptance_thresholds) if mission is not None else []
        stop_rule = mission.stop_rule if mission is not None else "Stop; no setup test is authorized."
        rollback_rule = "Keep or restore the unchanged baseline; no setup change was authorized."
        target_phase = packet.opportunity.phase
        mechanism = None

    return PredictionContract(
        contract_id=_stable_id("prediction", workflow.workflow_id, "v1"),
        workflow_id=workflow.workflow_id,
        created_at=workflow.created_at,
        source_run_id=workflow.source_run_id,
        target_metric="target_phase_time_s",
        target_phase=target_phase,
        support=support,
        expected_direction=expected_direction,
        expected_range_s=expected_range,
        expected_mechanism=mechanism,
        success_thresholds=tuple(dict.fromkeys(thresholds)),
        stop_rule=stop_rule,
        rollback_rule=rollback_rule,
        evidence_references=_prediction_references(workflow),
        ordinal_evidence_score=packet.confidence_score,
        score_basis=(packet.confidence_basis + " " + basis).strip(),
        score_is_probability=False,
    )


def build_prediction_grade(
    workflow: ControlledWorkflow,
    contract: PredictionContract,
) -> PredictionGrade:
    if workflow.quality is None or workflow.execution is None:
        raise ValueError("A scored workflow with execution and quality is required for grading.")
    quality = workflow.quality
    execution = workflow.execution
    effect = _finite(workflow.reproduction_snapshot.get("pooled_target_effect_s"))
    if effect is None:
        values = [
            value
            for value in (
                _finite(execution.phase_effect_b_vs_a_s),
                _finite(execution.phase_effect_b_vs_a2_s),
            )
            if value is not None
        ]
        effect = median(values) if len(values) == 2 else None

    if not quality.protocol_valid:
        actual_direction = "unavailable"
    elif execution.target_effect_distribution_state == "faster":
        actual_direction = "decrease"
    elif execution.target_effect_distribution_state == "slower":
        actual_direction = "increase"
    elif execution.target_effect_distribution_state in {"inconclusive", "inconsistent"}:
        actual_direction = "inconclusive"
    else:
        actual_direction = "unavailable"

    if contract.expected_direction is None or actual_direction == "unavailable":
        direction_result = "unavailable"
    elif actual_direction == "inconclusive":
        direction_result = "inconclusive"
    elif actual_direction == contract.expected_direction:
        direction_result = "matched"
    else:
        direction_result = "missed"

    if not quality.protocol_valid or contract.expected_range_s is None or effect is None:
        range_result = "unavailable"
    elif actual_direction == "inconclusive":
        range_result = "inconclusive"
    elif contract.expected_range_s[0] <= effect <= contract.expected_range_s[1]:
        range_result = "inside"
    else:
        range_result = "outside"

    if not quality.protocol_valid:
        label = "not_gradable_protocol_invalid"
    elif actual_direction in {"inconclusive", "unavailable"}:
        label = "inconclusive"
    elif contract.expected_direction is None:
        label = "outcome_recorded_without_quantified_prediction"
    elif direction_result == "missed":
        label = "missed_prediction"
    elif range_result == "inside":
        label = "matched_direction_and_range"
    else:
        label = "matched_direction"

    contract_json = _canonical_json(contract)
    return PredictionGrade(
        grade_id=_stable_id("prediction_grade", workflow.workflow_id, "v1"),
        contract_id=contract.contract_id,
        workflow_id=workflow.workflow_id,
        created_at=workflow.updated_at,
        prediction_contract_sha256=hashlib.sha256(contract_json.encode("utf-8")).hexdigest(),
        actual_effect_s=effect if quality.protocol_valid else None,
        actual_direction=actual_direction,
        direction_result=direction_result,
        range_result=range_result,
        grade_label=label,
        workflow_verdict=quality.verdict,
        protocol_valid=quality.protocol_valid,
        protocol_evidence_score=quality.score,
        score_is_probability=False,
        evidence_references=_workflow_references(workflow),
    )


def _workflow_scopes(
    workflow: ControlledWorkflow,
    db_path: str | Path | None,
) -> tuple[tuple[str, str | None], ...]:
    run_ids = set(_workflow_run_ids(workflow))
    sessions = [
        session
        for session in list_sessions(include_archived=True, db_path=db_path)
        if run_ids & set(session.run_ids)
    ]
    if sessions:
        return tuple((session.session_id, session.session_id) for session in sessions)
    return ((f"run:{workflow.source_run_id}", None),)


def save_narrative_entry(
    entry: EngineeringNarrativeEntry,
    *,
    db_path: str | Path | None = None,
) -> EngineeringNarrativeEntry:
    _insert_immutable(
        table="engineering_narrative_entries",
        id_column="entry_id",
        record_id=entry.entry_id,
        payload_column="entry_json",
        payload=entry,
        columns={
            "created_at": entry.created_at.isoformat(),
            "scope_id": entry.scope_id,
            "session_id": entry.session_id,
            "entry_type": entry.entry_type,
            "workflow_id": entry.workflow_id,
            "run_ids_json": _canonical_json(entry.run_ids),
        },
        db_path=db_path,
    )
    return entry


def _record_narrative(
    workflow: ControlledWorkflow,
    *,
    entry_type: NarrativeEntryType,
    variant: str,
    text: str,
    created_at: datetime,
    metadata: Mapping[str, Any] | None,
    db_path: str | Path | None = None,
    run_ids: tuple[str, ...] | None = None,
    evidence_references: tuple[EngineeringEvidenceReference, ...] | None = None,
) -> tuple[EngineeringNarrativeEntry, ...]:
    entries: list[EngineeringNarrativeEntry] = []
    for scope_id, session_id in _workflow_scopes(workflow, db_path):
        entry = EngineeringNarrativeEntry(
            entry_id=_stable_id(
                "narrative",
                workflow.workflow_id,
                scope_id,
                entry_type,
                variant,
            ),
            created_at=created_at,
            scope_id=scope_id,
            session_id=session_id,
            entry_type=entry_type,
            text=text,
            run_ids=run_ids or _workflow_run_ids(workflow),
            workflow_id=workflow.workflow_id,
            evidence_references=evidence_references or _workflow_references(workflow),
            metadata=dict(metadata or {}),
        )
        entries.append(save_narrative_entry(entry, db_path=db_path))
    return tuple(entries)


def list_engineering_narrative(
    *,
    session_id: str | None = None,
    run_id: str | None = None,
    workflow_id: str | None = None,
    db_path: str | Path | None = None,
) -> tuple[EngineeringNarrativeEntry, ...]:
    connection = initialize_database(db_path)
    sql = (
        "SELECT entry_id, created_at, scope_id, session_id, entry_type, workflow_id, "
        "run_ids_json, entry_json FROM engineering_narrative_entries WHERE 1=1"
    )
    params: list[Any] = []
    if session_id is not None:
        sql += " AND session_id = ?"
        params.append(session_id)
    if workflow_id is not None:
        sql += " AND workflow_id = ?"
        params.append(workflow_id)
    sql += " ORDER BY created_at, entry_id"
    rows = connection.execute(sql, params).fetchall()
    connection.close()
    session = get_session(session_id, db_path) if session_id is not None else None
    session_runs = set(session.run_ids) if session is not None else set()
    entries: list[EngineeringNarrativeEntry] = []
    for row in rows:
        try:
            entry = EngineeringNarrativeEntry.model_validate_json(row["entry_json"])
            stored_run_ids = tuple(json.loads(row["run_ids_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            entry.entry_id != row["entry_id"]
            or entry.created_at.isoformat() != row["created_at"]
            or entry.scope_id != row["scope_id"]
            or entry.session_id != row["session_id"]
            or entry.entry_type != row["entry_type"]
            or entry.workflow_id != row["workflow_id"]
            or entry.run_ids != stored_run_ids
            or not _narrative_references_are_valid(entry)
            or run_id is not None and run_id not in entry.run_ids
            or session_id is not None
            and (
                session is None
                or entry.session_id != session_id
                or not set(entry.run_ids) & session_runs
            )
        ):
            continue
        entries.append(entry)
    return tuple(entries)


def _normalized_context(context: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: str(context[key]).strip()
        for key in _CONTEXT_KEYS
        if context.get(key) is not None and str(context[key]).strip()
    }


def presentation_profile_identity(
    driver_id: str,
    context: Mapping[str, Any],
) -> tuple[str, str, dict[str, str]]:
    scope = _normalized_context(context)
    context_key = hashlib.sha256(_canonical_json(scope).encode("utf-8")).hexdigest()
    profile_id = _stable_id("driver_profile", driver_id, context_key)
    return profile_id, context_key, scope


def _presentation_observation_identity_is_valid(
    observation: DriverPresentationObservation,
) -> bool:
    if not observation.driver_id.strip():
        return False
    expected_profile_id, expected_context_key, expected_scope = (
        presentation_profile_identity(observation.driver_id, observation.context_scope)
    )
    return (
        observation.profile_id == expected_profile_id
        and observation.context_key == expected_context_key
        and observation.context_scope == expected_scope
    )


def _profile_identity_from_compatibility(
    identity: Mapping[str, Any],
    *,
    run_id: str,
) -> tuple[str, str, str, dict[str, str]]:
    driver_id = str(identity.get("driver_user_id") or f"unknown:{run_id}")
    context: dict[str, Any] = dict(identity)
    if driver_id.startswith("unknown:"):
        context["car_id"] = context.get("car_id") or run_id
    profile_id, context_key, scope = presentation_profile_identity(driver_id, context)
    return profile_id, driver_id, context_key, scope


def _run_presentation_identity(
    run_id: str,
    db_path: str | Path | None,
) -> tuple[str, str, str, dict[str, str]]:
    identity: dict[str, Any] = {}
    try:
        from racelab_engine.services.import_service import read_telemetry_manifest

        identity = read_telemetry_manifest(run_id).get("compatibility_identity") or {}
    except (AttributeError, FileNotFoundError, OSError, TypeError, ValueError):
        identity = {}
    if not identity:
        from racelab_engine.storage.repository import RaceLabRepository

        overview = RaceLabRepository(db_path).get_overview(run_id)
        if overview is not None:
            identity = {
                "car_path": overview.session.car_path,
                "track_id": overview.session.track_id_or_path,
                "session_type": overview.session.session_type,
            }
    return _profile_identity_from_compatibility(identity, run_id=run_id)


def _workflow_presentation_identity(
    workflow: ControlledWorkflow,
    db_path: str | Path | None,
) -> tuple[str, str, str, dict[str, str]]:
    stages = workflow.reproduction_snapshot.get("stages") or {}
    stage_a = stages.get("A") if isinstance(stages, dict) else None
    identity = (
        stage_a.get("compatibility_identity")
        if isinstance(stage_a, dict)
        else None
    ) or {}
    if not identity:
        return _run_presentation_identity(workflow.source_run_id, db_path)
    return _profile_identity_from_compatibility(identity, run_id=workflow.source_run_id)


def save_driver_presentation_observation(
    observation: DriverPresentationObservation,
    *,
    db_path: str | Path | None = None,
) -> DriverPresentationObservation:
    if not _presentation_observation_identity_is_valid(observation):
        raise ValueError(
            "A presentation observation must match its exact driver and normalized context identity."
        )
    connection = initialize_database(db_path)
    row = connection.execute(
        "SELECT observation_json FROM driver_presentation_observations WHERE source_key = ?",
        (observation.source_key,),
    ).fetchone()
    connection.close()
    if row is not None:
        existing = DriverPresentationObservation.model_validate_json(row["observation_json"])
        if existing != observation:
            raise ValueError(
                f"Presentation source {observation.source_key} already has a different immutable observation."
            )
        return existing
    _insert_immutable(
        table="driver_presentation_observations",
        id_column="observation_id",
        record_id=observation.observation_id,
        payload_column="observation_json",
        payload=observation,
        columns={
            "created_at": observation.created_at.isoformat(),
            "source_key": observation.source_key,
            "profile_id": observation.profile_id,
            "driver_id": observation.driver_id,
            "context_key": observation.context_key,
            "kind": observation.kind,
            "run_id": observation.run_id,
            "workflow_id": observation.workflow_id,
        },
        db_path=db_path,
    )
    return observation


def record_driver_presentation_preference(
    *,
    driver_id: str,
    context: Mapping[str, Any],
    source_key: str,
    preferred_mode: str | None = None,
    terminology_level: str | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
    db_path: str | Path | None = None,
) -> DriverPresentationObservation:
    if preferred_mode is None and terminology_level is None:
        raise ValueError("At least one explicit presentation preference is required.")
    profile_id, context_key, scope = presentation_profile_identity(driver_id, context)
    observation_id = _stable_id("driver_observation", source_key)
    connection = initialize_database(db_path)
    existing = connection.execute(
        "SELECT observation_json FROM driver_presentation_observations WHERE observation_id = ?",
        (observation_id,),
    ).fetchone()
    connection.close()
    if existing is not None:
        persisted = DriverPresentationObservation.model_validate_json(existing["observation_json"])
        if (
            persisted.driver_id != driver_id
            or persisted.context_key != context_key
            or persisted.preferred_mode != preferred_mode
            or persisted.terminology_level != terminology_level
            or persisted.run_id != run_id
        ):
            raise ValueError("An explicit preference source key cannot be rewritten.")
        return persisted
    observation = DriverPresentationObservation(
        observation_id=observation_id,
        created_at=created_at or _utc_now(),
        source_key=source_key,
        profile_id=profile_id,
        driver_id=driver_id,
        context_key=context_key,
        context_scope=scope,
        kind="explicit_preference",
        preferred_mode=preferred_mode,
        terminology_level=terminology_level,
        run_id=run_id,
    )
    return save_driver_presentation_observation(observation, db_path=db_path)


def record_driver_presentation_preference_for_run(
    run_id: str,
    *,
    source_key: str,
    preferred_mode: str | None = None,
    terminology_level: str | None = None,
    created_at: datetime | None = None,
    db_path: str | Path | None = None,
) -> DriverPresentationObservation:
    """Persist an explicit UI preference without exposing identity fields to clients."""
    _profile_id, driver_id, _context_key, scope = _run_presentation_identity(run_id, db_path)
    return record_driver_presentation_preference(
        driver_id=driver_id,
        context=scope,
        source_key=source_key,
        preferred_mode=preferred_mode,
        terminology_level=terminology_level,
        run_id=run_id,
        created_at=created_at,
        db_path=db_path,
    )


def _record_workflow_presentation_observation(
    workflow: ControlledWorkflow,
    *,
    kind: str,
    db_path: str | Path | None,
) -> DriverPresentationObservation:
    source_key = f"workflow:{workflow.workflow_id}:{kind}"
    observation_id = _stable_id("driver_observation", source_key)
    connection = initialize_database(db_path)
    existing = connection.execute(
        "SELECT observation_json FROM driver_presentation_observations WHERE observation_id = ?",
        (observation_id,),
    ).fetchone()
    connection.close()
    if existing is not None:
        return DriverPresentationObservation.model_validate_json(existing["observation_json"])
    profile_id, driver_id, context_key, scope = _workflow_presentation_identity(
        workflow, db_path
    )
    observation = DriverPresentationObservation(
        observation_id=observation_id,
        created_at=workflow.created_at if kind == "symptom_observed" else workflow.updated_at,
        source_key=source_key,
        profile_id=profile_id,
        driver_id=driver_id,
        context_key=context_key,
        context_scope=scope,
        kind=kind,
        canonical_symptom=(
            workflow.packet.canonical_symptom if kind == "symptom_observed" else None
        ),
        symptom_phrase=workflow.complaint if kind == "symptom_observed" else None,
        protocol_valid=(
            workflow.quality.protocol_valid
            if kind == "controlled_test_outcome" and workflow.quality is not None
            else None
        ),
        driver_match_score=(
            workflow.execution.driver_match_score
            if kind == "controlled_test_outcome" and workflow.execution is not None
            else None
        ),
        run_id=workflow.source_run_id,
        workflow_id=workflow.workflow_id,
    )
    return save_driver_presentation_observation(observation, db_path=db_path)


def _profile_from_observations(
    observations: Iterable[DriverPresentationObservation],
) -> DriverPresentationProfile:
    ordered = sorted(observations, key=lambda item: (item.created_at, item.observation_id))
    if not ordered:
        raise ValueError("At least one presentation observation is required.")
    first = ordered[0]
    identities = [
        presentation_profile_identity(item.driver_id, item.context_scope)
        for item in ordered
    ]
    if any(
        item.profile_id != expected_profile_id
        or item.context_key != expected_context_key
        or item.context_scope != expected_scope
        for item, (expected_profile_id, expected_context_key, expected_scope) in zip(
            ordered, identities, strict=True,
        )
    ):
        raise ValueError("A presentation observation has an invalid driver/context identity.")
    if any(
        item.profile_id != first.profile_id
        or item.driver_id != first.driver_id
        or item.context_key != first.context_key
        or item.context_scope != first.context_scope
        for item in ordered
    ):
        raise ValueError("Presentation observations from different context scopes cannot be merged.")
    preferred_mode = "race"
    terminology_level = "standard"
    for item in ordered:
        if item.kind == "explicit_preference":
            preferred_mode = item.preferred_mode or preferred_mode
            terminology_level = item.terminology_level or terminology_level

    try:
        canonical_symptoms = {
            item.canonical_symptom
            for item in load_setup_knowledge().symptom_vocabulary
        }
    except (FileNotFoundError, OSError, TypeError, ValueError):
        canonical_symptoms = set()
    symptom_counts: Counter[str] = Counter()
    phrases: dict[str, list[str]] = defaultdict(list)
    for item in ordered:
        if (
            item.kind != "symptom_observed"
            or not item.canonical_symptom
            or item.canonical_symptom not in canonical_symptoms
        ):
            continue
        symptom_counts[item.canonical_symptom] += 1
        phrase = (item.symptom_phrase or "").strip()
        if phrase and phrase not in phrases[item.canonical_symptom]:
            phrases[item.canonical_symptom].append(phrase)
    recurring = tuple(
        RecurringSymptom(
            canonical_symptom=symptom,
            observations=count,
            phrases=tuple(phrases[symptom][:3]),
        )
        for symptom, count in sorted(
            symptom_counts.items(), key=lambda item: (-item[1], item[0])
        )
    )

    completed = [item for item in ordered if item.kind == "controlled_test_outcome"]
    valid_matches = [
        item.driver_match_score
        for item in completed
        if item.protocol_valid is True and item.driver_match_score is not None
    ]
    if not valid_matches:
        consistency = "unavailable"
    elif len(valid_matches) < 3:
        consistency = "insufficient_history"
    elif all(score >= 0.8 for score in valid_matches):
        consistency = "consistent_in_controlled_tests"
    else:
        consistency = "mixed_in_controlled_tests"
    return DriverPresentationProfile(
        profile_id=first.profile_id,
        driver_id=first.driver_id,
        context_key=first.context_key,
        scope=first.context_scope,
        preferred_mode=preferred_mode,
        terminology_level=terminology_level,
        recurring_symptoms=recurring,
        controlled_tests_completed=len(completed),
        consistency_label=consistency,
        affects_evidence_eligibility=False,
    )


def get_driver_presentation_profile(
    *,
    driver_id: str,
    context: Mapping[str, Any],
    db_path: str | Path | None = None,
) -> DriverPresentationProfile:
    profile_id, context_key, scope = presentation_profile_identity(driver_id, context)
    connection = initialize_database(db_path)
    rows = connection.execute(
        "SELECT observation_json FROM driver_presentation_observations "
        "WHERE profile_id = ? ORDER BY created_at, observation_id",
        (profile_id,),
    ).fetchall()
    connection.close()
    observations: list[DriverPresentationObservation] = []
    for row in rows:
        try:
            observation = DriverPresentationObservation.model_validate_json(
                row["observation_json"]
            )
        except ValueError:
            continue
        if (
            _presentation_observation_identity_is_valid(observation)
            and observation.profile_id == profile_id
            and observation.driver_id == driver_id
            and observation.context_key == context_key
            and observation.context_scope == scope
        ):
            observations.append(observation)
    if not observations:
        return DriverPresentationProfile(
            profile_id=profile_id,
            driver_id=driver_id,
            context_key=context_key,
            scope=scope,
            controlled_tests_completed=0,
            consistency_label="unavailable",
            affects_evidence_eligibility=False,
        )
    return _profile_from_observations(observations)


def get_driver_presentation_profile_by_id(
    profile_id: str,
    *,
    db_path: str | Path | None = None,
) -> DriverPresentationProfile | None:
    connection = initialize_database(db_path)
    rows = connection.execute(
        "SELECT observation_json FROM driver_presentation_observations "
        "WHERE profile_id = ? ORDER BY created_at, observation_id",
        (profile_id,),
    ).fetchall()
    connection.close()
    observations: list[DriverPresentationObservation] = []
    for row in rows:
        try:
            observation = DriverPresentationObservation.model_validate_json(
                row["observation_json"]
            )
        except ValueError:
            continue
        if (
            _presentation_observation_identity_is_valid(observation)
            and observation.profile_id == profile_id
        ):
            observations.append(observation)
    if not observations:
        return None
    return _profile_from_observations(observations)


def get_driver_presentation_profile_for_run(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> DriverPresentationProfile:
    """Read the presentation-only profile in the run's exact compatibility scope."""
    _profile_id, driver_id, _context_key, scope = _run_presentation_identity(run_id, db_path)
    return get_driver_presentation_profile(
        driver_id=driver_id,
        context=scope,
        db_path=db_path,
    )


def record_workflow_plan(
    workflow: ControlledWorkflow,
    *,
    db_path: str | Path | None = None,
) -> PredictionContract:
    contract = save_prediction_contract(build_prediction_contract(workflow), db_path=db_path)
    _record_narrative(
        workflow,
        entry_type="complaint",
        variant="initial",
        text=workflow.complaint,
        created_at=workflow.created_at,
        metadata={"canonical_symptom": workflow.packet.canonical_symptom},
        run_ids=(workflow.source_run_id,),
        evidence_references=_prediction_references(workflow),
        db_path=db_path,
    )
    if workflow.packet.primary_test is not None:
        card = workflow.packet.primary_test
        _record_narrative(
            workflow,
            entry_type="hypothesis",
            variant="initial",
            text=card.hypothesis,
            created_at=workflow.created_at,
            metadata={"target_phase": card.target_phase, "control_key": card.control_key},
            run_ids=(workflow.source_run_id,),
            evidence_references=_prediction_references(workflow),
            db_path=db_path,
        )
        measurement_text = (
            "Run the frozen A/B/A2 protocol and grade B against both A and restored A2."
        )
    else:
        mission = workflow.packet.measurement_mission
        measurement_text = mission.purpose if mission is not None else "Collect missing evidence."
    _record_narrative(
        workflow,
        entry_type="measurement",
        variant="initial",
        text=measurement_text,
        created_at=workflow.created_at,
        metadata={"success_thresholds": list(contract.success_thresholds)},
        run_ids=(workflow.source_run_id,),
        evidence_references=_prediction_references(workflow),
        db_path=db_path,
    )
    _record_workflow_presentation_observation(
        workflow,
        kind="symptom_observed",
        db_path=db_path,
    )
    return contract


def record_workflow_stage(
    workflow: ControlledWorkflow,
    stage: str,
    *,
    db_path: str | Path | None = None,
) -> tuple[EngineeringNarrativeEntry, ...]:
    if stage != "B" or workflow.packet.primary_test is None:
        return ()
    card = workflow.packet.primary_test
    return _record_narrative(
        workflow,
        entry_type="change",
        variant="stage-b",
        text=card.exact_change,
        created_at=workflow.updated_at,
        metadata={
            "stage": "B",
            "control_key": card.control_key,
            "stage_run_id": workflow.stage_run_ids.get("B"),
        },
        db_path=db_path,
    )


def record_workflow_outcome(
    workflow: ControlledWorkflow,
    *,
    db_path: str | Path | None = None,
) -> PredictionGrade:
    contract = get_prediction_contract(workflow.workflow_id, db_path=db_path)
    if contract is None:
        contract = save_prediction_contract(build_prediction_contract(workflow), db_path=db_path)
    grade = save_prediction_grade(build_prediction_grade(workflow, contract), db_path=db_path)
    _record_narrative(
        workflow,
        entry_type="outcome",
        variant="scored",
        text=(
            f"Controlled workflow verdict: {grade.workflow_verdict}; prediction grade: "
            f"{grade.grade_label.replace('_', ' ')}."
        ),
        created_at=workflow.updated_at,
        metadata={
            "workflow_verdict": grade.workflow_verdict,
            "prediction_grade": grade.grade_label,
            "actual_effect_s": grade.actual_effect_s,
            "protocol_valid": grade.protocol_valid,
        },
        db_path=db_path,
    )
    if grade.workflow_verdict == "undo":
        _record_narrative(
            workflow,
            entry_type="rollback",
            variant="scored-undo",
            text=contract.rollback_rule,
            created_at=workflow.updated_at,
            metadata={"reason": "controlled_workflow_undo"},
            db_path=db_path,
        )
    _record_narrative(
        workflow,
        entry_type="learning",
        variant="prediction-grade",
        text=(
            "The frozen pre-test prediction was graded against the controlled outcome as "
            f"{grade.grade_label.replace('_', ' ')}."
        ),
        created_at=workflow.updated_at,
        metadata={
            "score_basis": grade.score_basis,
            "score_is_probability": False,
            "learning_admitted": workflow.learning_admitted,
        },
        db_path=db_path,
    )
    _record_workflow_presentation_observation(
        workflow,
        kind="controlled_test_outcome",
        db_path=db_path,
    )
    return grade


def record_workflow_cancellation(
    workflow: ControlledWorkflow,
    *,
    db_path: str | Path | None = None,
) -> tuple[EngineeringNarrativeEntry, ...]:
    contract = get_prediction_contract(workflow.workflow_id, db_path=db_path)
    rollback_rule = (
        contract.rollback_rule
        if contract is not None
        else "Restore the unchanged baseline; the unfinished test was abandoned."
    )
    return _record_narrative(
        workflow,
        entry_type="rollback",
        variant="cancelled",
        text=f"Controlled test explicitly abandoned. {rollback_rule}",
        created_at=workflow.updated_at,
        metadata={"reason": "explicit_abandon", "status": workflow.status},
        db_path=db_path,
    )


__all__ = [
    "build_prediction_contract",
    "build_prediction_grade",
    "get_driver_presentation_profile",
    "get_driver_presentation_profile_by_id",
    "get_driver_presentation_profile_for_run",
    "get_prediction_calibration",
    "get_prediction_contract",
    "get_prediction_grade",
    "list_engineering_narrative",
    "presentation_profile_identity",
    "record_driver_presentation_preference",
    "record_driver_presentation_preference_for_run",
    "record_workflow_cancellation",
    "record_workflow_outcome",
    "record_workflow_plan",
    "record_workflow_stage",
    "save_driver_presentation_observation",
    "save_narrative_entry",
    "save_prediction_contract",
    "save_prediction_grade",
]
