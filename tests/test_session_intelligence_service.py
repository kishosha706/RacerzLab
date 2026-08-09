from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

import pytest

from racelab_engine.analysis.crew_chief_packet import (
    CauseCandidate,
    OpportunityEvidence,
    build_kaizen_packet,
)
from racelab_engine.analysis.evidence_contracts import EvidenceState
from racelab_engine.analysis.test_director import (
    TestEvidenceLink,
    TestExecution,
    score_test_execution,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.session_intelligence import (
    AngularOperatingContextMatch,
    CategoricalOperatingContextMatch,
    HypothesisPolicyIdentity,
    NumericOperatingContextMatch,
    OperatingContextAttestation,
    PairedLapOperatingContext,
    PositionAlignedEvidence,
    ProximityOperatingContextMatch,
    RacingLineContextMatch,
)
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.engineering_memory_service import (
    build_prediction_contract,
    build_prediction_grade,
    save_prediction_contract,
    save_prediction_grade,
)
from racelab_engine.services.import_service import csv_path, telemetry_manifest_path
from racelab_engine.services.session_intelligence_service import (
    SessionScopeChangedError,
    build_hypothesis_lifecycle,
    build_session_engineering_ledger,
    controlled_hypothesis_fingerprint,
    controlled_hypothesis_policy_identity,
    _events_match,
    _event_signature,
    evaluate_durable_hypothesis_repeat,
    evaluate_hypothesis_repeat,
    hypothesis_may_repeat,
    position_evidence_sha256,
    setup_policy_fingerprint,
    setup_snapshot_fingerprint,
)
from racelab_engine.services.session_service import (
    add_run_to_session,
    create_session,
    quarantine_session_intelligence_history,
    remove_run_from_session,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
IDENTITY = {
    "driver_user_id": 42,
    "car_id": 1,
    "car_path": "stockcars/gen7",
    "car_version": "2026.08",
    "track_id": 7,
    "track_configuration_name": "oval",
    "track_version": "2026.1",
    "iracing_build_version": "2026.08.01",
    "session_type": "Practice",
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _setup(run_id: str, *, cross: float = 50.0, brake_bias: float = 55.0) -> SetupSnapshot:
    return SetupSnapshot(
        setup_id=f"setup-{run_id}",
        run_id=run_id,
        setup_name="baseline",
        tape_percent=40.0,
        rear_end_ratio=3.25,
        lf_ride_height_mm=55.0,
        rf_ride_height_mm=55.0,
        lr_ride_height_mm=70.0,
        rr_ride_height_mm=70.0,
        lf_front_spring_n_per_mm=300.0,
        rf_front_spring_n_per_mm=300.0,
        lr_rear_spring_n_per_mm=250.0,
        rr_rear_spring_n_per_mm=250.0,
        nose_weight_percent=49.0,
        cross_weight_percent=cross,
        front_brake_bias_percent=brake_bias,
        steering_ratio="12:1",
        steering_offset_deg=0.0,
    )


def _laps(run_id: str, base_time: float, *, junk: bool = False) -> list[LapSummary]:
    return [
        LapSummary(
            lap_id=f"{run_id}:{number}",
            run_id=run_id,
            lap_number=number,
            lap_type="out_lap" if junk else "flying",
            is_complete=not junk,
            is_useful=not junk,
            lap_time=base_time + offset,
            pct_min=0.0,
            pct_max=99.9,
            pct_span=99.9,
            sample_count=6000,
            classification_tags=["OUT_LAP"] if junk else [],
        )
        for number, offset in ((1, 0.0), (2, 0.05), (3, -0.04))
    ]


def _position_context(
    baseline_run_id: str,
    test_run_id: str,
) -> OperatingContextAttestation:
    source_channels = (
        "fuel_level",
        "air_temp",
        "track_temp",
        "wind_vel",
        "wind_dir",
        "lf_tire_distance_m",
        "rf_tire_distance_m",
        "lr_tire_distance_m",
        "rr_tire_distance_m",
        "player_tire_compound",
        "lat",
        "lon",
        "car_distance_ahead_m",
        "car_distance_behind_m",
        "speed_mps",
    )

    def numeric(channel: str, value: float, tolerance: float, span: float):
        return NumericOperatingContextMatch(
            channel=channel,
            baseline_range=(value, value),
            test_range=(value, value),
            baseline_coverage=1.0,
            test_coverage=1.0,
            tolerance=tolerance,
            maximum_within_lap_span=span,
        )

    return OperatingContextAttestation(
        pairs=tuple(
            PairedLapOperatingContext(
                baseline_lap_id=f"{baseline_run_id}:{lap_number}",
                test_lap_id=f"{test_run_id}:{lap_number}",
                fuel=numeric("fuel_level", 20.0, 2.0, 10.0),
                air_temperature=numeric("air_temp", 25.0, 5.0, 5.0),
                track_temperature=numeric("track_temp", 35.0, 5.0, 8.0),
                wind_speed=numeric("wind_vel", 2.0, 2.0, 3.0),
                wind_direction=AngularOperatingContextMatch(
                    baseline_median=1.0,
                    test_median=1.0,
                    absolute_delta_rad=0.0,
                    maximum_delta_rad=0.35,
                    baseline_coverage=1.0,
                    test_coverage=1.0,
                ),
                tire_distances=tuple(
                    numeric(channel, 1_000.0, 1_000.0, 5_000.0)
                    for channel in (
                        "lf_tire_distance_m",
                        "rf_tire_distance_m",
                        "lr_tire_distance_m",
                        "rr_tire_distance_m",
                    )
                ),
                tire_compound=CategoricalOperatingContextMatch(
                    baseline_value="primary",
                    test_value="primary",
                    baseline_coverage=1.0,
                    test_coverage=1.0,
                ),
                line=RacingLineContextMatch(
                    coverage_fraction=1.0,
                    median_deviation_m=0.2,
                    p95_deviation_m=0.4,
                    maximum_median_deviation_m=1.5,
                ),
                proximity=ProximityOperatingContextMatch(
                    channels=(
                        "car_distance_ahead_m",
                        "car_distance_behind_m",
                        "speed_mps",
                    ),
                    baseline_state="no_nearby_car_reported",
                    test_state="no_nearby_car_reported",
                    baseline_coverage=1.0,
                    test_coverage=1.0,
                    baseline_min_distance_ahead_m=500.0,
                    baseline_min_distance_behind_m=500.0,
                    test_min_distance_ahead_m=500.0,
                    test_min_distance_behind_m=500.0,
                    baseline_min_time_gap_ahead_s=12.5,
                    baseline_min_time_gap_behind_s=12.5,
                    test_min_time_gap_ahead_s=12.5,
                    test_min_time_gap_behind_s=12.5,
                    ahead_exclusion_seconds=1.5,
                    behind_exclusion_seconds=0.5,
                ),
                source_channels=source_channels,
            )
            for lap_number in (1, 2, 3)
        ),
        source_channels=source_channels,
    )


def _position_evidence(
    baseline_run_id: str,
    test_run_id: str,
    *,
    delta_s: float,
    noise_s: float = 0.01,
) -> PositionAlignedEvidence:
    context = _position_context(baseline_run_id, test_run_id)
    draft = PositionAlignedEvidence(
        evidence_id=f"position:{baseline_run_id}:{test_run_id}",
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        baseline_lap_ids=tuple(
            f"{baseline_run_id}:{lap_number}" for lap_number in (1, 2, 3)
        ),
        test_lap_ids=tuple(
            f"{test_run_id}:{lap_number}" for lap_number in (1, 2, 3)
        ),
        start_pct=20.0,
        end_pct=30.0,
        phase="entry",
        delta_s=delta_s,
        empirical_noise_s=noise_s,
        alignment_confidence=0.95,
        source_channels=("lap_dist_pct_100", *context.source_channels),
        context_match=context,
        provenance_sha256="0" * 64,
    )
    return PositionAlignedEvidence(
        **draft.model_dump(exclude={"provenance_sha256"}),
        provenance_sha256=position_evidence_sha256(draft),
    )


def test_racing_line_tail_limit_cannot_be_widened_by_supplied_evidence() -> None:
    payload = _position_context("run-a", "run-b").model_dump(mode="json")
    payload["pairs"][0]["line"].update(
        {
            "p95_deviation_m": 100.0,
            "maximum_p95_deviation_m": 100.0,
        }
    )

    with pytest.raises(ValueError, match="less than or equal to 3"):
        OperatingContextAttestation.model_validate(payload)


def _event(run_id: str, event_id: str | None = None) -> TelemetryEvent:
    return TelemetryEvent(
        event_id=event_id or f"{run_id}:event-entry",
        run_id=run_id,
        lap_number=2,
        event_type="CORNER_BALANCE",
        event_subtype="tight_entry",
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        lap_pct_peak=25.0,
        zone_name="Turn 1",
        confidence_score=0.9,
        valid_for_tuning=True,
        related_setup_keys=["cross_weight_percent"],
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=["lap_dist_pct_100", "speed_mps"],
        blocker_reasons=[],
        evidence_json={"phase": "entry"},
    )


@pytest.mark.parametrize(
    "update",
    [
        {"confidence_score": 0.0},
        {"evidence_state": EvidenceState.UNAVAILABLE},
        {"blocker_reasons": ["The producer did not qualify this event."]},
    ],
)
def test_session_event_signature_requires_actionable_evidence(update) -> None:
    event = _event("run-a").model_copy(update=update)

    assert _event_signature(event) is None


def test_event_matching_tolerates_small_physical_window_jitter() -> None:
    baseline = _event("run-a")
    shifted = _event("run-b").model_copy(update={
        "lap_pct_start": 20.1,
        "lap_pct_end": 30.1,
        "lap_pct_peak": 25.1,
    })
    assert _events_match(baseline, shifted) is True


def _write_artifacts(
    data_dir: Path,
    run_id: str,
    source_hash: str,
    *,
    identity: dict[str, object] | None = None,
) -> dict[str, object]:
    cache = csv_path(data_dir, run_id)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("SessionTime,lap\n0,1\n", encoding="utf-8")
    cache_hash = hashlib.sha256(cache.read_bytes()).hexdigest()
    effective_identity = {**IDENTITY, **(identity or {})}
    manifest = {
        "manifest_schema_version": 4,
        "universal_archive_version": 1,
        "run_id": run_id,
        "source_file_sha256": source_hash,
        "telemetry_cache_sha256": cache_hash,
        "schema_fingerprint": _hash("schema"),
        "compatibility_fingerprint": _hash(json.dumps(effective_identity, sort_keys=True)),
        "compatibility_identity": effective_identity,
        "lossless_archive_complete": True,
        "declared_channel_count": 2,
        "cached_channel_count": 2,
        "channels": [
            {
                "name": raw_name,
                "raw_name": raw_name,
                "archive_column": raw_name,
                "canonical_name": canonical_name,
                "archive_status": "cached",
                "record_count": 1,
                "valid_record_count": 1,
                "health_status": "healthy",
            }
            for raw_name, canonical_name in (
                ("LapDistPct", "lap_dist_pct"),
                ("Speed", "speed_mps"),
            )
        ],
        "capabilities": [],
    }
    path = telemetry_manifest_path(data_dir, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _save_run(
    repo: RaceLabRepository,
    data_dir: Path,
    run_id: str,
    *,
    base_time: float = 30.0,
    setup: SetupSnapshot | None = None,
    identity: dict[str, object] | None = None,
    junk: bool = False,
    include_event: bool = True,
) -> dict[str, object]:
    source_hash = _hash(f"source:{run_id}")
    manifest = _write_artifacts(data_dir, run_id, source_hash, identity=identity)
    overview = RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            source_file=f"{run_id}.ibt",
            file_hash=source_hash,
            import_time=NOW,
            car_name="Test Car",
            car_path="stockcars/gen7",
            track_name="test-track",
            track_id_or_path="7",
            session_type="Practice",
            setup_passed_tech=True,
        ),
        laps=_laps(run_id, base_time, junk=junk),
        events=[_event(run_id)] if include_event and not junk else [],
        setup_snapshot=setup or _setup(run_id),
    )
    repo.save_import(overview)
    return manifest


def _session_with_runs(db_path: Path, run_ids: list[str]) -> str:
    session = create_session("Engineering night", db_path=db_path)
    for run_id in run_ids:
        add_run_to_session(session.session_id, run_id, db_path=db_path)
    return session.session_id


def test_session_ledger_reports_observed_direction_without_causal_attribution(tmp_path) -> None:
    db_path = tmp_path / "ledger.sqlite"
    data_dir = tmp_path / "data"
    repo = RaceLabRepository(db_path)
    _save_run(repo, data_dir, "run-a", base_time=30.0)
    _save_run(repo, data_dir, "run-b", base_time=29.8, setup=_setup("run-b", cross=50.5))
    session_id = _session_with_runs(db_path, ["run-a", "run-b"])

    ledger = build_session_engineering_ledger(
        session_id,
        expected_run_ids=("run-a", "run-b"),
        position_evidence=(_position_evidence("run-a", "run-b", delta_s=-0.2),),
        db_path=db_path,
        data_dir=data_dir,
    )

    pace = next(entry for entry in ledger.entries if entry.observation_kind == "pace")
    assert ledger.status == "ready"
    assert pace.state == "improved"
    assert pace.delta_s == pytest.approx(-0.2)
    assert pace.attribution == "observation_only"
    assert pace.causal_claim is False
    assert pace.setup_changes[0].setup_key == "cross_weight_percent"
    assert "does not attribute" in pace.description
    assert {citation.kind for citation in pace.citations} >= {"run", "lap", "setup", "manifest"}


def test_resolved_event_requires_healthy_observable_source_channels(tmp_path) -> None:
    db_path = tmp_path / "resolved-capability.sqlite"
    data_dir = tmp_path / "data"
    repo = RaceLabRepository(db_path)
    _save_run(repo, data_dir, "run-a")
    manifest = _save_run(repo, data_dir, "run-b", include_event=False)
    session_id = _session_with_runs(db_path, ["run-a", "run-b"])

    observable = build_session_engineering_ledger(
        session_id,
        db_path=db_path,
        data_dir=data_dir,
    )
    assert any(entry.state == "resolved" for entry in observable.entries)

    manifest["channels"] = [
        {
            **channel,
            "health_status": (
                "warning"
                if channel.get("canonical_name") == "speed_mps"
                else channel.get("health_status")
            ),
        }
        for channel in manifest["channels"]
    ]
    telemetry_manifest_path(data_dir, "run-b").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    withheld = build_session_engineering_ledger(
        session_id,
        db_path=db_path,
        data_dir=data_dir,
    )

    assert not any(entry.state == "resolved" for entry in withheld.entries)
    assert any(
        "healthy observable source-channel coverage" in blocker
        and "speed_mps" in blocker
        for blocker in withheld.blocker_reasons
    )


def test_test_only_event_is_recorded_as_new(tmp_path) -> None:
    db_path = tmp_path / "new-event.sqlite"
    data_dir = tmp_path / "data"
    repo = RaceLabRepository(db_path)
    _save_run(repo, data_dir, "run-a", include_event=False)
    _save_run(repo, data_dir, "run-b", include_event=True)
    session_id = _session_with_runs(db_path, ["run-a", "run-b"])

    ledger = build_session_engineering_ledger(
        session_id,
        db_path=db_path,
        data_dir=data_dir,
    )

    new_entry = next(entry for entry in ledger.entries if entry.state == "new")
    assert new_entry.observation_kind == "new_issue"
    assert any(citation.run_id == "run-b" for citation in new_entry.citations)


@pytest.mark.parametrize(
    ("second_setup", "second_identity", "expected_blocker"),
    [
        (_setup("run-b", cross=50.5, brake_bias=56.0), None, "More than one setup control changed"),
        (_setup("run-b"), {"track_version": "different"}, "track_version changed"),
    ],
)
def test_session_ledger_rejects_multi_change_and_context_mismatch(
    tmp_path, second_setup, second_identity, expected_blocker
) -> None:
    db_path = tmp_path / "blocked.sqlite"
    data_dir = tmp_path / "data"
    repo = RaceLabRepository(db_path)
    _save_run(repo, data_dir, "run-a")
    _save_run(repo, data_dir, "run-b", setup=second_setup, identity=second_identity)
    session_id = _session_with_runs(db_path, ["run-a", "run-b"])

    ledger = build_session_engineering_ledger(session_id, db_path=db_path, data_dir=data_dir)

    assert ledger.status == "blocked"
    assert ledger.entries[0].state == "not_comparable"
    assert any(expected_blocker in reason for reason in ledger.entries[0].blocker_reasons)
    assert ledger.entries[0].delta_s is None
    assert ledger.entries[0].causal_claim is False


def test_session_ledger_rejects_junk_laps_and_tampered_position_evidence(tmp_path) -> None:
    db_path = tmp_path / "junk.sqlite"
    data_dir = tmp_path / "data"
    repo = RaceLabRepository(db_path)
    _save_run(repo, data_dir, "run-a")
    _save_run(repo, data_dir, "run-b", junk=True)
    session_id = _session_with_runs(db_path, ["run-a", "run-b"])

    junk = build_session_engineering_ledger(session_id, db_path=db_path, data_dir=data_dir)
    assert junk.entries[0].state == "not_comparable"
    assert any("No currently eligible" in reason for reason in junk.entries[0].blocker_reasons)

    # Restore a valid second run in a fresh exact session, then supply a digest
    # that does not bind to the claimed physical-window evidence.
    _save_run(repo, data_dir, "run-c", base_time=29.8)
    session2 = _session_with_runs(db_path, ["run-a", "run-c"])
    tampered = PositionAlignedEvidence(
        evidence_id="position-1",
        baseline_run_id="run-a",
        test_run_id="run-c",
        baseline_lap_ids=("run-a:1", "run-a:2", "run-a:3"),
        test_lap_ids=("run-c:1", "run-c:2", "run-c:3"),
        start_pct=20.0,
        end_pct=30.0,
        phase="entry",
        delta_s=-0.05,
        empirical_noise_s=0.01,
        alignment_confidence=0.95,
        source_channels=(
            "lap_dist_pct_100",
            "fuel_level",
            "air_temp",
            "track_temp",
            "wind_vel",
            "wind_dir",
            "lat",
            "lon",
            "car_distance_ahead_m",
            "car_distance_behind_m",
            "speed_mps",
            "lf_tire_distance_m",
            "rf_tire_distance_m",
            "lr_tire_distance_m",
            "rr_tire_distance_m",
            "player_tire_compound",
        ),
        context_match=_position_context("run-a", "run-c"),
        provenance_sha256="0" * 64,
    )
    assert position_evidence_sha256(tampered) != tampered.provenance_sha256
    blocked = build_session_engineering_ledger(
        session2,
        position_evidence=(tampered,),
        db_path=db_path,
        data_dir=data_dir,
    )
    assert blocked.entries[0].state == "not_comparable"
    assert any("provenance hash" in reason for reason in blocked.entries[0].blocker_reasons)


@pytest.mark.parametrize("tamper", ["missing_context", "inside_noise"])
def test_session_ledger_revalidates_context_and_noise_attestations(tmp_path, tamper) -> None:
    db_path = tmp_path / f"position-{tamper}.sqlite"
    data_dir = tmp_path / "data"
    repo = RaceLabRepository(db_path)
    _save_run(repo, data_dir, "run-a")
    _save_run(repo, data_dir, "run-b", base_time=29.8)
    session_id = _session_with_runs(db_path, ["run-a", "run-b"])
    evidence = _position_evidence("run-a", "run-b", delta_s=-0.05)
    if tamper == "missing_context":
        evidence = evidence.model_copy(update={"context_match": None})
    else:
        evidence = evidence.model_copy(update={"delta_s": -0.005})
    evidence = evidence.model_copy(
        update={"provenance_sha256": position_evidence_sha256(evidence)}
    )

    ledger = build_session_engineering_ledger(
        session_id,
        position_evidence=(evidence,),
        db_path=db_path,
        data_dir=data_dir,
    )

    assert ledger.status == "blocked"
    assert ledger.entries[0].state == "not_comparable"
    joined = " ".join(ledger.entries[0].blocker_reasons)
    if tamper == "missing_context":
        assert "fuel, tire, weather, line, and proximity" in joined
    else:
        assert "does not exceed paired-lap empirical noise" in joined


def test_removed_session_membership_invalidates_a_pinned_request(tmp_path) -> None:
    db_path = tmp_path / "scope.sqlite"
    session_id = _session_with_runs(db_path, ["run-a", "run-b"])
    remove_run_from_session(session_id, "run-b", db_path=db_path)

    with pytest.raises(SessionScopeChangedError, match="membership changed"):
        build_session_engineering_ledger(
            session_id, expected_run_ids=("run-a", "run-b"), db_path=db_path
        )


def _packet():
    link = TestEvidenceLink(
        event_id="run-source:event-entry",
        eligible_lap=True,
        valid_for_tuning=True,
        phase="entry",
        related_setup_keys=("cross_weight_percent",),
    )
    return build_kaizen_packet(
        opportunity=OpportunityEvidence(
            start_pct=20.0,
            end_pct=30.0,
            phase="entry",
            observed_time_loss_s=0.2,
            empirical_noise_s=0.01,
            alignment_confidence=0.95,
            repeatable=True,
            evidence_links=(link,),
            source_channels=("lap_dist_pct_100", "speed_mps"),
            supporting_evidence=("Entry loss repeated on eligible laps.",),
        ),
        canonical_symptom="tight_entry",
        candidates=[
            CauseCandidate(
                cause_bucket="corner_balance",
                control_key="cross_weight_percent",
                direction_sign=1,
                score=0.9,
                hypothesis="Test whether cross weight improves entry.",
                success_metrics=("Entry time improves beyond noise.",),
                countereffects=("Center time must remain within baseline noise.",),
                supporting_event_ids=("run-source:event-entry",),
            )
        ],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={
            "cross_weight_percent": {"50.5": ["tech-passing-setup:option-run"]}
        },
    )


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _scored_workflow(
    workflow_id: str,
    *,
    verdict: str,
    manifests: dict[str, dict[str, object]],
    setups: dict[str, SetupSnapshot],
) -> ControlledWorkflow:
    expected_verdict = verdict
    countereffect_passed = True
    if verdict == "keep":
        effects = (-0.05, -0.05)
        distribution = "faster"
        context_match = 0.96
    elif verdict == "undo":
        effects = (0.05, 0.05)
        distribution = "slower"
        context_match = 0.96
    elif verdict == "undo_countereffect":
        effects = (-0.05, -0.05)
        distribution = "faster"
        context_match = 0.96
        countereffect_passed = False
        expected_verdict = "undo"
    elif verdict == "retest":
        effects = (-0.005, -0.004)
        distribution = "inconclusive"
        context_match = 0.96
    else:
        effects = (-0.05, -0.05)
        distribution = "faster"
        context_match = 0.5
    execution = TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=3,
        unrelated_setup_changes=0,
        control_key="cross_weight_percent",
        planned_b_value=50.5,
        observed_a_value=50.0,
        observed_b_value=50.5,
        observed_a2_value=50.0,
        context_match_score=context_match,
        driver_match_score=0.96,
        sim_integrity_score=0.98,
        phase_effect_b_vs_a_s=effects[0],
        phase_effect_b_vs_a2_s=effects[1],
        empirical_noise_s=0.01,
        empirical_noise_observations=3,
        minimum_alignment_confidence=0.93,
        target_effect_distributions_consistent=distribution in {"faster", "slower"},
        target_effect_distribution_state=distribution,
        countereffect_passed=countereffect_passed,
        control_guardrails_passed=True,
        countereffect_noise_by_phase_s={"center": 0.01},
        control_guardrail_metrics={"tire_temperature_delta": 1.0},
    )
    quality = score_test_execution(execution)
    assert quality.verdict == expected_verdict
    stage_run_ids = {"A": "run-a", "B": "run-b", "A2": "run-a2"}
    stage_laps = {stage: (1, 2, 3) for stage in stage_run_ids}
    chronology = {
        "source": {"run_id": "run-source"},
        "A": {"run_id": "run-a"},
        "B": {"run_id": "run-b"},
        "A2": {"run_id": "run-a2"},
    }
    decision_context = {
        "selected_lap": None,
        "lap_scope": "run",
        "window_start_lap": None,
        "window_end_lap": None,
        "representative_lap": None,
        "selected_zone_start_pct": None,
        "selected_zone_end_pct": None,
        "selected_zone_label": None,
        "selected_phase": None,
        "objective": "setup-development",
        "priority": None,
    }
    packet = _packet()
    workflow = ControlledWorkflow(
        workflow_id=workflow_id,
        created_at=NOW,
        updated_at=NOW + timedelta(hours=1),
        status="scored",
        source_run_id="run-source",
        complaint="It pushes on entry",
        packet=packet,
        stage_run_ids=stage_run_ids,
        stage_eligible_lap_numbers=stage_laps,
        execution=execution,
        quality=quality,
        learning_admitted=expected_verdict == "keep",
        reproduction_snapshot={
            "recording_chronology": chronology,
            "decision_context": decision_context,
            "pooled_target_effect_s": median(effects),
        },
    )
    plan_payload = {
        "source_run_id": workflow.source_run_id,
        "complaint": workflow.complaint,
        "decision_context": decision_context,
        "packet": workflow.packet.model_dump(mode="json"),
    }
    stage_payload = {
        "stage_run_ids": stage_run_ids,
        "stage_eligible_lap_numbers": stage_laps,
        "recording_chronology": chronology,
    }
    reproduction_stages: dict[str, object] = {}
    for stage, run_id in stage_run_ids.items():
        setup = setups[run_id]
        setup_payload = setup.model_dump(mode="json")
        reproduction_stages[stage] = {
            "run_id": run_id,
            "source_file_sha256": _hash(f"source:{run_id}"),
            "schema_fingerprint": manifests[run_id]["schema_fingerprint"],
            "cache_version": None,
            "compatibility_identity": manifests[run_id]["compatibility_identity"],
            "setup_fingerprint": _json_hash(setup_payload),
            "setup_values": setup_payload,
            "eligible_lap_numbers": [1, 2, 3],
        }
    return workflow.model_copy(
        update={
            "reproduction_snapshot": {
                **workflow.reproduction_snapshot,
                "plan_binding_sha256": _json_hash(plan_payload),
                "stage_binding_sha256": _json_hash(stage_payload),
                "stages": reproduction_stages,
            }
        }
    )


def _lifecycle_fixture(tmp_path: Path, verdict: str):
    db_path = tmp_path / f"{verdict}.sqlite"
    data_dir = tmp_path / f"data-{verdict}"
    repo = RaceLabRepository(db_path)
    setups = {
        "run-source": _setup("run-source"),
        "run-a": _setup("run-a"),
        "run-b": _setup("run-b", cross=50.5),
        "run-a2": _setup("run-a2"),
    }
    manifests = {
        run_id: _save_run(repo, data_dir, run_id, setup=setup)
        for run_id, setup in setups.items()
    }
    session_id = _session_with_runs(db_path, list(setups))
    workflow = _scored_workflow(
        f"workflow-{verdict}", verdict=verdict, manifests=manifests, setups=setups
    )
    repo.save_controlled_workflow(workflow)
    contract = build_prediction_contract(workflow)
    save_prediction_contract(contract, db_path=db_path)
    save_prediction_grade(build_prediction_grade(workflow, contract), db_path=db_path)
    return db_path, data_dir, session_id, workflow


@pytest.mark.parametrize(
    ("verdict", "expected_state", "expected_outcome"),
    [
        ("keep", "supported", "supported"),
        ("undo", "do_not_repeat", "contradicted"),
        ("retest", "inconclusive", "inconclusive"),
        ("invalid", "invalid", "invalid"),
    ],
)
def test_hypothesis_lifecycle_preserves_keep_undo_retest_and_invalid(
    tmp_path, verdict, expected_state, expected_outcome
) -> None:
    db_path, data_dir, session_id, _workflow = _lifecycle_fixture(tmp_path, verdict)

    lifecycle = build_hypothesis_lifecycle(
        session_id, db_path=db_path, data_dir=data_dir
    )

    entry = lifecycle.entries[0]
    assert entry.lifecycle_state == expected_state
    assert entry.outcome_classification == expected_outcome
    assert entry.target_effect.phase == "entry"
    assert entry.countereffects.criteria == ("Center time must remain within baseline noise.",)
    assert entry.protocol.verdict == verdict
    assert entry.protocol.eligible_lap_ids
    citation_kinds = {citation.kind for citation in entry.citations}
    assert citation_kinds >= {"workflow", "run", "lap", "event"}
    if verdict != "invalid":
        assert citation_kinds >= {"prediction_contract", "prediction_grade"}


def test_countereffect_only_undo_preserves_supported_target_outcome(tmp_path) -> None:
    db_path, data_dir, session_id, _workflow = _lifecycle_fixture(
        tmp_path,
        "undo_countereffect",
    )

    lifecycle = build_hypothesis_lifecycle(
        session_id,
        db_path=db_path,
        data_dir=data_dir,
    )

    entry = lifecycle.entries[0]
    assert entry.protocol.verdict == "undo"
    assert entry.lifecycle_state == "do_not_repeat"
    assert entry.do_not_repeat is True
    assert entry.countereffects.passed is False
    assert entry.target_effect.direction_result == "matched"
    assert entry.outcome_classification == "supported"
    assert "recorded separately for cause reasoning" in entry.do_not_repeat_reason


def test_failed_exact_hypothesis_is_not_repeated_but_changed_context_is_new(tmp_path) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    failed = lifecycle.entries[0]

    assert failed.lifecycle_state == "do_not_repeat"
    assert not hypothesis_may_repeat(lifecycle, failed.hypothesis_fingerprint)
    changed = controlled_hypothesis_fingerprint(
        workflow,
        {**IDENTITY, "track_version": "new-version"},
        source_setup_fingerprint=setup_snapshot_fingerprint(_setup("run-source")),
    )
    assert changed != failed.hypothesis_fingerprint
    assert hypothesis_may_repeat(lifecycle, changed)


def test_hypothesis_fingerprint_binds_source_run_and_exact_source_setup(tmp_path) -> None:
    _db_path, _data_dir, _session_id, workflow = _lifecycle_fixture(tmp_path, "keep")
    source_setup = _setup("run-source")
    source_setup_hash = setup_snapshot_fingerprint(source_setup)
    assert source_setup_hash is not None

    first = controlled_hypothesis_fingerprint(
        workflow,
        IDENTITY,
        source_setup_fingerprint=source_setup_hash,
    )
    repeated = controlled_hypothesis_fingerprint(
        workflow,
        dict(IDENTITY),
        source_setup_fingerprint=source_setup_hash,
    )
    different_run = controlled_hypothesis_fingerprint(
        workflow.model_copy(update={"source_run_id": "different-source-run"}),
        IDENTITY,
        source_setup_fingerprint=source_setup_hash,
    )
    changed_setup_hash = setup_snapshot_fingerprint(
        _setup("run-source", cross=50.5)
    )
    assert changed_setup_hash is not None
    different_setup = controlled_hypothesis_fingerprint(
        workflow,
        IDENTITY,
        source_setup_fingerprint=changed_setup_hash,
    )

    assert first == repeated
    assert different_run != first
    assert different_setup != first


def test_undo_policy_survives_protocol_wording_event_and_run_identity_churn(tmp_path) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    failed = lifecycle.entries[0]
    assert failed.hypothesis_policy is not None
    card = workflow.packet.primary_test
    assert card is not None
    changed_card = card.model_copy(
        update={
            "hypothesis": "Different display wording for the same controlled question.",
            "expected_mechanism": "Different explanatory wording only.",
            "success_metrics": ("The same producer contract, worded differently.",),
            "proposed_value": "50.500 percent",
            "proposed_value_raw": "50.5%",
            "countereffects": (
                "  CENTER   TIME MUST REMAIN WITHIN BASELINE NOISE.  ",
            ),
            "rollback_rule": "Different rollback wording.",
            "keep_rule": "Different keep wording.",
            "stop_rule": "Different stop wording.",
            "evidence_event_ids": ("run-a:new-event-id",),
            "stages": tuple(
                stage.model_copy(
                    update={
                        "setup_instruction": f"Reworded {stage.stage} instruction.",
                        "purpose": f"Reworded {stage.stage} purpose.",
                    }
                )
                for stage in card.stages
            ),
        }
    )
    changed_workflow = workflow.model_copy(
        update={
            "workflow_id": "workflow-wording-churn",
            "source_run_id": "run-a",
            "complaint": "Different driver wording.",
            "packet": workflow.packet.model_copy(
                update={
                    "primary_test": changed_card,
                    "opportunity": workflow.packet.opportunity.model_copy(
                        update={
                            "start_pct": workflow.packet.opportunity.start_pct + 1e-12,
                            "end_pct": workflow.packet.opportunity.end_pct - 1e-12,
                        }
                    ),
                }
            ),
        }
    )
    candidate = controlled_hypothesis_policy_identity(
        changed_workflow,
        IDENTITY,
        source_setup=_setup("run-a"),
    )
    changed_protocol = controlled_hypothesis_fingerprint(
        changed_workflow,
        IDENTITY,
        source_setup_fingerprint=setup_snapshot_fingerprint(_setup("run-a")),
    )

    assert changed_protocol != failed.protocol_fingerprint
    assert candidate == failed.hypothesis_policy
    decision = evaluate_hypothesis_repeat(lifecycle, candidate)
    assert decision.status == "blocked"
    assert not decision.allowed
    assert decision.matched_workflow_ids == (workflow.workflow_id,)
    assert decision.changed_dimensions == ()
    assert not hypothesis_may_repeat(lifecycle, candidate)
    assert not hypothesis_may_repeat(lifecycle, candidate.policy_key)


@pytest.mark.parametrize("session_type", ["practice", "  Practice  ", "PRACTICE"])
def test_undo_policy_survives_compatibility_text_representation_churn(
    tmp_path,
    session_type,
) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    candidate = controlled_hypothesis_policy_identity(
        workflow.model_copy(update={"workflow_id": "workflow-context-format"}),
        {**IDENTITY, "session_type": session_type},
        source_setup=_setup(workflow.source_run_id),
    )

    decision = evaluate_hypothesis_repeat(lifecycle, candidate)

    assert decision.status == "blocked"
    assert not decision.allowed
    assert decision.matched_workflow_ids == (workflow.workflow_id,)
    assert decision.changed_dimensions == ()


def test_setup_policy_fingerprint_ignores_integer_float_serialization_churn() -> None:
    integer_setup = _setup("run-source").model_copy(
        update={
            "setup_json": {
                "Chassis": {"Front": {"CrossWeight": 50}},
                "Name": "Baseline",
            },
            "extracted_values": {"CrossWeight": 50},
        }
    )
    float_setup = _setup("run-source").model_copy(
        update={
            "setup_json": {
                "chassis": {"front": {"crossweight": 50.0}},
                "name": "Different display name",
            },
            "extracted_values": {"crossweight": 50.0},
        }
    )

    assert setup_policy_fingerprint(integer_setup) == setup_policy_fingerprint(float_setup)


def test_setup_policy_ignores_only_root_display_metadata_and_preserves_nested_names() -> None:
    baseline = _setup("run-source").model_copy(
        update={
            "setup_json": {
                "Name": "Baseline display name",
                "SetupName": "Garage display name",
                "Tires": {"Compound": {"Name": "Soft"}},
            },
            "extracted_values": {"raw_source": "CarSetup"},
        }
    )
    root_metadata_churn = baseline.model_copy(
        update={
            "setup_json": {
                "Name": "Renamed baseline",
                "SetupName": "Renamed garage setup",
                "Tires": {"Compound": {"Name": "Soft"}},
            },
            "extracted_values": {"raw_source": "session_yaml"},
        }
    )
    material_nested_change = root_metadata_churn.model_copy(
        update={
            "setup_json": {
                "Name": "Renamed baseline",
                "SetupName": "Renamed garage setup",
                "Tires": {"Compound": {"Name": "Hard"}},
            },
        }
    )

    assert setup_policy_fingerprint(baseline) == setup_policy_fingerprint(
        root_metadata_churn
    )
    assert setup_policy_fingerprint(baseline) != setup_policy_fingerprint(
        material_nested_change
    )


def test_setup_policy_fingerprint_is_invariant_to_known_control_source_location() -> None:
    known = _setup("run-source")
    raw = known.model_copy(
        update={
            "cross_weight_percent": None,
            "setup_json": {"Chassis": {"Front": {"CrossWeight": 50.0}}},
            "extracted_values": {},
        }
    )
    extracted = known.model_copy(
        update={
            "cross_weight_percent": None,
            "setup_json": {},
            "extracted_values": {"CrossWeight": 50},
        }
    )
    redundant = raw.model_copy(
        update={"extracted_values": {"crossweight": " 50.0 % "}},
    )
    material_change = raw.model_copy(
        update={"setup_json": {"Chassis": {"Front": {"CrossWeight": 50.5}}}},
    )

    fingerprints = {
        setup_policy_fingerprint(candidate)
        for candidate in (known, raw, extracted, redundant)
    }

    assert len(fingerprints) == 1
    assert setup_policy_fingerprint(material_change) not in fingerprints


def test_setup_policy_preserves_unmapped_raw_material_and_rejects_collisions() -> None:
    baseline = _setup("run-source").model_copy(
        update={"setup_json": {"Chassis": {"RearARB": {"Diameter": 51}}}},
    )
    changed = baseline.model_copy(
        update={"setup_json": {"Chassis": {"RearARB": {"Diameter": 52}}}},
    )
    derived_churn = baseline.model_copy(
        update={"extracted_values": {"rear_arb_diameter_mm": 999}},
    )

    assert setup_policy_fingerprint(baseline) != setup_policy_fingerprint(changed)
    assert setup_policy_fingerprint(baseline) == setup_policy_fingerprint(derived_churn)
    with pytest.raises(ValueError, match="colliding keys"):
        setup_policy_fingerprint(
            baseline.model_copy(
                update={"setup_json": {"Unknown": 1, " unknown ": 1}},
            )
        )
    with pytest.raises(ValueError, match="conflicting semantic values"):
        setup_policy_fingerprint(
            _setup("run-source").model_copy(
                update={
                    "setup_json": {"CrossWeight": 50.0},
                    "extracted_values": {"cross_weight_percent": 50.5},
                }
            )
        )


def test_setup_policy_preserves_steering_pinion_representation_semantics() -> None:
    raw = _setup("run-source").model_copy(
        update={
            "steering_ratio": None,
            "setup_json": {"Chassis": {"Front": {"SteeringPinion": "60 mm/rev"}}},
            "extracted_values": {},
        }
    )
    extracted = raw.model_copy(
        update={
            "setup_json": {},
            "extracted_values": {"steering_pinion_mm": 60.0},
        }
    )
    material_change = extracted.model_copy(
        update={"extracted_values": {"steering_pinion_mm": 62.0}},
    )

    assert setup_policy_fingerprint(raw) == setup_policy_fingerprint(extracted)
    assert setup_policy_fingerprint(raw) != setup_policy_fingerprint(material_change)


def test_undo_policy_cannot_be_evaded_by_integer_float_setup_churn(tmp_path) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    entry = lifecycle.entries[0]
    integer_setup = _setup(workflow.source_run_id).model_copy(
        update={
            "setup_json": {"Chassis": {"Front": {"CrossWeight": 50}}},
            "extracted_values": {"CrossWeight": 50},
        }
    )
    float_setup = integer_setup.model_copy(
        update={
            "setup_json": {"chassis": {"front": {"crossweight": 50.0}}},
            "extracted_values": {"crossweight": 50.0},
        }
    )
    previous = controlled_hypothesis_policy_identity(
        workflow,
        IDENTITY,
        source_setup=integer_setup,
    )
    candidate = controlled_hypothesis_policy_identity(
        workflow.model_copy(update={"workflow_id": "workflow-numeric-format"}),
        IDENTITY,
        source_setup=float_setup,
    )
    lifecycle_with_integer_policy = lifecycle.model_copy(
        update={
            "entries": (
                entry.model_copy(update={"hypothesis_policy": previous}),
            )
        }
    )

    decision = evaluate_hypothesis_repeat(lifecycle_with_integer_policy, candidate)

    assert decision.status == "blocked"
    assert not decision.allowed
    assert decision.matched_workflow_ids == (workflow.workflow_id,)
    assert decision.changed_dimensions == ()


def test_undo_policy_cannot_be_evaded_by_known_control_source_location_churn(
    tmp_path,
) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    entry = lifecycle.entries[0]
    raw_setup = _setup(workflow.source_run_id).model_copy(
        update={
            "cross_weight_percent": None,
            "setup_json": {"Chassis": {"Front": {"CrossWeight": 50}}},
            "extracted_values": {},
        }
    )
    extracted_setup = raw_setup.model_copy(
        update={
            "setup_json": {},
            "extracted_values": {"cross_weight_percent": 50.0},
        }
    )
    changed_setup = extracted_setup.model_copy(
        update={"extracted_values": {"cross_weight_percent": 50.5}},
    )
    previous = controlled_hypothesis_policy_identity(
        workflow,
        IDENTITY,
        source_setup=raw_setup,
    )
    candidate = controlled_hypothesis_policy_identity(
        workflow.model_copy(update={"workflow_id": "workflow-source-churn"}),
        IDENTITY,
        source_setup=extracted_setup,
    )
    changed = controlled_hypothesis_policy_identity(
        workflow.model_copy(update={"workflow_id": "workflow-material-change"}),
        IDENTITY,
        source_setup=changed_setup,
    )
    lifecycle_with_raw_policy = lifecycle.model_copy(
        update={"entries": (entry.model_copy(update={"hypothesis_policy": previous}),)},
    )

    repeated = evaluate_hypothesis_repeat(lifecycle_with_raw_policy, candidate)
    material = evaluate_hypothesis_repeat(lifecycle_with_raw_policy, changed)

    assert repeated.status == "blocked"
    assert repeated.changed_dimensions == ()
    assert material.status == "allowed"
    assert material.changed_dimensions == ("setup",)


def test_repeat_policy_binds_exact_physical_target_window(tmp_path) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    previous = lifecycle.entries[0].hypothesis_policy
    assert previous is not None
    opportunity = workflow.packet.opportunity.model_copy(
        update={"start_pct": 70.0, "end_pct": 80.0},
    )
    changed_window = workflow.model_copy(
        update={
            "workflow_id": "workflow-turn-four",
            "packet": workflow.packet.model_copy(update={"opportunity": opportunity}),
        }
    )

    candidate = controlled_hypothesis_policy_identity(
        changed_window,
        IDENTITY,
        source_setup=_setup(workflow.source_run_id),
    )
    decision = evaluate_hypothesis_repeat(lifecycle, candidate)

    assert candidate.target_scope_sha256 != previous.target_scope_sha256
    assert decision.status == "allowed"
    assert decision.changed_dimensions == ("location",)


def test_repeat_policy_rejects_a_missing_or_zero_physical_target_window(tmp_path) -> None:
    _db_path, _data_dir, _session_id, workflow = _lifecycle_fixture(tmp_path, "keep")
    invalid_opportunity = workflow.packet.opportunity.model_copy(
        update={"end_pct": workflow.packet.opportunity.start_pct},
    )
    invalid = workflow.model_copy(
        update={
            "packet": workflow.packet.model_copy(
                update={"opportunity": invalid_opportunity},
            )
        }
    )

    with pytest.raises(ValueError, match="physical target window"):
        controlled_hypothesis_policy_identity(
            invalid,
            IDENTITY,
            source_setup=_setup(workflow.source_run_id),
        )


@pytest.mark.parametrize(
    ("updates", "expected_dimension"),
    [
        ({"context_sha256": "1" * 64}, "context"),
        ({"setup_sha256": "2" * 64}, "setup"),
        ({"target_scope_sha256": "4" * 64}, "location"),
        ({"proposed_control_value_sha256": "3" * 64}, "setup"),
        ({"canonical_symptom": "loose_exit"}, "symptom"),
        ({"cause_bucket": "aero_platform"}, "cause"),
        ({"control_key": "front_brake_bias_percent"}, "control"),
        ({"control_direction_sign": -1}, "direction"),
        ({"expected_effect_direction": "increase"}, "direction"),
        ({"target_metric": "following_straight_carry_s"}, "metric"),
        ({"target_phase": "center"}, "phase"),
        ({"countereffects": ("entry time must remain inside noise.",)}, "countereffects"),
    ],
)
def test_material_policy_dimension_change_allows_a_new_controlled_hypothesis(
    tmp_path,
    updates,
    expected_dimension,
) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    previous = lifecycle.entries[0].hypothesis_policy
    assert previous is not None
    dimensions = previous.model_dump(
        mode="python",
        exclude={"policy_key", "policy_version"},
    )
    dimensions.update(updates)
    candidate = HypothesisPolicyIdentity.build(**dimensions)

    decision = evaluate_hypothesis_repeat(lifecycle, candidate)

    assert decision.status == "allowed"
    assert decision.allowed
    assert decision.matched_workflow_ids == ()
    assert decision.changed_dimensions == (expected_dimension,)
    assert len(decision.comparisons) == 1
    assert decision.comparisons[0].workflow_id == workflow.workflow_id
    assert decision.comparisons[0].changed_dimensions == (expected_dimension,)


def test_policy_identity_rejects_a_key_that_does_not_bind_its_dimensions(tmp_path) -> None:
    db_path, data_dir, session_id, _workflow = _lifecycle_fixture(tmp_path, "undo")
    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)
    policy = lifecycle.entries[0].hypothesis_policy
    assert policy is not None

    with pytest.raises(ValueError, match="bind every exact policy dimension"):
        HypothesisPolicyIdentity.model_validate(
            {**policy.model_dump(mode="json"), "policy_key": "f" * 64}
        )


