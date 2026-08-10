from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from racelab_engine.evaluation.acquisition_operations import (
    admit_qualification_certificate,
    build_pre_run_checklist,
    build_qualification_certificate,
    build_steering_signal_truth_audit,
    freeze_negative_control_expectation,
    get_qualification_certificate,
    list_qualification_certificates,
    negative_control_recipe_catalog,
    negative_control_recipes,
    p23_acquisition_progress,
    p23_collection_templates,
    qualify_p23_operations_for_run,
    save_negative_control_expectation,
)
from racelab_engine.evaluation.campaigns import campaign_progress, initial_campaigns
from racelab_engine.evaluation.first_activation import first_activation_protocol
from racelab_engine.evaluation.learning_operations import (
    assess_active_operations_for_run,
    start_campaign_operation,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.storage.repository import RaceLabRepository

NOW = datetime(2026, 8, 11, tzinfo=UTC)
SOURCE_A = "a" * 64
SOURCE_B = "b" * 64


def _overview(
    run_id: str,
    *,
    source: str,
    steering_ratio: str = "14:1",
) -> RunOverview:
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            file_hash=source,
            car_path="stockcars chevycamarozl12022",
            track_id_or_path="atlanta-oval",
        ),
        laps=[
            LapSummary(
                lap_id=f"{run_id}:lap:{lap}",
                run_id=run_id,
                lap_number=lap,
                is_complete=True,
                is_useful=True,
                lap_time=30.0,
                pct_min=0.0,
                pct_max=100.0,
                pct_span=100.0,
                sample_count=100,
            )
            for lap in range(1, 11)
        ],
        setup_snapshot=SetupSnapshot(
            setup_id=f"setup:{run_id}",
            run_id=run_id,
            setup_name="same setup",
            setup_json={"cross_weight": 50.0},
            steering_ratio=steering_ratio,
        ),
    )


def _channel(
    raw_name: str,
    canonical_name: str,
    unit: str,
    *,
    subtick: bool = False,
    malformed: int = 0,
) -> dict[str, object]:
    return {
        "raw_name": raw_name,
        "canonical_name": canonical_name,
        "unit": unit,
        "base_sample_rate_hz": 60.0,
        "effective_sample_rate_hz": 360.0 if subtick else 60.0,
        "samples_per_record": 6 if subtick else 1,
        "count_as_time": subtick,
        "record_count": 10,
        "valid_record_count": 10,
        "malformed_array_record_count": malformed,
        "non_finite_sample_count": 0,
        "variation": "varying" if raw_name in {
            "SteeringWheelTorque_ST",
            "SteeringWheelTorque",
            "SteeringWheelAngle",
        } else "constant",
    }


def _manifest(source: str, *, malformed_subtick: int = 0) -> dict[str, object]:
    channels = [
        _channel("SteeringWheelTorque_ST", "steering_wheel_torque_subtick_nm", "N*m", subtick=True, malformed=malformed_subtick),
        _channel("SteeringWheelTorque", "steering_wheel_torque_nm", "N*m"),
        _channel("SteeringWheelAngle", "steering_deg", "rad"),
        _channel("SteeringWheelAngleMax", "steering_wheel_angle_max", "rad"),
        _channel("SteeringWheelMaxForceNm", "steering_ffb_max_force_nm", "N*m"),
        _channel("SteeringWheelUseLinear", "steering_ffb_use_linear", "bool"),
        _channel("SteeringWheelPctIntensity", "steering_ffb_intensity_01", "%"),
        _channel("SteeringWheelPctSmoothing", "steering_ffb_smoothing_01", "%"),
        _channel("SteeringWheelPctDamper", "steering_ffb_damper_01", "%"),
        _channel("SteeringWheelLimiter", "steering_ffb_limiter_01", "%"),
    ]
    return {
        "source_file_sha256": source,
        "compatibility_identity": {
            "car_path": "stockcars chevycamarozl12022",
            "track_id": "atlanta-oval",
            "iracing_build_version": "2026.08.1",
        },
        "sample_continuity": {"status": "healthy", "discontinuity_count": 0},
        "channels": channels,
    }


def _rows(
    *,
    max_force: float = 40.0,
    use_linear: bool = True,
    smoothing: float = 0.1,
    damper: float = 0.05,
) -> list[dict[str, object]]:
    rows = []
    for lap in range(1, 11):
        torque = 1.0 + lap / 10.0
        rows.append(
            {
                "session_time": float(lap),
                "lap": lap,
                "lap_dist_pct_100": 50.0,
                "SteeringWheelTorque_ST": [torque] * 6,
                "SteeringWheelTorque": torque,
                "SteeringWheelAngle": 0.02 * lap,
                "SteeringWheelAngleMax": 7.85,
                "SteeringWheelFFBEnabled": True,
                "SteeringWheelMaxForceNm": max_force,
                "SteeringWheelUseLinear": use_linear,
                "SteeringWheelPctIntensity": 0.8,
                "SteeringWheelPctSmoothing": smoothing,
                "SteeringWheelPctDamper": damper,
                "SteeringWheelLimiter": 1.0,
                "applied_brake_bias": 44.0,
                "dcBrakeBias": 44.0,
            }
        )
    return rows


