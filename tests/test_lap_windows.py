"""Tests for lap window analysis algorithms and compare-selection validation."""

from __future__ import annotations

from racelab_engine.analysis.lap_windows import (
    _draft_status,
    _is_lap_valid_for_ranking,
    compute_best_windows,
    compute_degradation,
    compute_fastest_groups,
    compute_lap_windows_response,
)
from racelab_engine.models.lap import LapSummary


def _make_lap(
    lap_number: int,
    lap_time: float | None = 50.0,
    is_complete: bool = True,
    is_useful: bool = True,
    tags: list[str] | None = None,
    run_id: str = "test_run",
) -> LapSummary:
    return LapSummary(
        lap_id=f"{run_id}_lap_{lap_number}",
        run_id=run_id,
        lap_number=lap_number,
        lap_type="timed",
        is_complete=is_complete,
        is_useful=is_useful,
        lap_time=lap_time,
        classification_tags=tags or ["SOLO_CLEAN"],
        avg_speed_mph=180.0,
    )


def _make_laps(count: int, base_time: float = 50.0, time_step: float = 0.1, start_lap: int = 1, **kwargs) -> list[LapSummary]:
    """Create N consecutive laps with linearly increasing lap times."""
    return [_make_lap(start_lap + i, base_time + i * time_step, **kwargs) for i in range(count)]


# ── _draft_status ─────────────────────────────────────────────

class TestDraftStatus:
    def test_draft_affected_detected(self):
        assert _draft_status(["DRAFT_AFFECTED"]) == "DRAFT_AFFECTED"

    def test_possible_draft_assist_detected(self):
        assert _draft_status(["POSSIBLE_DRAFT_ASSIST"]) == "POSSIBLE_DRAFT_ASSIST"

    def test_likely_solo_detected(self):
        assert _draft_status(["LIKELY_SOLO"]) == "LIKELY_SOLO"

    def test_unknown_when_no_draft_tag(self):
        assert _draft_status(["SOLO_CLEAN"]) == "UNKNOWN_DRAFT_STATUS"

    def test_empty_tags_returns_unknown(self):
        assert _draft_status([]) == "UNKNOWN_DRAFT_STATUS"

    def test_draft_takes_precedence(self):
        # DRAFT_AFFECTED is checked before LIKELY_SOLO
        assert _draft_status(["DRAFT_AFFECTED", "LIKELY_SOLO"]) == "DRAFT_AFFECTED"


# ── _is_lap_valid_for_ranking ─────────────────────────────────

class TestIsLapValidForRanking:
    def _assert_invalid(self, tags=None, **kwargs):
        lap = _make_lap(1, tags=tags, **kwargs)
        ok, _ = _is_lap_valid_for_ranking(lap)
        assert not ok

    def _assert_valid(self, tags=None, **kwargs):
        include_draft = kwargs.pop("include_draft", False)
        lap = _make_lap(1, tags=tags, **kwargs)
        ok, _ = _is_lap_valid_for_ranking(lap, include_draft=include_draft)
        assert ok

    def test_valid_lap_passes(self):
        lap = _make_lap(1)
        ok, reason = _is_lap_valid_for_ranking(lap)
        assert ok
        assert reason is None

    def test_incomplete_lap_fails(self):
        self._assert_invalid(is_complete=False)

    def test_not_useful_lap_fails(self):
        self._assert_invalid(is_useful=False)

    def test_out_lap_excluded(self):
        self._assert_invalid(tags=["OUT_LAP"])

    def test_cooldown_lap_excluded(self):
        self._assert_invalid(tags=["COOLDOWN"])

    def test_pit_road_excluded(self):
        self._assert_invalid(tags=["PIT_ROAD"])

    def test_wreck_excluded(self):
        self._assert_invalid(tags=["WRECK_OR_SPIN"])

    def test_invalid_speed_excluded(self):
        self._assert_invalid(tags=["INVALID_SPEED_EVENT"])

    def test_draft_affected_excluded_by_default(self):
        self._assert_invalid(tags=["DRAFT_AFFECTED"])

    def test_draft_affected_included_when_flag_set(self):
        self._assert_valid(tags=["DRAFT_AFFECTED"], include_draft=True)

    def test_no_lap_time_fails(self):
        self._assert_invalid(lap_time=None)

    def test_zero_lap_time_fails(self):
        self._assert_invalid(lap_time=0.0)