@pytest.mark.parametrize("tamper", ["stage_provenance", "prediction_grade_hash"])
def test_hypothesis_lifecycle_fails_closed_on_hash_or_provenance_mismatch(
    tmp_path, tamper
) -> None:
    db_path, data_dir, session_id, workflow = _lifecycle_fixture(tmp_path, "keep")
    connection = initialize_database(db_path)
    if tamper == "stage_provenance":
        snapshot = dict(workflow.reproduction_snapshot)
        stages = {key: dict(value) for key, value in snapshot["stages"].items()}
        stages["B"]["source_file_sha256"] = "f" * 64
        snapshot["stages"] = stages
        connection.execute(
            "UPDATE controlled_test_workflows SET reproduction_snapshot_json = ? WHERE workflow_id = ?",
            (json.dumps(snapshot), workflow.workflow_id),
        )
    else:
        row = connection.execute(
            "SELECT grade_id, grade_json FROM engineering_prediction_grades WHERE workflow_id = ?",
            (workflow.workflow_id,),
        ).fetchone()
        grade = json.loads(row["grade_json"])
        grade["prediction_contract_sha256"] = "f" * 64
        connection.execute(
            "UPDATE engineering_prediction_grades SET grade_json = ? WHERE grade_id = ?",
            (json.dumps(grade), row["grade_id"]),
        )
    connection.commit()
    connection.close()

    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)

    assert lifecycle.status == "blocked"
    assert lifecycle.entries[0].lifecycle_state == "invalid"
    joined = " ".join(lifecycle.entries[0].protocol.blocker_reasons)
    assert "provenance" in joined or "prediction grade hash" in joined


