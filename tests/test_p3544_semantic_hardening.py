from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from racelab_engine.models.engineering_case import (
    ResponseCountereffectContract,
    ResponseExpectationContract,
)
from racelab_engine.services.controlled_workflow_service import (
    _expected_response_relations,
)
from racelab_engine.services.crew_chief_service import (
    _active_workflow_identity,
    _assert_crew_mutation_identity,
    _inspection_evidence_qualifications,
    _usable_response_relations,
)
from racelab_engine.services.engineering_case_service import (
    build_evidence_deficits,
    build_setup_effect_readiness,
)
from racelab_engine.services.p19_response_admission_service import (
    evaluate_response_expectation,
)
from test_p3543_engineering_case import (
    _expectation,
    _hypothesis,
    _response_artifacts,
)


def _rebuild(contract: ResponseExpectationContract, **updates):
    payload = contract.model_dump(
        mode="python",
        exclude={"expectation_contract_id", "expectation_sha256"},
    )
    payload.update(updates)
    return ResponseExpectationContract.build(**payload)


def _evaluate(contract: ResponseExpectationContract):
    return evaluate_response_expectation(
        contract,
        _response_artifacts()[0],
        context_states=(
            "matched_driver_demand",
            "qualified_context",
            "traffic_clear",
        ),
    )


def test_exact_response_contract_rejects_wrong_sign_range_noise_and_scope() -> None:
    artifact = _response_artifacts()[0]
    contract = _expectation(artifact)
    assert _evaluate(contract).result == "matched"

    wrong_sign = _rebuild(contract, expected_sign=-contract.expected_sign)
    assert _evaluate(wrong_sign).result == "contradicted"

    metric = artifact.operational_evidence.metrics[0]
    wrong_range = _rebuild(
        contract,
        expected_sign=None,
        accepted_min=metric.value + 1.0,
        accepted_max=metric.value + 2.0,
    )
    assert _evaluate(wrong_range).result == "contradicted"

    below_noise = _rebuild(
        contract,
        minimum_absolute_signal=abs(metric.value) + 1.0,
    )
    assert _evaluate(below_noise).result == "inconclusive"

    wrong_phase = _rebuild(contract, phase="entry")
    assert _evaluate(wrong_phase).result == "unavailable"

    if artifact.speed_min_mps is not None and artifact.speed_max_mps is not None:
        wrong_speed = _rebuild(
            contract,
            speed_min_mps=artifact.speed_min_mps + 1.0,
            speed_max_mps=artifact.speed_max_mps + 2.0,
        )
        assert _evaluate(wrong_speed).result == "unavailable"

    insufficient_repetition = _rebuild(
        contract,
        minimum_independent_repetitions=(
            artifact.operational_evidence.repetition_count + 1
        ),
    )
    assert _evaluate(insufficient_repetition).result == "blocked"

    missing_countereffect = _rebuild(
        contract,
        countereffect_contracts=(
            ResponseCountereffectContract(metric_id="metric:missing"),
        ),
    )
    assert _evaluate(missing_countereffect).result == "blocked"


def test_blocked_artifact_cannot_satisfy_crew_inspection() -> None:
    artifact = _response_artifacts()[0]
    blocked_case = SimpleNamespace(
        response_artifacts=(artifact,),
        p19_response_admissions=(
            SimpleNamespace(
                response_artifact_id=artifact.artifact_id,
                state="blocked",
            ),
        ),
        response_expectation_evaluations=(
            SimpleNamespace(
                response_artifact_id=artifact.artifact_id,
                result="matched",
            ),
        ),
    )
    assert _usable_response_relations(blocked_case) == frozenset()