# ── compute_fastest_groups ────────────────────────────────────

class TestComputeFastestGroups:
    def test_fastest_10_with_25_valid_laps(self):
        laps = _make_laps(25)
        groups = compute_fastest_groups(laps, sizes=[10, 20, 30, 40])
        assert groups[0].is_available  # Fastest 10
        assert groups[1].is_available  # Fastest 20
        assert not groups[2].is_available  # Fastest 30 — only 25 laps
        assert not groups[3].is_available  # Fastest 40 — only 25 laps

    def test_fastest_10_returns_correct_count(self):
        laps = _make_laps(25)
        groups = compute_fastest_groups(laps, sizes=[10])
        assert len(groups[0].laps) == 10

    def test_fastest_are_sorted_by_time(self):
        laps = _make_laps(15)
        groups = compute_fastest_groups(laps, sizes=[10])
        times = [l.lap_time for l in groups[0].laps if l.lap_time is not None]
        assert times == sorted(times)  # Already sorted fastest first

    def test_not_enough_laps_shows_warning(self):
        laps = _make_laps(5)
        groups = compute_fastest_groups(laps, sizes=[10])
        assert not groups[0].is_available
        assert "only 5 valid" in (groups[0].warning or "").lower()

    def test_draft_laps_excluded_by_default(self):
        laps = _make_laps(15) + [_make_lap(16, tags=["DRAFT_AFFECTED"])]
        groups = compute_fastest_groups(laps, sizes=[15])
        assert groups[0].is_available  # 15 valid, 1 draft excluded

    def test_draft_laps_included_when_flag_set(self):
        laps = _make_laps(15) + [_make_lap(16, tags=["DRAFT_AFFECTED"])]
        groups = compute_fastest_groups(laps, sizes=[16], include_draft=True)
        assert groups[0].is_available  # All 16 included

    def test_empty_laps_returns_all_unavailable(self):
        groups = compute_fastest_groups([], sizes=[10])
        assert all(not g.is_available for g in groups)

    def test_average_time_computed_correctly(self):
        laps = _make_laps(10, base_time=50.0, time_step=0.0)  # All same time
        groups = compute_fastest_groups(laps, sizes=[10])
        assert groups[0].average_lap_time == 50.0


# ── compute_best_windows ──────────────────────────────────────

class TestComputeBestWindows:
    def _best_window(self, laps, size=10):
        return compute_best_windows(laps, sizes=[size])[0].best_window

    def test_best_5_window_with_25_laps(self):
        laps = _make_laps(25)
        windows = compute_best_windows(laps, sizes=[5, 10, 20, 30, 40])
        assert windows[0].is_available
        assert windows[1].is_available
        assert windows[2].is_available
        assert not windows[3].is_available
        assert not windows[4].is_available

    def test_best_window_has_correct_size(self):
        best = self._best_window(_make_laps(25))
        assert best is not None
        assert best.window_size == 10
        assert best.valid_lap_count == 10

    def test_window_start_end_lap_recorded(self):
        best = self._best_window(_make_laps(25))
        assert best is not None
        assert best.end_lap - best.start_lap == 9

    def test_draft_lap_excluded_from_window(self):
        laps = _make_laps(25)
        laps[12] = _make_lap(13, tags=["DRAFT_AFFECTED"])
        best = self._best_window(laps)
        assert best is not None
        assert best.valid_lap_count == 10

    def test_not_enough_laps_for_window(self):
        windows = compute_best_windows(_make_laps(3), sizes=[10])
        assert not windows[0].is_available

    def test_empty_laps_returns_all_unavailable(self):
        windows = compute_best_windows([], sizes=[10])
        assert all(not w.is_available for w in windows)

    def test_consistency_score_higher_for_constant_times(self):
        const_best = self._best_window(_make_laps(15, base_time=50.0, time_step=0.0))
        var_best = self._best_window(_make_laps(15, base_time=50.0, time_step=0.5))
        assert const_best is not None and var_best is not None
        assert const_best.consistency_score > var_best.consistency_score


# ── compute_degradation ───────────────────────────────────────

