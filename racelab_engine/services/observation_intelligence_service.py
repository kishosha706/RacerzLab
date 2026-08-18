"""Thin repository wrapper for pure same-setup observation builders."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from racelab_engine.analysis.dynamic_response import (
    analyze_brake_throttle_dynamic_response,
)
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.observation_intelligence import (
    adapt_event_mechanism_observations,
    build_driver_repeatability_signature,
    build_opportunity_signatures,
    build_same_setup_anomaly_envelopes,
)
from racelab_engine.models.evidence import (
    EngineeringBlockTarget,
    EvidenceState,
    engineering_blockers_for,
)
from racelab_engine.models.observation_intelligence import (
    DriverRepeatabilitySignature,
    MechanismObservationReport,
    ObservationStatus,
    OpportunitySignatureReport,
    RunObservationIntelligence,
    SameSetupAnomalyReport,
)
from racelab_engine.services.engineering_awareness_service import (
    EngineeringAwarenessEvidenceBuild,
    build_engineering_awareness_evidence,
)
from racelab_engine.services.import_service import (
    TelemetryArtifactIdentityError,
    read_telemetry_rows,
)
from racelab_engine.services.p3_observation_bridge import (
    build_p3_mechanism_observations,
    merge_mechanism_observation_reports,
    p3_observation_columns,
    revalidate_event_mechanism_observations,
)
from racelab_engine.storage.repository import RaceLabRepository

_DEFAULT_ANOMALY_CHANNELS = (
    "speed_mph",
    "brake_pct",
    "throttle_pct",
    "steering_deg",
)
_OBSERVATION_COLUMNS = [
    "lap",
    "lap_number",
    "lap_dist_pct_100",
    "lap_dist_pct",
    "session_time",
    "speed_mph",
    "speed_mps",
    "throttle_pct",
    "brake_pct",
    "steering_deg",
    "yaw_rate",
    "lat_accel",
    "long_accel",
    "vert_accel",
    "vert_accel_g",
    "on_pit_road",
    "enter_exit_reset_state",
    "lf_shock_vel_in_s",
    "rf_shock_vel_in_s",
    "lr_shock_vel_in_s",
    "rr_shock_vel_in_s",
    "applied_brake_bias",
    "requested_lf_tire_cold_pressure_pa",
    "requested_rf_tire_cold_pressure_pa",
    "requested_lr_tire_cold_pressure_pa",
    "requested_rr_tire_cold_pressure_pa",
    "requested_left_tire_change",
    "requested_right_tire_change",
    "requested_fuel_fill",
    "requested_fuel_add_kg",
    "requested_fuel_auto_fill_enabled",
    "requested_fuel_auto_fill_active",
]


@dataclass(frozen=True)
class ObservationAwarenessBuild:
    observations: RunObservationIntelligence
    awareness: EngineeringAwarenessEvidenceBuild
    telemetry_rows: tuple[dict[str, Any], ...] = ()


def _blocked_bundle(run_id: str, reason: str) -> RunObservationIntelligence:
    blockers = (reason,)
    return RunObservationIntelligence(
        run_id=run_id,
        setup_id=None,
        opportunity_signatures=OpportunitySignatureReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=None,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            eligible_lap_count=0,
            telemetry_sample_count=0,
            blocker_reasons=blockers,
        ),
        mechanism_observations=MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=None,
            blocker_reasons=blockers,
        ),
        anomaly_envelopes=SameSetupAnomalyReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=None,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            required_channels=("lap_dist_pct_100", *_DEFAULT_ANOMALY_CHANNELS),
            eligible_lap_count=0,
            reference_lap_count=0,
            telemetry_sample_count=0,
            blocker_reasons=blockers,
        ),
        driver_repeatability=DriverRepeatabilitySignature(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=None,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            eligible_lap_count=0,
            telemetry_sample_count=0,
            blocker_reasons=blockers,
        ),
        blocker_reasons=blockers,
    )


def _blocked_build(run_id: str, reason: str) -> ObservationAwarenessBuild:
    observations = _blocked_bundle(run_id, reason)
    episode_report = MechanismObservationReport(
        status=ObservationStatus.BLOCKED,
        run_id=run_id,
        setup_id=None,
        blocker_reasons=(reason,),
    )
    return ObservationAwarenessBuild(
        observations=observations,
        awareness=EngineeringAwarenessEvidenceBuild(
            frames=(),
            transitions=(),
            episodes=(),
            episode_observations=episode_report,
            blocker_reasons=(reason,),
        ),
        telemetry_rows=(),
    )


def _build_observation_intelligence_with_awareness(
    run_id: str,
    session_run_ids: Sequence[str] | None = None,
    *,
    repository: Any | None = None,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    anomaly_channels: Sequence[str] = _DEFAULT_ANOMALY_CHANNELS,
) -> ObservationAwarenessBuild:
    """Load one exact run and assemble non-authorizing observation reports.

    ``session_run_ids`` is only an ownership guard.  This builder never merges
    telemetry across runs and never treats another session run as same-setup
    evidence.
    """
    if not run_id.strip():
        return _blocked_build("invalid-run", "A non-empty run identity is required.")
    if session_run_ids is not None:
        scope = tuple(session_run_ids)
        if len(scope) != len(set(scope)):
            return _blocked_build(run_id, "Session run identities are duplicated.")
        if run_id not in scope:
            return _blocked_build(
                run_id,
                "The requested run is not part of the supplied session scope.",
            )
    repo = repository or RaceLabRepository(db_path)
    try:
        overview = repo.get_overview(run_id)
    except (OSError, TypeError, ValueError) as exc:
        return _blocked_build(run_id, f"Stored run evidence could not be verified: {exc}")
    if overview is None:
        return _blocked_build(run_id, f"Run not found: {run_id}")
    if overview.run_id != run_id or overview.session.run_id != run_id:
        return _blocked_build(
            run_id, "The stored run identity does not match the requested scope."
        )
    integrity_blockers = engineering_blockers_for(
        overview.engineering_blockers,
        EngineeringBlockTarget.OBSERVATION,
    )
    if integrity_blockers:
        return _blocked_build(
            run_id,
            " ".join(blocker.message for blocker in integrity_blockers),
        )

    setup = overview.setup_snapshot
    setup_id = setup.setup_id if setup is not None and setup.run_id == run_id else None
    event_mechanisms = adapt_event_mechanism_observations(
        overview.events,
        overview.laps,
        run_id=run_id,
        setup_id=setup_id,
    )
    event_source_channels = tuple(
        channel
        for observation in event_mechanisms.observations
        if observation.qualified
        for channel in observation.source_channels
    )
    # The intelligence shell also builds per-lap engineering context.  Include
    # that builder's canonical inputs in this single artifact read so the cold
    # path does not materialize the same telemetry cache a second time.
    from racelab_engine.services.lap_engineering_context_service import (
        _CONTEXT_CHANNELS,
    )

    requested_columns = list(dict.fromkeys([
        *_OBSERVATION_COLUMNS,
        *_CONTEXT_CHANNELS,
        *anomaly_channels,
        *event_source_channels,
        *p3_observation_columns(),
    ]))
    read_blocker: str | None = None
    try:
        rows = read_telemetry_rows(run_id, data_dir, columns=requested_columns)
    except (
        FileNotFoundError,
        OSError,
        TelemetryArtifactIdentityError,
        TypeError,
        ValueError,
    ) as exc:
        rows = []
        read_blocker = f"Telemetry artifacts could not be verified: {exc}"
    # A verified cache is now explicitly bound to this requested run for the
    # pure builders' cross-run guard.  Untrusted caller-supplied rows never pass
    # through this wrapper.
    # ``read_telemetry_rows`` owns these freshly materialized dictionaries.
    # Bind them in place rather than allocating and copying another full cold
    # telemetry population solely to add an immutable run identity.
    for row in rows:
        row["run_id"] = run_id
    scoped_rows = rows
    brake_throttle_response = analyze_brake_throttle_dynamic_response(
        scoped_rows,
        run_id=run_id,
        setup_id=setup_id,
        eligible_lap_numbers=tuple(
            lap.lap_number for lap in eligible_laps(overview.laps)
        ),
        expected_sample_rate_hz=getattr(
            overview.session,
            "telemetry_rate_hz",
            None,
        ),
    )
    lap_setup_ids = (
        {lap.lap_number: setup_id for lap in overview.laps}
        if setup_id is not None
        else None
    )
    opportunity = build_opportunity_signatures(
        scoped_rows,
        overview.laps,
        run_id=run_id,
        setup_id=setup_id,
        lap_setup_ids=lap_setup_ids,
    )
    if read_blocker is not None:
        # Persisted events do not remain qualified when their source telemetry
        # artifact cannot be re-bound to this exact run.
        mechanisms = MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=(read_blocker,),
        )
    else:
        event_mechanisms = revalidate_event_mechanism_observations(
            event_mechanisms,
            scoped_rows,
        )
        existing_mechanisms = frozenset(
            observation.mechanism
            for observation in event_mechanisms.observations
            if observation.qualified
        )
        p3_mechanisms = build_p3_mechanism_observations(
            scoped_rows,
            overview.laps,
            run_id=run_id,
            setup_id=setup_id,
            telemetry_rate_hz=overview.session.telemetry_rate_hz,
            redline_rpm=(
                overview.session.shift_light_rpm_thresholds.blink_rpm
                if overview.session.shift_light_rpm_thresholds is not None
                else None
            ),
            preferred_lap_number=(
                overview.best_useful_lap.lap_number
                if overview.best_useful_lap is not None
                else None
            ),
            existing_mechanisms=existing_mechanisms,
        )
        mechanisms = merge_mechanism_observation_reports(
            run_id,
            setup_id,
            (event_mechanisms, p3_mechanisms),
        )
    awareness = build_engineering_awareness_evidence(
        mechanisms,
        scoped_rows,
        run_id=run_id,
        setup_id=setup_id,
    )
    if awareness.episode_observations.status is ObservationStatus.READY:
        mechanisms = merge_mechanism_observation_reports(
            run_id,
            setup_id,
            (mechanisms, awareness.episode_observations),
        )
    anomalies = build_same_setup_anomaly_envelopes(
        scoped_rows,
        overview.laps,
        run_id=run_id,
        setup_id=setup_id,
        channels=anomaly_channels,
        lap_setup_ids=lap_setup_ids,
    )
    driver = build_driver_repeatability_signature(
        scoped_rows,
        overview.laps,
        run_id=run_id,
        setup_id=setup_id,
        lap_setup_ids=lap_setup_ids,
    )
    aggregate_blockers = tuple(dict.fromkeys(
        blocker
        for group in (
            (read_blocker,) if read_blocker else (),
            opportunity.blocker_reasons,
            mechanisms.blocker_reasons,
            awareness.blocker_reasons,
            anomalies.blocker_reasons,
            driver.blocker_reasons,
        )
        for blocker in group
        if blocker
    ))
    return ObservationAwarenessBuild(
        observations=RunObservationIntelligence(
            run_id=run_id,
            setup_id=setup_id,
            opportunity_signatures=opportunity,
            mechanism_observations=mechanisms,
            anomaly_envelopes=anomalies,
            driver_repeatability=driver,
            brake_throttle_response=brake_throttle_response,
            blocker_reasons=aggregate_blockers,
        ),
        awareness=awareness,
        telemetry_rows=tuple(scoped_rows),
    )


def build_observation_intelligence(
    run_id: str,
    session_run_ids: Sequence[str] | None = None,
    *,
    repository: Any | None = None,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    anomaly_channels: Sequence[str] = _DEFAULT_ANOMALY_CHANNELS,
) -> RunObservationIntelligence:
    return _build_observation_intelligence_with_awareness(
        run_id,
        session_run_ids,
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
        anomaly_channels=anomaly_channels,
    ).observations


def build_observation_intelligence_with_awareness(
    run_id: str,
    session_run_ids: Sequence[str] | None = None,
    *,
    repository: Any | None = None,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    anomaly_channels: Sequence[str] = _DEFAULT_ANOMALY_CHANNELS,
) -> ObservationAwarenessBuild:
    return _build_observation_intelligence_with_awareness(
        run_id,
        session_run_ids,
        repository=repository,
        db_path=db_path,
        data_dir=data_dir,
        anomaly_channels=anomaly_channels,
    )


__all__ = [
    "ObservationAwarenessBuild",
    "build_observation_intelligence",
    "build_observation_intelligence_with_awareness",
]
