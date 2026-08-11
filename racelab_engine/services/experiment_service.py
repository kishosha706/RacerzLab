"""Materialize immutable missions and stop repeated low-information testing."""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

from racelab_engine.models.experiment import (
    MeasurementAttempt,
    MeasurementMissionContract,
    SessionResourceSnapshot,
)
from racelab_engine.models.intelligence import InformationPlan
from racelab_engine.storage.repository import RaceLabRepository


def _contract_payload(
    plan: InformationPlan,
    *,
    candidate_id: str,
    run_id: str,
    session_id: str | None,
    session_run_ids: Sequence[str],
    source_setup_id: str,
    setup_sha256: str,
    compatibility_fingerprint: str,
    required_channels: Sequence[str],
    cause_ids: Sequence[str],
    telemetry_health_identity: str,
    resource_snapshot: SessionResourceSnapshot,
) -> dict[str, object]:
    if plan.kind == "measurement_mission" and plan.measurement_mission is not None:
        mission = plan.measurement_mission
        purpose = mission.purpose
        procedure = tuple(mission.procedure)
        required_laps = mission.required_laps_or_passes
        controlled_variables = tuple(mission.controlled_variables)
        acceptance = tuple(mission.acceptance_thresholds)
        stop_rules = (mission.stop_rule,)
    elif plan.kind == "discriminator" and plan.discriminator is not None:
        discriminator = plan.discriminator
        purpose = plan.rationale
        procedure = (discriminator.instruction,)
        required_laps = 3
        controlled_variables = (
            "setup",
            "fuel range",
            "tire state",
            "weather",
            "driving line",
            "nearby-car context",
        )
        acceptance = tuple(discriminator.acceptance_thresholds)
        stop_rules = (
            "Stop after a pit, reset, incident, setup change, invalid lap, or telemetry-integrity fault.",
        )
    else:
        raise ValueError("only collection plans can become mission contracts")
    return {
        "schema_version": "p19.measurement-mission.v2",
        "candidate_id": candidate_id,
        "run_id": run_id,
        "session_id": session_id,
        "session_run_ids": tuple(sorted(set(session_run_ids))),
        "source_setup_id": source_setup_id,
        "setup_sha256": setup_sha256,
        "compatibility_fingerprint": compatibility_fingerprint,
        "purpose": purpose,
        "procedure": procedure,
        "required_channels": tuple(dict.fromkeys(required_channels)),
        "controlled_variables": controlled_variables,
        "required_laps": required_laps,
        "acceptance_thresholds": acceptance,
        "integrity_stop_rules": stop_rules,
        "source_event_ids": tuple(plan.source_event_ids),
        "cause_ids": tuple(dict.fromkeys(cause_ids)),
        "telemetry_health_identity": telemetry_health_identity,
        "resource_snapshot": resource_snapshot.model_dump(
            mode="json", exclude={"captured_at"}
        ),
    }


def materialize_mission_contract(
    plan: InformationPlan,
    *,
    candidate_id: str,
    run_id: str,
    session_id: str | None = None,
    session_run_ids: Sequence[str],
    source_setup_id: str,
    setup_sha256: str,
    compatibility_fingerprint: str,
    required_channels: Sequence[str] = (),
    cause_ids: Sequence[str] = (),
    telemetry_health_identity: str = "health:unknown",
    resource_snapshot: SessionResourceSnapshot | None = None,
) -> MeasurementMissionContract:
    resources = resource_snapshot or SessionResourceSnapshot()
    payload = _contract_payload(
        plan,
        candidate_id=candidate_id,
        run_id=run_id,
        session_id=session_id,
        session_run_ids=session_run_ids,
        source_setup_id=source_setup_id,
        setup_sha256=setup_sha256,
        compatibility_fingerprint=compatibility_fingerprint,
        required_channels=required_channels,
        cause_ids=cause_ids,
        telemetry_health_identity=telemetry_health_identity,
        resource_snapshot=resources,
    )
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return MeasurementMissionContract(
        contract_id=f"mission:{digest[:20]}",
        contract_sha256=digest,
        resource_snapshot=resources,
        **{key: value for key, value in payload.items() if key != "resource_snapshot"},
    )


