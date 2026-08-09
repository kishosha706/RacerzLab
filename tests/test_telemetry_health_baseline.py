from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.io.telemetry_manifest import compatibility_fingerprint
from racelab_engine.analysis.test_director import (
    ControlledTestCard,
    TestStage as ControlledTestStage,
)
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.telemetry_health import TelemetryHealthBaselineReport
from racelab_engine.services.import_service import (
    csv_path,
    telemetry_manifest_path,
)
from racelab_engine.services.session_service import add_run_to_session, create_session
from racelab_engine.services.telemetry_health_service import (
    build_telemetry_health_baseline,
)
from racelab_engine.services.run_intelligence_service import (
    _controlled_decision,
    _setup_values,
    _telemetry_health_card_blockers,
    build_run_intelligence,
)
from racelab_engine.storage.repository import RaceLabRepository
from api.intelligence_adapter import to_public_intelligence_report


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)
RAW_CHANNELS = {
    "session_time": "SessionTime",
    "session_tick": "SessionTick",
    "lap_dist_pct": "LapDistPct",
    "speed_mps": "Speed",
    "throttle_01": "Throttle",
    "brake_01": "Brake",
    "steering_rad": "SteeringWheelAngle",
    "rpm": "RPM",
    "gear": "Gear",
}
DEFAULT_RANGES = {
    "session_time": (0.0, 100.0),
    "session_tick": (0.0, 6000.0),
    "lap_dist_pct": (0.0, 1.0),
    "speed_mps": (20.0, 80.0),
    "throttle_01": (0.0, 1.0),
    "brake_01": (0.0, 0.8),
    "steering_rad": (-0.6, 0.6),
    "rpm": (3500.0, 9000.0),
    "gear": (1.0, 5.0),
}
BASE_IDENTITY = {
    "driver_user_id": 7,
    "car_id": 1,
    "car_path": "stockcars/gen7",
    "car_version": "2026.08",
    "track_id": 10,
    "track_configuration_name": "oval",
    "track_version": "2026.08",
    "iracing_build_version": "2026.08.07.01",
    "session_type": "Practice",
    "source": "ibt_session_yaml",
    "missing_required_fields": [],
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _channel(
    canonical: str,
    *,
    variation: str = "varying",
    valid_records: int = 100,
    observed_range: tuple[float, float] | None = None,
    health_status: str = "healthy",
    effective_rate_hz: float = 60.0,
    clipping_status: str = "none_detected",
    saturation_status: str = "none_detected",
    numeric_limit_hit_count: int = 0,
) -> dict[str, object]:
    raw = RAW_CHANNELS[canonical]
    minimum, maximum = observed_range or DEFAULT_RANGES[canonical]
    distinct = 10 if variation == "varying" else 1 if variation == "constant" else 0
    return {
        "name": raw,
        "raw_name": raw,
        "canonical_name": canonical,
        "archive_status": "cached",
        "record_count": 100,
        "valid_record_count": valid_records,
        "missing_fraction": round(1.0 - valid_records / 100.0, 8),
        "distinct_value_count": distinct,
        "variation": variation,
        "observed_min": minimum,
        "observed_max": maximum,
        "health_status": health_status,
        "effective_sample_rate_hz": effective_rate_hz,
        "clipping_status": clipping_status,
        "saturation_status": saturation_status,
        "lower_bound_occupancy_fraction": 0.0,
        "upper_bound_occupancy_fraction": 0.0,
        "numeric_limit_hit_count": numeric_limit_hit_count,
    }


def _save_run(
    repository: RaceLabRepository,
    data_dir: Path,
    run_id: str,
    *,
    channels: list[dict[str, object]] | None = None,
    identity: dict[str, object] | None = None,
    lossless: bool = True,
) -> dict[str, object]:
    source_hash = _hash(f"source:{run_id}")
    repository.save_import(
        RunOverview(
            run_id=run_id,
            session=SessionSummary(
                run_id=run_id,
                source_file=f"{run_id}.ibt",
                file_hash=source_hash,
                import_time=NOW,
                car_name="Test Car",
                car_path="stockcars/gen7",
                track_name="Test Track",
                track_id_or_path="10",
                session_type="Practice",
                setup_passed_tech=True,
            ),
        )
    )
    cache = csv_path(data_dir, run_id)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("SessionTime,Speed\n0,20\n", encoding="utf-8")
    cache_hash = hashlib.sha256(cache.read_bytes()).hexdigest()
    effective_identity = {**BASE_IDENTITY, **(identity or {})}
    schema_hash = _hash("critical-schema")
    effective_channels = channels or [_channel(name) for name in RAW_CHANNELS]
    manifest: dict[str, object] = {
        "manifest_schema_version": 4,
        "universal_archive_version": 1,
        "run_id": run_id,
        "source_file_sha256": source_hash,
        "telemetry_cache_sha256": cache_hash,
        "schema_fingerprint": schema_hash,
        "compatibility_fingerprint": compatibility_fingerprint(
            schema_hash,
            effective_identity,
        ),
        "compatibility_identity": effective_identity,
        "telemetry_rate_hz": 60,
        "record_count": 100,
        "declared_channel_count": len(effective_channels),
        "cached_channel_count": len(effective_channels),
        "lossless_archive_complete": lossless,
        "channels": effective_channels,
        "capabilities": [],
    }
    path = telemetry_manifest_path(data_dir, run_id)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _saved_session(db_path: Path, run_ids: list[str]) -> str:
    saved = create_session("Health baseline", db_path=db_path)
    for run_id in run_ids:
        add_run_to_session(saved.session_id, run_id, db_path=db_path)
    return saved.session_id


def _controlled_card() -> ControlledTestCard:
    return ControlledTestCard(
        hypothesis="A small cross-weight change improves center response.",
        control_key="cross_weight_percent",
        control_label="Cross Weight",
        direction_sign=1,
        current_value=50.0,
        proposed_value="50.1%",
        proposed_value_raw=50.1,
        proposed_value_provenance=("run-c:legal-option",),
        exact_change="50.0% to 50.1%",
        change_size="Small",
        target_phase="center",
        expected_mechanism="rotation response",
        success_metrics=("Center phase time improves beyond noise.",),
        countereffects=("Exit time does not regress.",),
        rollback_rule="Restore 50.0%.",
        keep_rule="Keep only after A/B/A2 confirmation.",
        stages=tuple(
            ControlledTestStage(
                stage=stage,
                setup_instruction=f"Record stage {stage}.",
                warmup_laps=1,
                required_flying_laps=3,
                purpose="Measure center response.",
            )
            for stage in ("A", "B", "A2")
        ),
        evidence_event_ids=("run-c:event",),
        do_not_change=("All other setup controls",),
    )


def _three_run_scope(tmp_path: Path) -> tuple[Path, Path, RaceLabRepository, str]:
    db_path = tmp_path / "health.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    for run_id in ("run-a", "run-b", "run-c"):
        _save_run(repository, data_dir, run_id)
    session_id = _saved_session(db_path, ["run-a", "run-b", "run-c"])
    return db_path, data_dir, repository, session_id


def test_health_baseline_binds_exact_session_build_schema_manifest_and_cache(
    tmp_path: Path,
) -> None:
    db_path, data_dir, repository, session_id = _three_run_scope(tmp_path)

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "healthy"
    assert report.authority == "measurement_health_only"
    assert report.vehicle_cause_attributed is False
    assert report.setup_authorized is False
    assert [item.run_id for item in report.baseline_identities] == ["run-a", "run-b"]
    assert report.current_identity is not None
    assert report.current_identity.run_id == "run-c"
    assert report.current_identity.iracing_build_version == "2026.08.07.01"
    assert report.current_identity.manifest_sha256 == hashlib.sha256(
        telemetry_manifest_path(data_dir, "run-c").read_bytes()
    ).hexdigest()
    assert len(report.comparisons) == len(RAW_CHANNELS)
    assert report.comparisons[0].metrics_compared == (
        "coverage",
        "range",
        "variation",
        "effective_rate",
        "missingness",
    )


def test_previously_healthy_channels_publish_typed_health_changes_only(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "changes.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    for run_id in ("run-a", "run-b"):
        _save_run(repository, data_dir, run_id)
    current_channels = [_channel(name) for name in RAW_CHANNELS]
    by_name = {item["canonical_name"]: item for item in current_channels}
    by_name["speed_mps"].update(
        _channel("speed_mps", variation="constant", observed_range=(40.0, 40.0))
    )
    by_name["brake_01"].update(
        _channel("brake_01", valid_records=70, health_status="warning")
    )
    by_name["throttle_01"].update(
        _channel(
            "throttle_01",
            health_status="warning",
            clipping_status="possible_numeric_limit_clipping",
            numeric_limit_hit_count=12,
        )
    )
    by_name["rpm"].update(_channel("rpm", observed_range=(15000.0, 19000.0)))
    by_name["gear"].update(_channel("gear", effective_rate_hz=30.0))
    _save_run(
        repository,
        data_dir,
        "run-c",
        channels=current_channels,
        lossless=False,
    )
    session_id = _saved_session(db_path, ["run-a", "run-b", "run-c"])

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "warning"
    assert {finding.kind for finding in report.findings} == {
        "dropout",
        "became_constant",
        "became_saturated",
        "range_shifted",
        "effective_rate_changed",
    }
    assert all(finding.authority == "measurement_health_only" for finding in report.findings)
    assert all(finding.vehicle_cause_attributed is False for finding in report.findings)
    assert all(finding.setup_authorized is False for finding in report.findings)
    assert {finding.recovery.action for finding in report.findings} == {
        "reimport_original_ibt",
        "record_verification_run",
    }


def test_health_warning_blocks_only_cards_using_the_affected_source_channel(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "action-health.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    for run_id in ("run-a", "run-b"):
        _save_run(repository, data_dir, run_id)
    current = [_channel(name) for name in RAW_CHANNELS]
    next(item for item in current if item["canonical_name"] == "speed_mps").update(
        _channel("speed_mps", variation="constant", observed_range=(40.0, 40.0))
    )
    _save_run(repository, data_dir, "run-c", channels=current)
    session_id = _saved_session(db_path, ["run-a", "run-b", "run-c"])
    health = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )
    card = _controlled_card()
    workflow = SimpleNamespace(
        packet=SimpleNamespace(
            primary_test=card,
            opportunity=SimpleNamespace(source_channels=()),
            decision="test",
            measurement_mission=None,
        )
    )

    affected = _telemetry_health_card_blockers(
        health,
        workflow,
        (SimpleNamespace(event_id="run-c:event", source_channels=("speed_mph",)),),
    )
    unrelated = _telemetry_health_card_blockers(
        health,
        workflow,
        (SimpleNamespace(event_id="run-c:event", source_channels=("yaw_rate",)),),
    )

    assert health.status == "warning"
    assert "speed_mph" in affected[0]
    assert "withheld" in affected[0]
    assert _controlled_decision(workflow, affected) is None
    assert _setup_values(workflow, affected) == ()
    assert unrelated == ()
    assert _controlled_decision(workflow, unrelated) is not None


def test_constant_change_requires_two_previously_healthy_varying_baselines(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "prior-warning.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    _save_run(repository, data_dir, "run-a")
    warned = [_channel(name) for name in RAW_CHANNELS]
    next(item for item in warned if item["canonical_name"] == "speed_mps")[
        "health_status"
    ] = "warning"
    _save_run(repository, data_dir, "run-b", channels=warned)
    current = [_channel(name) for name in RAW_CHANNELS]
    next(item for item in current if item["canonical_name"] == "speed_mps").update(
        _channel("speed_mps", variation="constant", observed_range=(40.0, 40.0))
    )
    _save_run(repository, data_dir, "run-c", channels=current)
    session_id = _saved_session(db_path, ["run-a", "run-b", "run-c"])

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "healthy"
    assert not report.findings


def test_one_prior_compatible_run_is_insufficient_history(tmp_path: Path) -> None:
    db_path = tmp_path / "short.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    _save_run(repository, data_dir, "run-a")
    _save_run(repository, data_dir, "run-b")
    session_id = _saved_session(db_path, ["run-a", "run-b"])

    report = build_telemetry_health_baseline(
        session_id,
        "run-b",
        expected_run_ids=("run-a", "run-b"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "insufficient_history"
    assert len(report.baseline_identities) == 1
    assert not report.comparisons
    assert report.recovery[0].action == "record_verification_run"


def test_incompatible_build_cannot_enter_the_baseline(tmp_path: Path) -> None:
    db_path = tmp_path / "build.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    _save_run(
        repository,
        data_dir,
        "run-a",
        identity={"iracing_build_version": "older-build"},
    )
    _save_run(repository, data_dir, "run-b")
    _save_run(repository, data_dir, "run-c")
    session_id = _saved_session(db_path, ["run-a", "run-b", "run-c"])

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "insufficient_history"
    assert [item.run_id for item in report.baseline_identities] == ["run-b"]


@pytest.mark.parametrize("tamper", ["manifest_source", "cache"])
def test_swapped_current_artifacts_fail_closed(tmp_path: Path, tamper: str) -> None:
    db_path, data_dir, repository, session_id = _three_run_scope(tmp_path)
    if tamper == "manifest_source":
        path = telemetry_manifest_path(data_dir, "run-c")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["source_file_sha256"] = _hash("source:run-a")
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        csv_path(data_dir, "run-c").write_text("changed\n", encoding="utf-8")

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "blocked"
    assert not report.comparisons
    assert not report.findings
    assert report.recovery[0].action == "reimport_original_ibt"


@pytest.mark.parametrize("tamper", ["duplicate_channel", "bad_missingness", "bad_mapping"])
def test_malformed_current_manifest_fails_closed(tmp_path: Path, tamper: str) -> None:
    db_path, data_dir, repository, session_id = _three_run_scope(tmp_path)
    path = telemetry_manifest_path(data_dir, "run-c")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if tamper == "duplicate_channel":
        payload["channels"].append(deepcopy(payload["channels"][0]))
        payload["declared_channel_count"] += 1
        payload["cached_channel_count"] += 1
    elif tamper == "bad_missingness":
        payload["channels"][0]["missing_fraction"] = 0.5
    else:
        payload["channels"][0]["canonical_name"] = "speed_mps"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "blocked"
    assert not report.findings


def test_malformed_prior_run_is_not_admitted_as_health_evidence(tmp_path: Path) -> None:
    db_path, data_dir, repository, session_id = _three_run_scope(tmp_path)
    path = telemetry_manifest_path(data_dir, "run-b")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["channels"][0]["missing_fraction"] = 0.75
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "insufficient_history"
    assert [item.run_id for item in report.baseline_identities] == ["run-a"]
    assert not report.findings
    assert any(item.run_id == "run-b" for item in report.recovery)


def test_changed_session_scope_blocks_without_relabelling_evidence(tmp_path: Path) -> None:
    db_path, data_dir, repository, session_id = _three_run_scope(tmp_path)

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "blocked"
    assert report.ordered_session_run_ids == ("run-a", "run-c")
    assert report.current_identity is None
    assert not report.comparisons


def test_public_model_rejects_probability_and_setup_authority(tmp_path: Path) -> None:
    db_path, data_dir, repository, session_id = _three_run_scope(tmp_path)
    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )
    payload = report.model_dump(mode="json")
    payload["probability"] = 0.95
    payload["setup_authorized"] = True

    with pytest.raises(ValidationError):
        TelemetryHealthBaselineReport.model_validate(payload)


def test_overlapping_range_change_does_not_claim_a_shift(tmp_path: Path) -> None:
    db_path = tmp_path / "overlap.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    for run_id in ("run-a", "run-b"):
        _save_run(repository, data_dir, run_id)
    current = [_channel(name) for name in RAW_CHANNELS]
    next(item for item in current if item["canonical_name"] == "speed_mps").update(
        _channel("speed_mps", observed_range=(30.0, 75.0))
    )
    _save_run(repository, data_dir, "run-c", channels=current)
    session_id = _saved_session(db_path, ["run-a", "run-b", "run-c"])

    report = build_telemetry_health_baseline(
        session_id,
        "run-c",
        expected_run_ids=("run-a", "run-b", "run-c"),
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert report.status == "healthy"
    assert not report.findings


def test_explicit_session_run_intelligence_and_api_broadcast_health_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, data_dir, _repository, session_id = _three_run_scope(tmp_path)
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))

    bundle = build_run_intelligence(
        "run-c",
        session_id=session_id,
        db_path=db_path,
    )
    public = to_public_intelligence_report(bundle.report)

    assert bundle.report.telemetry_health is not None
    assert bundle.report.telemetry_health.status == "healthy"
    assert public.telemetry_health is not None
    assert public.telemetry_health.current_run_id == "run-c"
    assert public.telemetry_health.authority == "measurement_health_only"