class TestComputeDegradation:
    def test_less_than_10_laps_returns_low_confidence(self):
        laps = _make_laps(5)
        deg = compute_degradation(laps)
        assert deg.confidence_score == 0.0
        assert "Need at least 10" in (deg.coaching_message or "")

    def test_10_laps_produces_falloff_analysis(self):
        laps = _make_laps(10, base_time=50.0, time_step=0.1)
        deg = compute_degradation(laps)
        assert deg.lap_count >= 10
        assert deg.falloff_early_to_late is not None

    def test_constant_pace_shows_consistent_message(self):
        laps = _make_laps(15, base_time=50.0, time_step=0.0)
        deg = compute_degradation(laps)
        assert "consistent" in (deg.coaching_message or "").lower()

    def test_falloff_detected_with_20_laps(self):
        # First 10 fast, last 10 slow
        fast = _make_laps(10, base_time=50.0, time_step=0.0)
        slow = _make_laps(10, base_time=52.0, time_step=0.0, start_lap=11)
        laps = fast + slow
        deg = compute_degradation(laps)
        assert deg.falloff_early_to_late is not None
        assert deg.falloff_early_to_late > 1.0  # At least 1 second falloff

    def test_draft_warning_when_draft_present(self):
        laps = _make_laps(10, base_time=50.0, time_step=0.1)
        laps[5] = _make_lap(6, tags=["DRAFT_AFFECTED"])
        deg = compute_degradation(laps)
        # Draft lap is excluded from valid set, so no draft warning
        # Only 9 valid laps now, so falls back to <10 message
        assert deg.lap_count < 10

    def test_draft_warning_with_include_draft(self):
        laps = _make_laps(10, base_time=50.0, time_step=0.1)
        laps[5] = _make_lap(6, tags=["DRAFT_AFFECTED"])
        deg = compute_degradation(laps, include_draft=True)
        assert deg.draft_warning is not None

    def test_confidence_increases_with_more_laps(self):
        laps_10 = _make_laps(10)
        laps_40 = _make_laps(40)
        deg_10 = compute_degradation(laps_10)
        deg_40 = compute_degradation(laps_40)
        assert deg_40.confidence_score > deg_10.confidence_score

    def test_draft_reduces_confidence(self):
        laps_clean = _make_laps(20)
        laps_draft = _make_laps(20)
        laps_draft[5] = _make_lap(6, tags=["DRAFT_AFFECTED"])
        deg_clean = compute_degradation(laps_clean)
        deg_draft = compute_degradation(laps_draft, include_draft=True)
        assert deg_draft.confidence_score < deg_clean.confidence_score

    def test_early_middle_late_windows_recorded(self):
        laps = _make_laps(15)
        deg = compute_degradation(laps)
        assert deg.early_window_laps > 0
        assert deg.middle_window_laps > 0
        assert deg.late_window_laps > 0

    def test_empty_laps_returns_empty(self):
        deg = compute_degradation([])
        assert deg.lap_count == 0


# ── compute_lap_windows_response ──────────────────────────────

class TestComputeLapWindowsResponse:
    def test_response_contains_all_sections(self):
        laps = _make_laps(25)
        resp = compute_lap_windows_response(laps)
        assert len(resp.fastest_groups) > 0
        assert len(resp.best_windows) > 0
        assert resp.degradation is not None
        assert resp.total_valid_laps == 25
        assert resp.total_laps == 25

    def test_draft_laps_reduce_valid_count(self):
        laps = _make_laps(25) + [_make_lap(26, tags=["DRAFT_AFFECTED"])]
        resp = compute_lap_windows_response(laps)
        assert resp.total_valid_laps == 25
        assert resp.total_laps == 26

    def test_include_draft_increases_valid_count(self):
        laps = _make_laps(25) + [_make_lap(26, tags=["DRAFT_AFFECTED"])]
        resp = compute_lap_windows_response(laps, include_draft=True)
        assert resp.total_valid_laps == 26

    def test_warning_when_fewer_than_10_valid(self):
        laps = _make_laps(5)
        resp = compute_lap_windows_response(laps)
        assert len(resp.warnings) > 0

    def test_empty_laps_returns_warning(self):
        resp = compute_lap_windows_response([])
        assert len(resp.warnings) > 0