def _semantic(value: float):
    return SimpleNamespace(
        start_value=value,
        end_value=value,
        minimum_value=value,
        maximum_value=value,
    )


def _context_report():
    return SimpleNamespace(
        status="ready",
        contexts=tuple(
            SimpleNamespace(
                lap_number=lap,
                blocker_reasons=(),
                nearby_traffic_exposure_fraction=0.0,
                fuel_level=_semantic(20.0),
                track_temperature=_semantic(40.0),
                air_temperature=_semantic(25.0),
            )
            for lap in range(1, 11)
        ),
    )


def _patch_sources(monkeypatch, manifests, rows_by_run):
    def manifest(run_id):
        return manifests[run_id]

    def rows(run_id, columns=None):
        return rows_by_run[run_id]

    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.read_telemetry_manifest",
        manifest,
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.read_telemetry_rows",
        rows,
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.load_lap_engineering_context_report",
        lambda run_id, db_path=None: _context_report(),
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.acquisition_operations.read_telemetry_manifest",
        manifest,
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.acquisition_operations.read_telemetry_rows",
        rows,
    )


def _start_and_assess(database, monkeypatch, *, run_id="run-a", source=SOURCE_A):
    RaceLabRepository(database).save_import(_overview(run_id, source=source))
    operation = start_campaign_operation(
        "control_workload",
        run_id,
        db_path=database,
        created_at=NOW,
    )
    assessment = assess_active_operations_for_run(run_id, db_path=database)[0]
    return operation, assessment


def test_steering_signal_truth_audit_proves_clock_units_relation_and_debt():
    audit = build_steering_signal_truth_audit(
        run_id="run-a",
        manifest=_manifest(SOURCE_A),
        rows=_rows(),
        steering_conversion_model="14:1",
        created_at=NOW,
    )
    assert audit.state == "ready"
    assert audit.effective_sub_tick_rate_hz == 360.0
    assert audit.scalar_subtick_relation == "mean_consistent"
    assert audit.ffb_fingerprint.state == "ready"
    corrupt = build_steering_signal_truth_audit(
        run_id="run-a",
        manifest=_manifest(SOURCE_A, malformed_subtick=1),
        rows=_rows(),
        steering_conversion_model="14:1",
        created_at=NOW,
    )
    assert corrupt.state == "scientific_debt"
    assert "Malformed array" in " ".join(corrupt.blocker_reasons)
    missing_conversion = build_steering_signal_truth_audit(
        run_id="run-a",
        manifest=_manifest(SOURCE_A),
        rows=_rows(),
        steering_conversion_model=None,
        created_at=NOW,
    )
    assert missing_conversion.state == "scientific_debt"
    assert "ratio/pinion" in " ".join(missing_conversion.blocker_reasons)


