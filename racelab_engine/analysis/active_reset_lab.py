"""Repeatability analysis for corroborated Active Reset section attempts."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.analysis.lap_detection import direct_invalid_context_tags
from racelab_engine.analysis.test_director import active_reset_attempt_groups
from racelab_engine.analysis.proximity_context import classify_proximity_time_gap_window
from racelab_engine.models.evidence import EvidenceState


class ActiveResetAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: int
    start_index: int
    end_index: int
    target_start_pct: float
    target_end_pct: float
    duration_s: float | None = None
    complete: bool
    blocker_reasons: tuple[str, ...] = ()


class ActiveResetLabResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_start_pct: float
    target_end_pct: float
    attempts: tuple[ActiveResetAttempt, ...]
    eligible_attempt_count: int = Field(ge=0)
    median_duration_s: float | None = None
    empirical_noise_s: float | None = None
    repeatability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    repeatable: bool
    evidence_state: EvidenceState
    source_channels: tuple[str, ...]
    blockers: tuple[str, ...]
    full_lap_eligible: bool = False


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _pct(row: dict[str, Any]) -> float | None:
    value = _finite(row.get("lap_dist_pct_100"))
    if value is None:
        value = _finite(row.get("lap_dist_pct") if row.get("lap_dist_pct") is not None else row.get("LapDistPct"))
        if value is not None and value <= 1.5:
            value *= 100.0
    return value


def _crossing_time(samples: list[tuple[float, float]], target: float) -> float | None:
    for (left_pct, left_time), (right_pct, right_time) in zip(samples, samples[1:]):
        if left_pct <= target <= right_pct and right_pct > left_pct:
            fraction = (target - left_pct) / (right_pct - left_pct)
            return left_time + fraction * (right_time - left_time)
    return None


def _has_complete_channel(section: list[dict[str, Any]], *names: str) -> bool:
    return any(all(row.get(name) is not None for row in section) for name in names)


def analyze_active_reset_lab(
    rows: list[dict[str, Any]],
    *,
    target_start_pct: float,
    target_end_pct: float,
) -> ActiveResetLabResult:
    if not 0.0 <= target_start_pct < target_end_pct <= 100.0:
        raise ValueError("Active Reset target must be a non-zero 0-100% track-position window.")
    all_times = [
        value for row in rows
        if (value := _finite(row.get("session_time") if row.get("session_time") is not None else row.get("SessionTime"))) is not None
    ]
    clock_monotonic = len(all_times) == len(rows) and all(right > left for left, right in zip(all_times, all_times[1:]))
    attempts: list[ActiveResetAttempt] = []
    for number, (start, end) in enumerate(active_reset_attempt_groups(rows), start=1):
        section = rows[start:end + 1]
        timed = [(_pct(row), _finite(row.get("session_time") if row.get("session_time") is not None else row.get("SessionTime"))) for row in section]
        samples = [(pct, timestamp) for pct, timestamp in timed if pct is not None and timestamp is not None]
        blockers: list[str] = []
        positions = [value for row in section if (value := _pct(row)) is not None]
        if len(section) < 10:
            blockers.append("Attempt has fewer than ten samples.")
        if len(positions) != len(section) or any(right < left for left, right in zip(positions, positions[1:])):
            blockers.append("Attempt track position is missing or reversed.")
        if not clock_monotonic:
            blockers.append("Run clock is missing, duplicated, or non-monotonic.")
        duration = None
        bracketed = bool(positions and min(positions) < target_start_pct and max(positions) > target_end_pct)
        start_time = _crossing_time(samples, target_start_pct)
        end_time = _crossing_time(samples, target_end_pct)
        target_samples = [row for row in section if (pct := _pct(row)) is not None and target_start_pct <= pct <= target_end_pct]
        if not bracketed or start_time is None or end_time is None:
            blockers.append("Attempt does not bracket and cover the complete target window.")
        elif len(target_samples) < 8:
            blockers.append("Attempt has fewer than eight target-window samples.")
        elif end_time <= start_time:
            blockers.append("Attempt clock is missing or non-monotonic through the target window.")
        else:
            duration = end_time - start_time
        pit_states = [
            row.get("on_pit_road") if row.get("on_pit_road") is not None else row.get("OnPitRoad")
            for row in section
        ]
        surface_covered = _has_complete_channel(section, "player_track_surface", "PlayerTrackSurface")
        if any(value is None for value in pit_states) and not surface_covered:
            blockers.append("Pit-road or track-surface state is unavailable across the full attempt.")
        elif all(value is not None for value in pit_states) and any(bool(value) for value in pit_states):
            blockers.append("Attempt entered pit road.")
        caution_coverage = any(
            all(row.get(channel) is not None for row in section)
            for channel in ("session_flags", "SessionFlags", "under_caution", "pace_mode_active", "pace_mode")
        )
        if not caution_coverage:
            blockers.append("Caution or pacing state is unavailable across the full attempt.")
        if any(bool(
            row.get("under_caution")
            or row.get("pace_mode_active")
            or (_finite(row.get("pace_mode")) or 0.0) != 0.0
            or row.get("slowdown")
        ) for row in section):
            blockers.append("Attempt contains caution, pacing, or slowdown context.")
        canonical_junk = direct_invalid_context_tags(section)
        relevant_junk = canonical_junk & {
            "PIT_ROAD", "OFF_TRACK", "YELLOW", "CAUTION", "INCIDENT_COUNT_INCREASE",
            "INVALID_SPEED_EVENT", "WRECK_OR_SPIN", "SAMPLE_DISCONTINUITY",
        }
        if relevant_junk:
            blockers.append(
                "Attempt contains canonical junk context: " + ", ".join(sorted(relevant_junk)) + "."
            )
        on_track_covered = _has_complete_channel(section, "is_on_track", "IsOnTrack")
        if not section or (not on_track_covered and not surface_covered):
            blockers.append("On-track or track-surface state is unavailable between reset release and target completion.")
        elif on_track_covered and any(
            row.get("is_on_track") is not True and row.get("IsOnTrack") is not True for row in section
        ):
            blockers.append("Attempt is off track or on-track state is unavailable between reset release and target completion.")
        incident_channels = (
            "player_incident_count", "player_driver_incident_count", "player_team_incident_count",
            "PlayerCarMyIncidentCount", "PlayerCarDriverIncidentCount", "PlayerCarTeamIncidentCount",
        )
        incident_counter_covered = False
        for channel in incident_channels:
            counts = [_finite(row.get(channel)) for row in section]
            observed = [value for value in counts if value is not None]
            if len(observed) == len(section):
                incident_counter_covered = True
            if len(observed) == len(section) and max(observed) > min(observed):
                blockers.append("Incident count increased after attempt entry.")
                break
        if not incident_counter_covered:
            blockers.append("An authoritative incident counter is unavailable across the full attempt.")
        if any(bool(row.get("incident") or row.get("wreck") or row.get("slowdown") or row.get("invalid_speed")) for row in section):
            blockers.append("Attempt contains an incident, wreck, slowdown, or invalid-speed sample before target completion.")
        if any(bool(
            row.get("player_in_pit_stall")
            or row.get("repair_required")
            or row.get("pitstop_active")
            or (_finite(row.get("player_tow_service_time_s")) or 0.0) > 0.0
            or (_finite(row.get("pit_repair_remaining_s")) or 0.0) > 0.0
            or (_finite(row.get("pit_optional_repair_remaining_s")) or 0.0) > 0.0
        ) for row in section):
            blockers.append("Attempt contains tow, repair, or pit-service context.")
        if any((_finite(row.get("speed_mps")) is not None and _finite(row.get("speed_mps")) <= 1.0) for row in target_samples):
            blockers.append("Attempt contains invalid target-window speed.")
        # The first row may be the boundary that opened this attempt. Any later
        # reset evidence contaminates the declared pre-roll-to-target evidence unit.
        if any(bool(
            row.get("reset_event") or row.get("active_reset_event") or row.get("reset_discontinuity")
        ) for row in section[1:]):
            blockers.append("Attempt contains another reset transition before target completion.")
        if classify_proximity_time_gap_window(target_samples).blocks_relative_resistance:
            blockers.append("Attempt nearby-car context is inside the exclusion window or unavailable.")
        attempts.append(ActiveResetAttempt(
            attempt_number=number, start_index=start, end_index=end,
            target_start_pct=target_start_pct, target_end_pct=target_end_pct,
            duration_s=round(duration, 5) if duration is not None else None,
            complete=not blockers, blocker_reasons=tuple(blockers),
        ))
    durations = [attempt.duration_s for attempt in attempts if attempt.complete and attempt.duration_s is not None]
    center = median(durations) if durations else None
    noise = median(abs(value - center) for value in durations) if center is not None else None
    score = (
        max(0.0, 1.0 - noise / max(center * 0.02, 0.001))
        if center is not None and noise is not None and len(durations) >= 3 else None
    )
    repeatable = len(durations) >= 3 and score is not None and score >= 0.8
    blockers = []
    if not clock_monotonic:
        blockers.append("Run clock is missing, duplicated, or non-monotonic.")
    if len(attempts) < 2:
        blockers.append("No corroborated reset boundaries produced multiple section attempts.")
    if len(durations) < 3:
        blockers.append("At least three complete target-window attempts are required.")
    if len(durations) >= 3 and not repeatable:
        blockers.append("Section time varies beyond the repeatability threshold.")
    actual_sources = tuple(dict.fromkeys(
        channel
        for channel in (
            "lap_dist_pct_100", "lap_dist_pct", "LapDistPct", "session_time", "SessionTime",
            "enter_exit_reset_state", "EnterExitReset", "reset_event", "active_reset_event",
            "reset_discontinuity", "speed_mps", "car_distance_ahead_m", "car_distance_behind_m",
            "is_on_track", "IsOnTrack", "player_track_surface", "player_incident_count",
            "player_driver_incident_count", "player_team_incident_count",
            "under_caution", "pace_mode_active", "session_flags",
            "player_in_pit_stall", "player_tow_service_time_s", "repair_required",
            "pitstop_active", "pit_repair_remaining_s", "pit_optional_repair_remaining_s",
        )
        if any(row.get(channel) is not None for row in rows)
    ))
    return ActiveResetLabResult(
        target_start_pct=target_start_pct, target_end_pct=target_end_pct,
        attempts=tuple(attempts), eligible_attempt_count=len(durations),
        median_duration_s=round(center, 5) if center is not None else None,
        empirical_noise_s=round(noise, 5) if noise is not None else None,
        repeatability_score=round(score, 3) if score is not None else None,
        repeatable=repeatable,
        evidence_state=EvidenceState.CALCULATED if len(durations) >= 3 else EvidenceState.NEEDS_CONFIRMATION,
        source_channels=actual_sources,
        blockers=tuple(blockers),
        # Section attempts are evidence units only and never become eligible full laps.
        full_lap_eligible=False,
    )


__all__ = ["ActiveResetAttempt", "ActiveResetLabResult", "analyze_active_reset_lab"]