def test_removed_stage_membership_invalidates_controlled_history(tmp_path) -> None:
    db_path, data_dir, session_id, _workflow = _lifecycle_fixture(tmp_path, "keep")
    remove_run_from_session(session_id, "run-b", db_path=db_path)

    lifecycle = build_hypothesis_lifecycle(session_id, db_path=db_path, data_dir=data_dir)

    assert lifecycle.status == "blocked"
    assert lifecycle.entries[0].lifecycle_state == "invalid"
    assert any(
        "no longer a member" in reason
        for reason in lifecycle.entries[0].protocol.blocker_reasons
    )


def test_unreadable_saved_session_blocks_durable_repeat_authority(tmp_path) -> None:
    db_path, _data_dir, _session_id, workflow = _lifecycle_fixture(tmp_path, "keep")
    candidate = controlled_hypothesis_policy_identity(
        workflow,
        IDENTITY,
        source_setup=_setup(workflow.source_run_id),
    )
    connection = initialize_database(db_path)
    connection.execute(
        """
        INSERT INTO racelab_sessions (
          session_id, name, created_at, updated_at, run_ids_json, status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "session_unreadable",
            "Unreadable history",
            NOW.isoformat(),
            NOW.isoformat(),
            "{not-valid-json",
            "archived",
        ),
    )
    connection.commit()
    connection.close()

    decision = evaluate_durable_hypothesis_repeat(candidate, db_path=db_path)

    assert decision.status == "blocked"
    assert not decision.allowed
    assert decision.matched_workflow_ids == ()
    assert decision.changed_dimensions == ()
    assert decision.history_debt[0].session_id == "session_unreadable"
    assert decision.history_debt[0].kind == "history_incomplete"

    quarantine_session_intelligence_history(
        "session_unreadable",
        "The archived session source is intentionally unavailable for recovery.",
        db_path=db_path,
    )
    quarantined = evaluate_durable_hypothesis_repeat(candidate, db_path=db_path)

    assert quarantined.status == "allowed"
    assert quarantined.allowed
    assert quarantined.history_debt == ()
