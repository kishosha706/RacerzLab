"""P19-owned, non-mutating admission of exact response observations.

Relationship knowledge can identify a relevant observation.  Only a complete
ResponseExpectationContract can turn that observation into support or
contradiction, and this adapter never changes P19 rank or terminal authority.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from racelab_engine.knowledge.engineering_semantic_registry import semantic_entry
from racelab_engine.models.engineering_case import (
    EngineeringResponseArtifact,
    P19ResponseAdmission,
    P19ResponseCauseAssessment,
    ResponseExpectationContract,
    ResponseExpectationEvaluation,
)


def evaluate_response_expectation(
    contract: ResponseExpectationContract,
    artifact: EngineeringResponseArtifact,
    *,
    context_states: Sequence[str],
    car_identity: str | None = None,
    build_identity: str | None = None,
) -> ResponseExpectationEvaluation:
    blockers: list[str] = []
    unavailable: list[str] = []
    if contract.relation_id != artifact.relation:
        unavailable.append("Response relation does not match the reviewed contract.")
    if contract.phase.casefold() != artifact.phase.casefold():
        unavailable.append("Response phase does not match the reviewed contract.")
    if contract.lap_pct_start is not None and (
        artifact.lap_pct_start < contract.lap_pct_start
        or artifact.lap_pct_end > contract.lap_pct_end  # type: ignore[operator]
    ):
        unavailable.append("Response physical scope falls outside the reviewed contract.")
    if contract.speed_min_mps is not None:
        if artifact.speed_min_mps is None or artifact.speed_max_mps is None:
            unavailable.append("Response speed band is unavailable.")
        elif (
            artifact.speed_min_mps < contract.speed_min_mps
            or artifact.speed_max_mps > contract.speed_max_mps  # type: ignore[operator]
        ):
            unavailable.append("Response speed band falls outside the reviewed contract.")
    if artifact.operational_evidence.repetition_count < (
        contract.minimum_independent_repetitions
    ):
        blockers.append("Independent response repetition is below the contract minimum.")
    if not set(contract.required_channel_ids) <= set(
        artifact.operational_evidence.source_channels
    ):
        blockers.append("Required response channel lineage is incomplete.")
    if artifact.evidence_state not in contract.allowed_evidence_states:
        blockers.append("Response evidence state is not admitted by the contract.")
    if not set(contract.required_context_states) <= set(context_states):
        blockers.append("Required response context gates are not satisfied.")
    if car_identity is not None and not (
        "all" in contract.car_applicability
        or car_identity in contract.car_applicability
    ):
        unavailable.append("Response contract does not apply to this car identity.")
    if build_identity is not None and not (
        "all" in contract.build_applicability
        or build_identity in contract.build_applicability
    ):
        unavailable.append("Response contract does not apply to this iRacing build.")

    metrics = {
        item.metric_id: item for item in artifact.operational_evidence.metrics
    }
    metric = metrics.get(contract.metric_id)
    if metric is None:
        blockers.append("The exact expected response metric is unavailable.")
    elif metric.units != contract.units:
        blockers.append("The response metric units do not match the contract.")

    missing_countereffects = tuple(
        item.metric_id
        for item in contract.countereffect_contracts
        if item.required and item.metric_id not in metrics
    )
    if missing_countereffects:
        blockers.append("Required protected countereffect metrics are unavailable.")

    if unavailable:
        return ResponseExpectationEvaluation.build(
            expectation_contract_id=contract.expectation_contract_id,
            response_artifact_id=artifact.artifact_id,
            result="unavailable",
            blocker_reasons=tuple(dict.fromkeys(unavailable)),
        )
    if blockers:
        return ResponseExpectationEvaluation.build(
            expectation_contract_id=contract.expectation_contract_id,
            response_artifact_id=artifact.artifact_id,
            result="blocked",
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    assert metric is not None
    if abs(metric.value) < contract.minimum_absolute_signal:
        return ResponseExpectationEvaluation.build(
            expectation_contract_id=contract.expectation_contract_id,
            response_artifact_id=artifact.artifact_id,
            result="inconclusive",
            matched_metric_ids=(metric.metric_id,),
            blocker_reasons=(
                "Observed response does not clear the empirical noise requirement.",
            ),
        )

    countereffect_outside_range = any(
        item.required
        and item.accepted_min is not None
        and not (
            item.accepted_min
            <= metrics[item.metric_id].value
            <= item.accepted_max  # type: ignore[operator]
        )
        for item in contract.countereffect_contracts
    )
    if countereffect_outside_range:
        return ResponseExpectationEvaluation.build(
            expectation_contract_id=contract.expectation_contract_id,
            response_artifact_id=artifact.artifact_id,
            result="contradicted",
            matched_metric_ids=(metric.metric_id,),
            blocker_reasons=("A protected countereffect moved outside its accepted range.",),
        )

    matched = (
        (contract.expected_sign is not None and metric.value * contract.expected_sign > 0)
        or (
            contract.accepted_min is not None
            and contract.accepted_min <= metric.value <= contract.accepted_max  # type: ignore[operator]
        )
    )
    return ResponseExpectationEvaluation.build(
        expectation_contract_id=contract.expectation_contract_id,
        response_artifact_id=artifact.artifact_id,
        result="matched" if matched else "contradicted",
        matched_metric_ids=(metric.metric_id,),
        blocker_reasons=() if matched else ("Observed response contradicts the reviewed sign or range.",),
    )


def build_p19_response_evaluations_and_admissions(
    *,
    case_id: str,
    case_revision_sha256: str,
    p19_reasoning_snapshot_sha256: str,
    causes: Sequence[Any],
    response_artifacts: Sequence[EngineeringResponseArtifact],
    expectation_contracts: Sequence[ResponseExpectationContract],
    driver_demand_state: str,
    context_state: str,
    traffic_blocked: bool,
    car_identity: str | None = None,
    build_identity: str | None = None,
) -> tuple[tuple[ResponseExpectationEvaluation, ...], tuple[P19ResponseAdmission, ...]]:
    exact_context = (
        driver_demand_state == "matched"
        and context_state == "qualified"
        and not traffic_blocked
    )
    context_states = tuple(
        value
        for value in (
            "matched_driver_demand" if driver_demand_state == "matched" else None,
            "qualified_context" if context_state == "qualified" else None,
            "traffic_clear" if not traffic_blocked else None,
        )
        if value is not None
    )
    contracts_by_relation: dict[str, list[ResponseExpectationContract]] = {}
    for contract in expectation_contracts:
        contracts_by_relation.setdefault(contract.relation_id, []).append(contract)

    all_evaluations: list[ResponseExpectationEvaluation] = []
    admissions: list[P19ResponseAdmission] = []
    for artifact in response_artifacts:
        semantic = semantic_entry(artifact.relation)
        relevant_contracts = contracts_by_relation.get(artifact.relation, [])
        artifact_evaluations = tuple(
            evaluate_response_expectation(
                contract,
                artifact,
                context_states=context_states,
                car_identity=car_identity,
                build_identity=build_identity,
            )
            for contract in relevant_contracts
        )
        all_evaluations.extend(artifact_evaluations)
        evaluations_by_contract = {
            item.expectation_contract_id: item for item in artifact_evaluations
        }

        if semantic is None:
            admissions.append(
                P19ResponseAdmission.build(
                    case_id=case_id,
                    case_revision_sha256=case_revision_sha256,
                    response_artifact_id=artifact.artifact_id,
                    p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
                    assessments=(),
                    state="blocked",
                    blocker_reasons=("No reviewed P19 response relationship exists.",),
                )
            )
            continue

        assessments: list[P19ResponseCauseAssessment] = []
        for cause in causes:
            matched_mechanisms = tuple(
                value
                for value in getattr(cause, "mechanism_keys", ())
                if value in semantic.p20_mechanism_ids
            )
            if not matched_mechanisms:
                continue
            cause_contracts = tuple(
                contract
                for contract in relevant_contracts
                if set(contract.owning_mechanism_ids).intersection(
                    semantic.p35_mechanism_ids
                )
            )
            evaluations = tuple(
                evaluations_by_contract[item.expectation_contract_id]
                for item in cause_contracts
            )
            if not exact_context:
                result = "blocked"
                basis = "Current driver demand, context, or traffic blocks P19 response admission."
                blockers = (
                    "P19 response admission requires matched driver demand, qualified context, and clear traffic.",
                )
            elif not cause_contracts:
                result = "unresolved"
                basis = "The observation is mechanically related, but no exact response expectation contract exists."
                blockers = ()
            elif any(item.result == "matched" for item in evaluations) and any(
                item.result == "contradicted" for item in evaluations
            ):
                result = "unresolved"
                basis = "Reviewed response contracts disagree; no support or contradiction is admitted."
                blockers = ()
            elif any(item.result == "matched" for item in evaluations):
                result = "support"
                basis = "An exact reviewed response contract matched; P19 rank and terminal action remain unchanged."
                blockers = ()
            elif any(item.result == "contradicted" for item in evaluations):
                result = "contradiction"
                basis = "An exact reviewed response contract was contradicted; P19 rank and terminal action remain unchanged."
                blockers = ()
            elif any(item.result in {"blocked", "unavailable"} for item in evaluations):
                result = "blocked"
                basis = "The exact response contract could not be evaluated in this scope."
                blockers = tuple(
                    dict.fromkeys(
                        reason for item in evaluations for reason in item.blocker_reasons
                    )
                )
            else:
                result = "unresolved"
                basis = "The response did not clear the exact contract noise requirement."
                blockers = ()
            assessments.append(
                P19ResponseCauseAssessment(
                    cause_id=cause.cause_id,
                    matched_mechanism_ids=matched_mechanisms,
                    expectation_contract_ids=tuple(
                        item.expectation_contract_id for item in cause_contracts
                    ),
                    evaluation_ids=tuple(item.evaluation_id for item in evaluations),
                    result=result,
                    basis=basis,
                    blocker_reasons=blockers,
                )
            )

        if not assessments or all(item.result == "unresolved" for item in assessments):
            state = "unresolved"
            admission_blockers: tuple[str, ...] = ()
        elif all(item.result == "blocked" for item in assessments):
            state = "blocked"
            admission_blockers = tuple(
                dict.fromkeys(
                    reason for item in assessments for reason in item.blocker_reasons
                )
            )
        elif any(item.result in {"support", "contradiction"} for item in assessments):
            state = "admitted"
            admission_blockers = ()
        else:
            state = "unresolved"
            admission_blockers = ()
            assessments = [
                item.model_copy(
                    update={
                        "result": "unresolved",
                        "blocker_reasons": (),
                        "basis": "Mixed blocked and unresolved response state cannot be admitted.",
                    }
                )
                for item in assessments
            ]
        admissions.append(
            P19ResponseAdmission.build(
                case_id=case_id,
                case_revision_sha256=case_revision_sha256,
                response_artifact_id=artifact.artifact_id,
                p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
                assessments=tuple(assessments),
                state=state,
                blocker_reasons=admission_blockers,
            )
        )
    return tuple(all_evaluations), tuple(admissions)


__all__ = [
    "build_p19_response_evaluations_and_admissions",
    "evaluate_response_expectation",
]
