from __future__ import annotations

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.evidence_contracts import (
    AllowedOutput,
    AnalysisEvidenceContract,
    ConfidenceCaps,
    EvidenceConclusion,
    EvidenceEvaluationInput,
    EvidenceState,
    HardBlocker,
    OperatingCondition,
    RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT,
    RUN_OBSERVATION_CONTRACT,
    evaluate_evidence_contract,
)


def _contract() -> AnalysisEvidenceContract:
    return AnalysisEvidenceContract(
        key="test_analysis",
        purpose="Exercise the shared contract evaluator.",
        required_channels=frozenset({"speed", "time"}),
        preferred_channels=frozenset({"temperature"}),
        operating_conditions=(
            OperatingCondition(
                key="eligible_lap",
                description="lap is complete and eligible",
                measurement_needed="Record one complete flying lap.",
            ),
            OperatingCondition(
                key="weather_matched",
                description="weather context is matched",
                measurement_needed="Record matched weather telemetry.",
                required=False,
            ),
        ),
        hard_blockers=(
            HardBlocker(
                key="reset_fragment",
                description="reset fragment detected",
                measurement_needed="Repeat without an active reset.",
            ),
        ),
        allowed_outputs=(
            AllowedOutput(
                key="relative_delta",
                description="Relative time delta.",
                evidence_state=EvidenceState.CALCULATED,
                source_channels=frozenset({"speed", "time"}),
            ),
        ),
        forbidden_outputs=frozenset({"exact_force"}),
        minimum_repetitions=2,
        high_confidence_repetitions=4,
        confidence_caps=ConfidenceCaps(
            absolute_maximum=0.90,
            minimum_repetitions_only=0.70,
            missing_preferred_channels=0.60,
            unmet_preferred_condition=0.50,
        ),
    )


def _valid_input(**updates: object) -> EvidenceEvaluationInput:
    values: dict[str, object] = {
        "usable_channels": frozenset({"speed", "time", "temperature"}),
        "condition_results": {"eligible_lap": True, "weather_matched": True},
        "blocker_results": {"reset_fragment": False},
        "repetitions": 4,
        "requested_outputs": frozenset({"relative_delta"}),
    }
    values.update(updates)
    return EvidenceEvaluationInput(**values)


def test_evidence_state_vocabulary_is_exact_and_serializable() -> None:
    assert {state.value for state in EvidenceState} == {
        "measured",
        "calculated",
        "estimated_proxy",
        "observed_correlation",
        "controlled_test_effect",
        "unavailable",
        "blocked_by_context",
        "needs_confirmation",
    }
    conclusion = EvidenceConclusion(
        output_key="delta",
        summary="A calculated delta.",
        evidence_state=EvidenceState.CALCULATED,
        source_channels=frozenset({"speed"}),
    )
    assert conclusion.model_dump(mode="json")["evidence_state"] == "calculated"


def test_conclusions_require_structural_provenance_or_blockers() -> None:
    with pytest.raises(ValidationError, match="require source_channels"):
        EvidenceConclusion(
            output_key="delta",
            summary="Unsupported.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
        )
    with pytest.raises(ValidationError, match="require blocker_reasons"):
        EvidenceConclusion(
            output_key="delta",
            summary="Blocked.",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        )