def bind_experiment_lifecycle(
    plan: InformationPlan,
    *,
    candidate_id: str,
    run_id: str,
    session_id: str | None = None,
    session_run_ids: Sequence[str],
    source_setup_id: str,
    setup_sha256: str,
    compatibility_fingerprint: str,
    required_channels: Sequence[str] = (),
    cause_ids: Sequence[str] = (),
    telemetry_health_identity: str = "health:unknown",
    resource_snapshot: SessionResourceSnapshot | None = None,
    prior_attempts: Sequence[MeasurementAttempt] = (),
) -> InformationPlan:
    if plan.kind not in {"measurement_mission", "discriminator"}:
        return plan
    contract = materialize_mission_contract(
        plan,
        candidate_id=candidate_id,
        run_id=run_id,
        session_id=session_id,
        session_run_ids=session_run_ids,
        source_setup_id=source_setup_id,
        setup_sha256=setup_sha256,
        compatibility_fingerprint=compatibility_fingerprint,
        required_channels=required_channels,
        cause_ids=cause_ids,
        telemetry_health_identity=telemetry_health_identity,
        resource_snapshot=resource_snapshot,
    )
    feasible_laps = contract.resource_snapshot.feasible_laps
    if feasible_laps is not None and feasible_laps < contract.required_laps:
        return InformationPlan(
            kind="stop_testing",
            title="Stop: this mission is infeasible in the remaining session",
            instruction="Preserve the contract for the next session instead of collecting a partial run.",
            rationale=(
                f"The mission requires {contract.required_laps} eligible laps, but at most "
                f"{feasible_laps} remain under the captured fuel/lap resources."
            ),
            mission_contract=contract,
            blocker_reasons=("Insufficient remaining session resources for a clean mission.",),
        )
    matching = [
        attempt
        for attempt in prior_attempts
        if attempt.contract_id == contract.contract_id
        and attempt.contract_sha256 == contract.contract_sha256
    ]
    repeated_low_information = 0
    counted_run_ids: set[str] = set()
    for attempt in reversed(matching):
        if attempt.outcome_authority != "server_derived":
            continue
        if attempt.counts_toward_stop_testing:
            # Adjacent/disjoint lap cohorts from one run share acquisition context and
            # therefore contribute at most one independent stop-testing vote.
            if attempt.run_id in counted_run_ids:
                continue
            counted_run_ids.add(attempt.run_id)
            repeated_low_information += 1
        else:
            break
    if repeated_low_information >= 2:
        return InformationPlan(
            kind="stop_testing",
            title="Stop repeating this measurement contract",
            instruction="Change the measurement design or restore integrity before another attempt.",
            rationale=(
                "Two consecutive exact-contract run acquisitions produced no usable information; "
                "more unchanged repetition is not currently justified."
            ),
            mission_contract=contract,
            blocker_reasons=(
                "Two independently acquired server-derived no-signal or integrity outcomes triggered the stop-testing rule.",
            ),
        )
    return plan.model_copy(update={"mission_contract": contract})


def bind_durable_experiment_lifecycle(
    plan: InformationPlan,
    *,
    candidate_id: str,
    run_id: str,
    repository: RaceLabRepository,
    session_id: str | None = None,
    session_run_ids: Sequence[str],
    source_setup_id: str,
    setup_sha256: str,
    compatibility_fingerprint: str,
    required_channels: Sequence[str] = (),
    cause_ids: Sequence[str] = (),
    telemetry_health_identity: str = "health:unknown",
    resource_snapshot: SessionResourceSnapshot | None = None,
) -> InformationPlan:
    """Bind a plan to append-only history and replay exact attempts after restart."""
    provisional = bind_experiment_lifecycle(
        plan,
        candidate_id=candidate_id,
        run_id=run_id,
        session_id=session_id,
        session_run_ids=session_run_ids,
        source_setup_id=source_setup_id,
        setup_sha256=setup_sha256,
        compatibility_fingerprint=compatibility_fingerprint,
        required_channels=required_channels,
        cause_ids=cause_ids,
        telemetry_health_identity=telemetry_health_identity,
        resource_snapshot=resource_snapshot,
    )
    contract = provisional.mission_contract
    if contract is None:
        return provisional
    repository.save_measurement_mission_contract(contract)
    attempts = repository.list_measurement_mission_attempts(contract)
    return bind_experiment_lifecycle(
        plan,
        candidate_id=candidate_id,
        run_id=run_id,
        session_id=session_id,
        session_run_ids=session_run_ids,
        source_setup_id=source_setup_id,
        setup_sha256=setup_sha256,
        compatibility_fingerprint=compatibility_fingerprint,
        required_channels=required_channels,
        cause_ids=cause_ids,
        telemetry_health_identity=telemetry_health_identity,
        resource_snapshot=resource_snapshot,
        prior_attempts=attempts,
    )


def record_durable_measurement_attempt(
    contract: MeasurementMissionContract,
    attempt: MeasurementAttempt,
    *,
    repository: RaceLabRepository,
) -> None:
    """Persist a typed outcome only when it binds the exact immutable contract."""
    if (
        attempt.run_id not in contract.session_run_ids
        or attempt.setup_sha256 != contract.setup_sha256
        or attempt.compatibility_fingerprint != contract.compatibility_fingerprint
    ):
        raise ValueError(
            "measurement attempt run/setup/build identity does not match its mission contract"
        )
    prior_attempts = repository.list_measurement_mission_attempts(contract)
    attempt_laps = set(attempt.eligible_lap_ids)
    for prior in prior_attempts:
        prior_laps = set(prior.eligible_lap_ids)
        if attempt_laps and prior_laps and attempt_laps & prior_laps:
            raise ValueError(
                "measurement attempts require non-overlapping eligible-lap cohorts"
            )
        if not attempt_laps and not prior_laps and attempt.run_id == prior.run_id:
            raise ValueError(
                "unscoped measurement attempts require a distinct run identity"
            )
    repository.record_measurement_mission_attempt(contract, attempt)


__all__ = [
    "bind_durable_experiment_lifecycle",
    "bind_experiment_lifecycle",
    "materialize_mission_contract",
    "record_durable_measurement_attempt",
]