def test_clean_import_produces_certificate_flight_recorder_and_certificate_owned_dataset(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "qualified.sqlite"
    _patch_sources(
        monkeypatch,
        {"run-a": _manifest(SOURCE_A)},
        {"run-a": _rows()},
    )
    _operation, assessment = _start_and_assess(database, monkeypatch)
    assert assessment.state == "pending_protocol"
    certificates = qualify_p23_operations_for_run(
        "run-a",
        assessments=(assessment,),
        db_path=database,
        created_at=NOW,
    )
    certificate = certificates[0]
    assert certificate.qualification_state == "qualified"
    assert certificate.eligible_laps == tuple(range(1, 11))
    assert all(item.state == "qualified" for item in certificate.flight_recorder)
    assert certificate.p19_authority_unchanged is True
    assert certificate.p20_authority_unchanged is True
    assert certificate.p23_authority == "shadow_only"
    progress = p23_acquisition_progress(db_path=database)
    assert progress.historical_sessions == 1
    assert progress.profile_status == "complete"
    campaign = next(
        item for item in initial_campaigns() if item.campaign_kind == "control_workload"
    )
    assert campaign_progress(campaign, db_path=database).independent_units == 1
    again = qualify_p23_operations_for_run(
        "run-a",
        assessments=(assessment,),
        db_path=database,
        created_at=NOW,
    )
    assert again == certificates
    forged = certificate.model_copy(update={"eligible_laps": (1,)})
    with pytest.raises(ValueError, match="stored immutable certificate"):
        admit_qualification_certificate(forged, db_path=database)


def test_renamed_reimport_and_adjacent_laps_cannot_inflate_source_session_count(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "duplicates.sqlite"
    repo = RaceLabRepository(database)
    repo.save_import(_overview("run-a", source=SOURCE_A))
    repo.save_import(_overview("renamed-copy", source=SOURCE_A))
    manifests = {
        "run-a": _manifest(SOURCE_A),
        "renamed-copy": _manifest(SOURCE_A),
    }
    rows_by_run = {"run-a": _rows(), "renamed-copy": _rows()}
    _patch_sources(monkeypatch, manifests, rows_by_run)
    operation = start_campaign_operation(
        "control_workload", "run-a", db_path=database, created_at=NOW
    )
    first = assess_active_operations_for_run("run-a", db_path=database)[0]
    qualify_p23_operations_for_run(
        "run-a", assessments=(first,), db_path=database, created_at=NOW
    )
    second = assess_active_operations_for_run("renamed-copy", db_path=database)[0]
    copied = qualify_p23_operations_for_run(
        "renamed-copy", assessments=(second,), db_path=database, created_at=NOW
    )[0]
    assert copied.duplicate_source is True
    assert copied.qualification_state != "qualified"
    assert copied.inventory_retained is True
    stored = list_qualification_certificates(db_path=database)
    assert len(stored) == 2
    assert list_qualification_certificates(db_path=database, limit=1) == stored[-1:]
    assert get_qualification_certificate(
        copied.certificate_id, db_path=database
    ) == copied
    assert get_qualification_certificate("p24c-missing", db_path=database) is None
    with pytest.raises(ValueError, match="at least one"):
        list_qualification_certificates(db_path=database, limit=0)
    progress = p23_acquisition_progress(db_path=database)
    assert progress.historical_sessions == 1
    assert progress.total_attempts == 2
    assert progress.qualified_attempts == 1
    assert progress.rejected_attempts == 1
    assert progress.next_best_collection_kind == "historical_exact_ffb"
    assert progress.latest_flight_recorder_total == len(stored[-1].flight_recorder)
    assert progress.latest_flight_recorder_truncated is False
    campaign = next(
        item for item in initial_campaigns() if item.campaign_id == operation.campaign_id
    )
    assert campaign_progress(campaign, db_path=database).independent_units == 1


@pytest.mark.parametrize(
    ("changed_rows", "steering_ratio", "expected"),
    (
        (_rows(max_force=45.0), "14:1", "max_force_nm"),
        (_rows(use_linear=False), "14:1", "use_linear"),
        (_rows(smoothing=0.2), "14:1", "smoothing_01"),
        (_rows(damper=0.2), "14:1", "damper_01"),
        (_rows(), "12:1", "steering_conversion_model"),
    ),
)
def test_material_ffb_and_steering_conversion_mismatches_block_admission(
    tmp_path,
    monkeypatch,
    changed_rows,
    steering_ratio,
    expected,
):
    database = tmp_path / f"mismatch-{expected}.sqlite"
    repo = RaceLabRepository(database)
    repo.save_import(_overview("reference", source=SOURCE_A))
    repo.save_import(
        _overview("test", source=SOURCE_B, steering_ratio=steering_ratio)
    )
    _patch_sources(
        monkeypatch,
        {"reference": _manifest(SOURCE_A), "test": _manifest(SOURCE_B)},
        {"reference": _rows(), "test": changed_rows},
    )
    start_campaign_operation(
        "control_workload", "reference", db_path=database, created_at=NOW
    )
    assessment = assess_active_operations_for_run("test", db_path=database)[0]
    assert expected in " ".join(assessment.rejection_reasons)
    certificate = qualify_p23_operations_for_run(
        "test", assessments=(assessment,), db_path=database, created_at=NOW
    )[0]
    assert certificate.qualification_state != "qualified"
    assert not certificate.dataset_admissions
    assert certificate.inventory_retained is True


def test_negative_control_expectation_must_be_frozen_before_observation(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "negative.sqlite"
    repo = RaceLabRepository(database)
    repo.save_import(_overview("reference", source=SOURCE_A))
    repo.save_import(_overview("test", source=SOURCE_B))
    _patch_sources(
        monkeypatch,
        {"reference": _manifest(SOURCE_A), "test": _manifest(SOURCE_B)},
        {"reference": _rows(), "test": _rows(max_force=45.0)},
    )
    operation = start_campaign_operation(
        "control_workload", "reference", db_path=database, created_at=NOW
    )
    expectation = freeze_negative_control_expectation(
        recipe_id="max_force_mismatch",
        operation=operation,
        created_at=NOW,
    )
    assert expectation.observed_run_id is None
    assert expectation.observed_result is None
    smoothing = freeze_negative_control_expectation(
        recipe_id="smoothing_mismatch",
        operation=operation,
        created_at=NOW,
    )
    assert expectation.protocol_control_id == "ffb_config_changed"
    assert smoothing.protocol_control_id == "ffb_config_changed"
    covered_protocol_controls = {
        freeze_negative_control_expectation(
            recipe_id=recipe_id,
            operation=operation,
            created_at=NOW,
        ).protocol_control_id
        for recipe_id in negative_control_recipes()
    }
    assert covered_protocol_controls == set(first_activation_protocol().negative_control_ids)
    save_negative_control_expectation(expectation, db_path=database)
    assessment = assess_active_operations_for_run("test", db_path=database)[0]
    certificate = qualify_p23_operations_for_run(
        "test", assessments=(assessment,), db_path=database, created_at=NOW
    )[0]
    assert certificate.collection_kind == "negative_control"
    assert certificate.qualification_state == "qualified"
    assert certificate.negative_control_expectation_id == expectation.expectation_id
    progress = p23_acquisition_progress(db_path=database)
    assert progress.negative_controls == 1
    assert progress.historical_sessions == 0


def test_applied_and_requested_control_boundaries_remain_distinct_and_block(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "control-boundaries.sqlite"
    changed = _rows()
    changed[5]["applied_brake_bias"] = 45.0
    changed[5]["dcBrakeBias"] = 45.0
    changed[5]["requested_fuel_add_kg"] = 5.0
    changed[6]["requested_fuel_add_kg"] = 6.0
    _patch_sources(
        monkeypatch,
        {"run-a": _manifest(SOURCE_A)},
        {"run-a": changed},
    )
    _operation, assessment = _start_and_assess(database, monkeypatch)
    certificate = qualify_p23_operations_for_run(
        "run-a", assessments=(assessment,), db_path=database, created_at=NOW
    )[0]
    assert certificate.qualification_state != "qualified"
    assert certificate.control_state_history
    applied = {
        item.mutation_id
        for item in certificate.control_state_history
        if item.mutation_kind == "applied_state"
    }
    requested = {
        item.mutation_id
        for item in certificate.control_state_history
        if item.mutation_kind == "requested_state"
    }
    assert applied and requested and applied.isdisjoint(requested)
    boundaries = [
        item for item in certificate.flight_recorder if item.state == "context_boundary"
    ]
    assert boundaries
    assert not certificate.dataset_admissions


def test_collection_templates_are_executable_debt_not_new_authority(tmp_path):
    templates = p23_collection_templates(db_path=tmp_path / "templates.sqlite")
    assert {item.collection_kind for item in templates} == {
        "historical_exact_ffb",
        "same_setup_null",
        "negative_control",
        "profile_validation",
        "prospective",
    }
    prospective = next(item for item in templates if item.collection_kind == "prospective")
    assert prospective.state == "locked"
    assert prospective.authority == "collection_template_only"
    assert all(item.protocol_hash == first_activation_protocol().protocol_hash for item in templates)


def test_negative_control_catalog_is_discoverable_without_freezing_an_outcome():
    catalog = negative_control_recipe_catalog()
    assert {item.recipe_id for item in catalog} == set(negative_control_recipes())
    assert {item.protocol_control_id for item in catalog} == set(
        first_activation_protocol().negative_control_ids
    )
    assert all(item.authority == "expectation_template_only" for item in catalog)
    assert all(item.label and item.expected_blocker_keys for item in catalog)


def test_prospective_collection_is_hard_locked_and_protocol_is_unchanged(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "prospective.sqlite"
    _patch_sources(
        monkeypatch,
        {"run-a": _manifest(SOURCE_A)},
        {"run-a": _rows()},
    )
    operation, assessment = _start_and_assess(database, monkeypatch)
    truth = build_steering_signal_truth_audit(
        run_id="run-a",
        manifest=_manifest(SOURCE_A),
        rows=_rows(),
        steering_conversion_model="14:1",
        created_at=NOW,
    )
    certificate = build_qualification_certificate(
        collection_kind="prospective",
        operation=operation,
        assessment=assessment,
        overview=RaceLabRepository(database).get_overview("run-a"),
        manifest=_manifest(SOURCE_A),
        truth_audit=truth,
        created_at=NOW,
    )
    assert certificate.qualification_state != "qualified"
    assert "locked until historical" in " ".join(certificate.blocker_reasons)
    checklist = build_pre_run_checklist(
        "run-a", collection_kind="prospective", db_path=database
    )
    assert checklist.ready_to_record is False
    assert checklist.campaign_progress.prospective_status == "locked_until_historical_gate"
    protocol = first_activation_protocol()
    assert protocol.protocol_id == "p23p-7039505728f07034d6f5"
    assert protocol.protocol_hash == "7039505728f07034d6f58e78c65759e30f3ac7c7b87beb9186b64c0e699bb4dc"
    assert protocol.current_authority == "shadow_only"