def test_contract_rejects_ambiguous_channels_and_outputs() -> None:
    with pytest.raises(ValidationError, match="both required and preferred"):
        AnalysisEvidenceContract(
            key="bad",
            purpose="Invalid overlap.",
            required_channels=frozenset({"speed"}),
            preferred_channels=frozenset({"speed"}),
            allowed_outputs=_contract().allowed_outputs,
        )
    with pytest.raises(ValidationError, match="source channels must be declared"):
        AnalysisEvidenceContract(
            key="bad",
            purpose="Undeclared output source.",
            required_channels=frozenset({"speed"}),
            allowed_outputs=(
                AllowedOutput(
                    key="force",
                    description="Unsupported force.",
                    evidence_state=EvidenceState.CALCULATED,
                    source_channels=frozenset({"force"}),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="both allowed and forbidden"):
        AnalysisEvidenceContract(
            key="bad",
            purpose="Invalid output overlap.",
            required_channels=frozenset({"speed"}),
            allowed_outputs=_contract().allowed_outputs,
            forbidden_outputs=frozenset({"relative_delta"}),
        )


def test_contract_rejects_impossible_confidence_and_repetition_rules() -> None:
    with pytest.raises(ValidationError, match="cannot exceed absolute_maximum"):
        ConfidenceCaps(absolute_maximum=0.5, minimum_repetitions_only=0.6)
    with pytest.raises(ValidationError, match="must meet minimum_repetitions"):
        AnalysisEvidenceContract(
            key="bad",
            purpose="Invalid repetition range.",
            required_channels=frozenset({"speed"}),
            allowed_outputs=_contract().allowed_outputs,
            minimum_repetitions=3,
            high_confidence_repetitions=2,
        )


def test_happy_path_authorizes_only_requested_declared_output() -> None:
    result = evaluate_evidence_contract(_contract(), _valid_input())

    assert result.eligible is True
    assert result.confidence_cap == 0.90
    assert [output.key for output in result.authorized_outputs] == ["relative_delta"]
    assert result.blockers == ()
    assert result.needed_measurements == ()


def test_missing_required_channel_blocks_and_names_measurement() -> None:
    result = evaluate_evidence_contract(
        _contract(),
        _valid_input(usable_channels=frozenset({"speed", "temperature"})),
    )

    assert result.eligible is False
    assert ("missing_required_channel", "time") in {
        (item.code, item.key) for item in result.blockers
    }
    assert ("missing_output_source_channel", "relative_delta") in {
        (item.code, item.key) for item in result.blockers
    }
    assert result.needed_measurements[0].key == "time"
    assert "healthy, varying time" in result.needed_measurements[0].instruction
    assert result.authorized_outputs == ()


def test_output_is_denied_when_its_preferred_source_channel_is_unusable() -> None:
    contract = AnalysisEvidenceContract(
        key="preferred_source",
        purpose="Require actual output provenance at evaluation time.",
        required_channels=frozenset({"speed"}),
        preferred_channels=frozenset({"temperature"}),
        allowed_outputs=(
            AllowedOutput(
                key="temperature_adjusted_speed",
                description="A temperature-context speed result.",
                evidence_state=EvidenceState.CALCULATED,
                source_channels=frozenset({"speed", "temperature"}),
            ),
        ),
    )

    result = evaluate_evidence_contract(
        contract,
        EvidenceEvaluationInput(
            usable_channels=frozenset({"speed"}),
            repetitions=1,
            requested_outputs=frozenset({"temperature_adjusted_speed"}),
        ),
    )

    assert result.eligible is False
    assert result.denied_outputs == frozenset({"temperature_adjusted_speed"})
    assert any(blocker.code == "missing_output_source_channel" for blocker in result.blockers)


@pytest.mark.parametrize(
    ("condition_value", "expected_code"),
    [(False, "operating_condition_failed"), (None, "operating_condition_unknown")],
)
def test_required_operating_condition_fails_closed(
    condition_value: bool | None,
    expected_code: str,
) -> None:
    result = evaluate_evidence_contract(
        _contract(),
        _valid_input(
            condition_results={
                "eligible_lap": condition_value,
                "weather_matched": True,
            }
        ),
    )

    assert result.eligible is False
    assert result.blockers[0].code == expected_code
    assert result.blockers[0].measurement_needed == "Record one complete flying lap."


@pytest.mark.parametrize(
    ("blocker_value", "expected_code"),
    [(True, "hard_blocker_active"), (None, "hard_blocker_unknown")],
)
def test_hard_blocker_must_be_observed_clear(
    blocker_value: bool | None,
    expected_code: str,
) -> None:
    result = evaluate_evidence_contract(
        _contract(),
        _valid_input(blocker_results={"reset_fragment": blocker_value}),
    )

    assert result.eligible is False
    assert result.blockers[0].code == expected_code
    assert result.needed_measurements[0].key == "reset_fragment"


def test_repetition_minimum_blocks_and_requests_exact_shortfall() -> None:
    result = evaluate_evidence_contract(_contract(), _valid_input(repetitions=0))

    assert result.eligible is False
    blocker = next(item for item in result.blockers if item.code == "insufficient_repetitions")
    assert "2 are required" in blocker.message
    measurement = next(item for item in result.needed_measurements if item.key == "repetitions")
    assert "2 more eligible repetitions" in measurement.instruction


def test_confidence_uses_strictest_nonblocking_cap() -> None:
    result = evaluate_evidence_contract(
        _contract(),
        _valid_input(
            usable_channels=frozenset({"speed", "time"}),
            condition_results={"eligible_lap": True, "weather_matched": False},
            repetitions=2,
        ),
    )

    assert result.eligible is True
    assert result.confidence_cap == 0.50
    assert {limit.code for limit in result.confidence_limits} == {
        "missing_preferred_channels",
        "minimum_repetitions_only",
        "unmet_preferred_condition",
    }
    assert any(item.key == "weather_matched" for item in result.needed_measurements)


@pytest.mark.parametrize(
    "forbidden_output",
    [
        "measured_cda",
        "exact_drag_force",
        "exact_aerodynamic_drag_force",
        "exact_horsepower_loss",
    ],
)
def test_relative_resistance_contract_rejects_prohibited_claims(
    forbidden_output: str,
) -> None:
    contract = RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT
    evidence = EvidenceEvaluationInput(
        usable_channels=contract.required_channels | contract.preferred_channels,
        condition_results={condition.key: True for condition in contract.operating_conditions},
        blocker_results={blocker.key: False for blocker in contract.hard_blockers},
        repetitions=contract.high_confidence_repetitions,
        requested_outputs=frozenset({forbidden_output}),
    )
    result = evaluate_evidence_contract(contract, evidence)

    assert result.eligible is False
    assert result.denied_outputs == frozenset({forbidden_output})
    blocker = result.blockers[0]
    assert blocker.code == "forbidden_output"
    assert blocker.resolvable is False
    assert blocker.measurement_needed is None


def test_relative_resistance_contract_never_labels_outputs_as_measured() -> None:
    states = {
        output.key: output.evidence_state
        for output in RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT.allowed_outputs
    }
    assert states == {
        "relative_speed_loss_delta": EvidenceState.CALCULATED,
        "relative_resistance_direction": EvidenceState.OBSERVED_CORRELATION,
        "resistance_cause_hypothesis": EvidenceState.ESTIMATED_PROXY,
        "measured_grade_context": EvidenceState.CALCULATED,
    }
    assert EvidenceState.MEASURED not in states.values()


def test_undeclared_output_is_denied_instead_of_silently_allowed() -> None:
    result = evaluate_evidence_contract(
        _contract(),
        _valid_input(requested_outputs=frozenset({"mystery_output"})),
    )

    assert result.eligible is False
    assert result.denied_outputs == frozenset({"mystery_output"})
    assert result.blockers[0].code == "undeclared_output"


def test_models_reject_unknown_fields_and_are_immutable() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceEvaluationInput(usable_channels=frozenset(), surprise=True)
    evidence = _valid_input()
    with pytest.raises(ValidationError, match="frozen"):
        evidence.repetitions = 99


def _run_observation_input(**updates: object) -> EvidenceEvaluationInput:
    contract = RUN_OBSERVATION_CONTRACT
    values: dict[str, object] = {
        "usable_channels": contract.required_channels | contract.preferred_channels,
        "condition_results": {item.key: True for item in contract.operating_conditions},
        "blocker_results": {item.key: False for item in contract.hard_blockers},
        "repetitions": 3,
        "requested_outputs": frozenset({"located_engineering_observation"}),
    }
    values.update(updates)
    return EvidenceEvaluationInput(**values)


def test_run_observation_contract_allows_only_a_non_authorizing_observation() -> None:
    result = evaluate_evidence_contract(
        RUN_OBSERVATION_CONTRACT,
        _run_observation_input(),
    )

    assert result.eligible is True
    assert [item.key for item in result.authorized_outputs] == ["located_engineering_observation"]
    assert result.authorized_outputs[0].evidence_state is EvidenceState.OBSERVED_CORRELATION


@pytest.mark.parametrize(
    "output_key",
    ["exact_drag_force", "measured_cda", "strong_tire_degradation_claim", "strong_cooling_claim"],
)
def test_run_observation_contract_forbids_unsupported_outputs(output_key: str) -> None:
    result = evaluate_evidence_contract(
        RUN_OBSERVATION_CONTRACT,
        _run_observation_input(requested_outputs=frozenset({output_key})),
    )

    assert result.eligible is False
    assert result.denied_outputs == frozenset({output_key})


def test_run_observation_contract_cannot_authorize_a_setup_test() -> None:
    result = evaluate_evidence_contract(
        RUN_OBSERVATION_CONTRACT,
        _run_observation_input(requested_outputs=frozenset({"controlled_setup_test"})),
    )

    assert result.eligible is False
    assert result.denied_outputs == frozenset({"controlled_setup_test"})


def test_short_run_sensitive_claim_blocks_run_observation() -> None:
    blockers = {item.key: False for item in RUN_OBSERVATION_CONTRACT.hard_blockers}
    blockers["short_run_sensitive_claim"] = True
    result = evaluate_evidence_contract(
        RUN_OBSERVATION_CONTRACT,
        _run_observation_input(blocker_results=blockers),
    )

    assert result.eligible is False
    assert any(item.key == "short_run_sensitive_claim" for item in result.blockers)
