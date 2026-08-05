from __future__ import annotations

from racelab_engine.analysis.active_reset_lab import analyze_active_reset_lab


def _attempt(start_time: float, duration: float, *, reset: bool) -> list[dict]:
    rows = []
    for index in range(21):
        pct = 20.0 + index
        rows.append({
            "lap_dist_pct_100": pct,
            "session_time": start_time + duration * index / 20.0,
            "enter_exit_reset_state": 2 if reset and index == 0 else 0,
            "reset_discontinuity": reset and index == 0,
            "on_pit_road": False,
            "speed_mps": 50.0,
            "car_distance_ahead_m": 500_000.0,
            "car_distance_behind_m": 500_000.0,
            "is_on_track": True,
            "player_incident_count": 0,
            "session_flags": 0,
        })
    return rows


def test_active_reset_lab_scores_three_section_attempts_without_promoting_laps() -> None:
    rows = [
        *_attempt(0.0, 10.00, reset=False),
        *_attempt(20.0, 10.01, reset=True),
        *_attempt(40.0, 9.99, reset=True),
    ]
    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert result.eligible_attempt_count == 3
    assert result.repeatable is True
    assert result.repeatability_score is not None and result.repeatability_score >= 0.8
    assert result.full_lap_eligible is False


def test_active_reset_lab_fails_closed_on_incomplete_attempts() -> None:
    rows = _attempt(0.0, 10.0, reset=False) + [
        {"lap_dist_pct_100": 20.0, "session_time": 20.0, "enter_exit_reset_state": 2, "reset_discontinuity": True}
    ]
    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert result.repeatable is False
    assert result.eligible_attempt_count == 1
    assert "At least three" in " ".join(result.blockers)


def test_active_reset_lab_rejects_reversed_time_and_sticky_reset_flags() -> None:
    rows = _attempt(0.0, 10.0, reset=False)
    sticky = _attempt(20.0, 10.0, reset=True)
    for row in sticky:
        row["reset_discontinuity"] = True
        row["enter_exit_reset_state"] = 2
    rows.extend(sticky)
    rows.extend(_attempt(15.0, 10.0, reset=True))

    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert len(result.attempts) == 2
    assert result.eligible_attempt_count == 0
    assert result.repeatable is False
    assert "non-monotonic" in " ".join(result.blockers)


def test_active_reset_lab_rejects_off_track_or_incident_attempts() -> None:
    rows = [
        *_attempt(0.0, 10.0, reset=False),
        *_attempt(20.0, 10.0, reset=True),
        *_attempt(40.0, 10.0, reset=True),
    ]
    for row in rows:
        if 22.0 <= row["lap_dist_pct_100"] <= 38.0:
            row["is_on_track"] = False
    rows[10]["player_incident_count"] = 1

    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert result.eligible_attempt_count == 0
    assert result.repeatable is False
    assert all(any("off track" in blocker for blocker in attempt.blocker_reasons) for attempt in result.attempts)


def test_active_reset_lab_rejects_incident_increment_in_preroll_before_target() -> None:
    rows = [
        *_attempt(0.0, 10.0, reset=False),
        *_attempt(20.0, 10.0, reset=True),
        *_attempt(40.0, 10.0, reset=True),
    ]
    for attempt_start in (0, 21, 42):
        rows[attempt_start]["player_incident_count"] = 0
        for row in rows[attempt_start + 1:attempt_start + 21]:
            row["player_incident_count"] = 1

    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert result.eligible_attempt_count == 0
    assert result.repeatable is False
    assert all(
        any("Incident count increased" in blocker for blocker in attempt.blocker_reasons)
        for attempt in result.attempts
    )


def test_active_reset_lab_fails_closed_without_incident_counter_coverage() -> None:
    rows = [
        *_attempt(0.0, 10.0, reset=False),
        *_attempt(20.0, 10.0, reset=True),
        *_attempt(40.0, 10.0, reset=True),
    ]
    for row in rows:
        row.pop("player_incident_count")
        row.pop("incident", None)

    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert result.eligible_attempt_count == 0
    assert result.repeatable is False
    assert result.evidence_state.value == "needs_confirmation"
    assert all(
        any("authoritative incident counter" in blocker for blocker in attempt.blocker_reasons)
        for attempt in result.attempts
    )


def test_active_reset_lab_rejects_raw_session_flag_caution_mask() -> None:
    rows = [
        *_attempt(0.0, 10.0, reset=False),
        *_attempt(20.0, 10.0, reset=True),
        *_attempt(40.0, 10.0, reset=True),
    ]
    for row in rows:
        row["session_flags"] = 0x4000

    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert result.eligible_attempt_count == 0
    assert result.repeatable is False
    assert all(
        any("CAUTION" in blocker for blocker in attempt.blocker_reasons)
        for attempt in result.attempts
    )


def test_active_reset_lab_fails_closed_without_pit_or_caution_coverage() -> None:
    rows = [
        *_attempt(0.0, 10.0, reset=False),
        *_attempt(20.0, 10.0, reset=True),
        *_attempt(40.0, 10.0, reset=True),
    ]
    for row in rows:
        row.pop("on_pit_road")
        row.pop("session_flags")

    result = analyze_active_reset_lab(rows, target_start_pct=22.0, target_end_pct=38.0)

    assert result.eligible_attempt_count == 0
    assert result.repeatable is False
    blockers = " ".join(blocker for attempt in result.attempts for blocker in attempt.blocker_reasons)
    assert "Pit-road or track-surface state is unavailable" in blockers
    assert "Caution or pacing state is unavailable" in blockers