def test_one_admitted_relation_does_not_admit_blocked_sibling_artifact() -> None:
    artifact = _response_artifacts()[0]
    blocked_id = artifact.artifact_id[:-1] + "0"
    if blocked_id == artifact.artifact_id:
        blocked_id = artifact.artifact_id[:-1] + "1"
    case = SimpleNamespace(
        case_sha256="a" * 64,
        response_artifacts=(
            SimpleNamespace(
                artifact_id=artifact.artifact_id, relation=artifact.relation
            ),
            SimpleNamespace(artifact_id=blocked_id, relation=artifact.relation),
        ),
        p19_response_admissions=(
            SimpleNamespace(response_artifact_id=artifact.artifact_id, state="admitted"),
            SimpleNamespace(
                response_artifact_id=blocked_id,
                state="blocked",
                blocker_reasons=("Context is blocked.",),
            ),
        ),
        response_expectation_evaluations=(
            SimpleNamespace(
                response_artifact_id=artifact.artifact_id,
                result="matched",
                blocker_reasons=(),
            ),
            SimpleNamespace(
                response_artifact_id=blocked_id,
                result="matched",
                blocker_reasons=(),
            ),
        ),
    )
    qualifications = _inspection_evidence_qualifications(case)
    relevant = tuple(
        item for item in qualifications if artifact.artifact_id in item.accepted_artifact_ids
    )
    assert relevant
    assert all(blocked_id not in item.accepted_artifact_ids for item in relevant)
    assert all(blocked_id in item.rejected_artifact_ids for item in relevant)


def test_active_workflow_revision_is_a_stable_content_hash() -> None:
    updated_at = datetime(2026, 8, 20, 12, tzinfo=UTC)
    move = SimpleNamespace(
        workflow_id="aba-current",
        workflow_updated_at=updated_at,
    )
    bundle = SimpleNamespace(
        report=SimpleNamespace(
            smart_guidance=SimpleNamespace(next_trustworthy_move=move)
        )
    )
    payload = {
        "workflow_id": "aba-current",
        "updated_at": updated_at.isoformat(),
        "status": "planned",
        "packet": {"decision": "test"},
    }
    workflow = SimpleNamespace(
        workflow_id="aba-current",
        updated_at=updated_at,
        model_dump=lambda *, mode: payload,
    )
    workflow_id, revision = _active_workflow_identity(bundle, workflow)
    assert workflow_id == "aba-current"
    assert revision is not None and len(revision) == 64
    assert revision == _active_workflow_identity(bundle, workflow)[1]

    changed = SimpleNamespace(
        workflow_id="aba-current",
        updated_at=updated_at,
        model_dump=lambda *, mode: {**payload, "status": "a_recorded"},
    )
    assert _active_workflow_identity(bundle, changed)[1] != revision

    stale = SimpleNamespace(
        workflow_id="aba-current",
        updated_at=datetime(2026, 8, 20, 13, tzinfo=UTC),
        model_dump=lambda *, mode: payload,
    )
    with pytest.raises(ValueError, match="catalog and public guidance disagree"):
        _active_workflow_identity(bundle, stale)


def test_crew_mutation_rejects_a_stale_case_even_when_workspace_is_unchanged() -> None:
    current = SimpleNamespace(
        identity=SimpleNamespace(workspace_revision="a" * 64),
        engineering_case=SimpleNamespace(case_sha256="b" * 64),
    )
    with pytest.raises(ValueError, match="Engineering Case revision"):
        _assert_crew_mutation_identity(
            current,
            expected_workspace_revision="a" * 64,
            expected_case_sha256="c" * 64,
        )


def test_typed_deficit_routing_is_independent_of_missing_evidence_prose() -> None:
    artifacts = _response_artifacts()
    first = build_setup_effect_readiness(
        (_hypothesis(missing_evidence=("First display wording.",)),), artifacts
    )
    second = build_setup_effect_readiness(
        (_hypothesis(missing_evidence=("Completely different wording.",)),), artifacts
    )
    first_deficits = build_evidence_deficits(first, artifacts)
    second_deficits = build_evidence_deficits(second, artifacts)
    assert tuple(item.code for item in first_deficits) == tuple(
        item.code for item in second_deficits
    )
    assert tuple(item.required_channel_ids for item in first_deficits) == tuple(
        item.required_channel_ids for item in second_deficits
    )


def test_zero_or_ambiguous_semantic_match_has_no_generic_phase_fallback() -> None:
    assert _expected_response_relations("unknown-effect", "center") == ()
