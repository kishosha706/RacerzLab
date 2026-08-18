from __future__ import annotations

import math
from typing import Iterable

from racelab_engine.models.lap import LapSummary


INVALID_TUNING_TAGS = frozenset(
    {
        "PARTIAL",
        "SHORT_RUN",
        "OUT_LAP",
        "COOLDOWN",
        "PIT_ROAD",
        "OFF_TRACK",
        "WRECK_OR_SPIN",
        "INVALID_SPEED_EVENT",
        "CAUTION",
        "YELLOW",
        "RESET",
        "ACTIVE_RESET",
        "SAMPLE_DISCONTINUITY",
        "CLOCK_RESET_BOUNDARY",
        "TIMING_INTEGRITY_BLOCKED",
        "POSITION_DISCONTINUITY",
        "SPARSE_POSITION_COVERAGE",
        "NON_CREDIBLE_LAP_SAMPLING",
        "INCIDENT_COUNT_INCREASE",
        "INVALID_FOR_PLATFORM_TUNING",
        "NO_SETUP_CONCLUSION",
    }
)


_TAG_REASONS = {
    "PARTIAL": "Incomplete lap",
    "SHORT_RUN": "Partial-distance lap",
    "OUT_LAP": "Out lap",
    "COOLDOWN": "Cool-down or abnormally slow lap",
    "PIT_ROAD": "Pit road included",
    "OFF_TRACK": "Off-track samples detected",
    "WRECK_OR_SPIN": "Wreck or spin detected",
    "INVALID_SPEED_EVENT": "Implausible or invalid speed event",
    "CAUTION": "Caution period",
    "YELLOW": "Yellow-flag period",
    "RESET": "Reset segment",
    "ACTIVE_RESET": "Active Reset segment",
    "SAMPLE_DISCONTINUITY": "Telemetry sample continuity failed",
    "CLOCK_RESET_BOUNDARY": "Lap crossed a telemetry clock reset boundary",
    "TIMING_INTEGRITY_BLOCKED": "Qualified SessionTick timing unavailable",
    "POSITION_DISCONTINUITY": "Track-position continuity failed",
    "SPARSE_POSITION_COVERAGE": "Track-position coverage was too sparse",
    "NON_CREDIBLE_LAP_SAMPLING": "Lap duration or sample density was not credible",
    "INCIDENT_COUNT_INCREASE": "Simulator incident count increased during the lap",
    "INVALID_FOR_PLATFORM_TUNING": "Invalid for platform tuning",
    "NO_SETUP_CONCLUSION": "Not valid for a setup conclusion",
}


def _qualified_timing_or_legacy_record(lap: LapSummary) -> bool:
    """Require explicit modern timing fields while keeping old stored rows readable.

    Current imports always persist both timing fields.  A pre-clock ``lap_json``
    has neither in Pydantic's explicit field set and remains readable for cache
    migration, but it cannot come from the current lap detector without the
    qualified-clock gate.
    """
    timing_fields = {"timing_primary_clock", "timing_clock_state"}
    if not (lap.model_fields_set & timing_fields):
        return True
    return (
        lap.timing_primary_clock == "session_tick"
        and lap.timing_clock_state == "qualified"
    )


def lap_ineligibility_reasons(lap: LapSummary) -> list[str]:
    """Return stable, user-facing reasons a lap cannot drive a setup decision."""
    reasons: list[str] = []
    if not lap.is_complete:
        reasons.append("Incomplete lap")
    if lap.lap_time is None or not math.isfinite(float(lap.lap_time)) or lap.lap_time <= 0:
        reasons.append("Valid lap time unavailable")
    if not _qualified_timing_or_legacy_record(lap):
        reasons.append("Qualified SessionTick timing unavailable")
    for tag in sorted({tag.upper() for tag in lap.classification_tags} & INVALID_TUNING_TAGS):
        reason = _TAG_REASONS[tag]
        if reason not in reasons:
            reasons.append(reason)
    if not lap.is_useful and not reasons:
        reasons.append("Lap did not pass the setup-evidence gate")
    return reasons


def lap_is_eligible(lap: LapSummary) -> bool:
    """Canonical setup/comparison eligibility gate used by every consumer."""
    return (
        lap.is_complete
        and lap.is_useful
        and lap.lap_time is not None
        and math.isfinite(float(lap.lap_time))
        and lap.lap_time > 0
        and _qualified_timing_or_legacy_record(lap)
        and not ({tag.upper() for tag in lap.classification_tags} & INVALID_TUNING_TAGS)
    )


def eligible_laps(laps: Iterable[LapSummary]) -> list[LapSummary]:
    return [lap for lap in laps if lap_is_eligible(lap)]


def longest_contiguous_eligible_lap_count(laps: Iterable[LapSummary]) -> int:
    """Return the longest consecutive eligible block without bridging gaps."""
    longest = 0
    current = 0
    previous_lap_number: int | None = None
    for lap in sorted(laps, key=lambda item: item.lap_number):
        if not lap_is_eligible(lap):
            current = 0
            previous_lap_number = None
            continue
        current = (
            current + 1
            if previous_lap_number is not None and lap.lap_number == previous_lap_number + 1
            else 1
        )
        longest = max(longest, current)
        previous_lap_number = lap.lap_number
    return longest


def find_lap(laps: Iterable[LapSummary], lap_number: int) -> LapSummary | None:
    return next((lap for lap in laps if lap.lap_number == lap_number), None)
