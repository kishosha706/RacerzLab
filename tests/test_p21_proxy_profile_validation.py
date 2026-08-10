from __future__ import annotations

from datetime import datetime, timedelta, timezone

from racelab_engine.evaluation.negative_controls import negative_control_library
from racelab_engine.evaluation.profile_validation import (
    build_profile_validation_record,
    resolve_profile_field,
    save_profile_validation_record,
)
from racelab_engine.evaluation.proxy_validation import (
    ProxyValidationCase,
    evaluate_proxy_cases,
    p20_proxy_contracts,
)


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)
PROFILE_HASH = "a" * 64


def test_every_p20_proxy_has_claim_boundaries_and_negative_controls():
    contracts = p20_proxy_contracts()
    assert len(contracts) == 8
    assert len({contract.proxy_key for contract in contracts}) == len(contracts)
    assert all(contract.allowed_claim for contract in contracts)
    assert all("setup_target" in contract.forbidden_claims for contract in contracts)
    assert all(contract.negative_control_ids for contract in contracts)
    controls = {control.control_id for control in negative_control_library()}
    assert {
        control_id
        for contract in contracts
        for control_id in contract.negative_control_ids
    }.issubset(controls)


def test_synthetic_proxy_success_is_not_real_world_validation():
    contract = p20_proxy_contracts()[0]
    result = evaluate_proxy_cases(
        contract,
        (
            ProxyValidationCase(
                case_id="slip-onset",
                independence_unit_id="synthetic-1",
                context_key="straight",
                expected_direction=1,
                observed_direction=1,
                synthetic=True,
                proxy_fired=True,
            ),
            ProxyValidationCase(
                case_id="no-slip",
                independence_unit_id="synthetic-2",
                context_key="straight",
                expected_direction=0,
                observed_direction=0,
                synthetic=True,
                negative_control=True,
                proxy_fired=False,
            ),
        ),
    )
    assert result.passed_mechanics
    assert not result.eligible_for_real_world_validation
    assert result.real_world_unit_count == 0


def test_proxy_negative_control_false_positive_blocks_mechanics():
    contract = p20_proxy_contracts()[0]
    result = evaluate_proxy_cases(
        contract,
        (
            ProxyValidationCase(
                case_id="slip-onset",
                independence_unit_id="event-1",
                context_key="corner",
                expected_direction=1,
                observed_direction=1,
                proxy_fired=True,
            ),
            ProxyValidationCase(
                case_id="no-slip",
                independence_unit_id="event-2",
                context_key="straight",
                expected_direction=0,
                observed_direction=0,
                negative_control=True,
                proxy_fired=True,
            ),
        ),
    )
    assert result.negative_control_false_positive_rate == 1.0
    assert not result.passed_mechanics
    assert not result.eligible_for_real_world_validation


def _profile_record(
    field: str,
    state: str,
    *,
    created_at: datetime = NOW,
    reason: str | None = None,
):
    usable = state in {"source_declared", "empirically_confirmed"}
    return build_profile_validation_record(
        {
            "created_at": created_at,
            "profile_id": "nextgen-v1",
            "profile_hash": PROFILE_HASH,
            "car_path": "stockcars chevycamarozl12022",
            "field": field,
            "state": state,
            "source_id": "official-source" if usable else None,
            "validation_method": "measured reference" if usable else None,
            "build_range": {
                "minimum_inclusive": "2026.01",
                "maximum_inclusive": "2026.12",
            },
            "last_validated_build": "2026.08" if usable else None,
            "evidence_artifact_ids": ("artifact-1",) if usable else (),
            "failure_or_revalidation_reason": reason,
        }
    )


def test_profile_fields_resolve_independently_and_require_empirical_confirmation(tmp_path):
    database = tmp_path / "profile.sqlite"
    wheelbase = _profile_record("wheelbase", "empirically_confirmed")
    rear_track = _profile_record("rear_track_width", "source_declared")
    save_profile_validation_record(wheelbase, db_path=database)
    save_profile_validation_record(rear_track, db_path=database)
    ready = resolve_profile_field(
        profile_id="nextgen-v1",
        profile_hash=PROFILE_HASH,
        car_path="stockcars chevycamarozl12022",
        build_id="2026.08",
        field="wheelbase",
        db_path=database,
    )
    blocked = resolve_profile_field(
        profile_id="nextgen-v1",
        profile_hash=PROFILE_HASH,
        car_path="stockcars chevycamarozl12022",
        build_id="2026.08",
        field="rear_track_width",
        db_path=database,
    )
    assert ready.status == "ready"
    assert blocked.status == "blocked"
    assert blocked.validation_state == "source_declared"


def test_profile_conflict_blocks_previously_confirmed_field(tmp_path):
    database = tmp_path / "profile.sqlite"
    save_profile_validation_record(
        _profile_record("wheelbase", "empirically_confirmed"),
        db_path=database,
    )
    conflict = _profile_record(
        "wheelbase",
        "conflicted",
        created_at=NOW + timedelta(days=1),
        reason="Source and measured reference disagree.",
    )
    save_profile_validation_record(conflict, db_path=database)
    resolution = resolve_profile_field(
        profile_id="nextgen-v1",
        profile_hash=PROFILE_HASH,
        car_path="stockcars chevycamarozl12022",
        build_id="2026.08",
        field="wheelbase",
        db_path=database,
    )
    assert resolution.status == "blocked"
    assert resolution.validation_state == "conflicted"
    assert "disagree" in resolution.blocker_reasons[0]


def test_profile_build_mismatch_blocks_dependent_metric(tmp_path):
    database = tmp_path / "profile.sqlite"
    save_profile_validation_record(
        _profile_record("rear_track_width", "empirically_confirmed"),
        db_path=database,
    )
    resolution = resolve_profile_field(
        profile_id="nextgen-v1",
        profile_hash=PROFILE_HASH,
        car_path="stockcars chevycamarozl12022",
        build_id="2027.01",
        field="rear_track_width",
        db_path=database,
    )
    assert resolution.status == "blocked"
    assert "iRacing build" in resolution.blocker_reasons[0]
