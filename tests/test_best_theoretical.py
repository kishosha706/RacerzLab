"""Tests for best theoretical lap calculation."""

from __future__ import annotations

from racelab_engine.analysis.best_theoretical import build_best_theoretical
from racelab_engine.models.segment import SegmentSummary


def _make_segment(
    pct_start: float,
    pct_end: float,
    speed: float,
    confidence: float = 0.8,
    lap_number: int = 2,
    run_id: str = "test_run",
) -> SegmentSummary:
    return SegmentSummary(
        segment_id=f"{run_id}:segment:{lap_number}:{int(pct_start)}-{int(pct_end)}",
        run_id=run_id,
        lap_number=lap_number,
        segment_name=f"{int(pct_start)}-{int(pct_end)}%",
        pct_start=pct_start,
        pct_end=pct_end,
        avg_speed_mph=speed,
        confidence_score=confidence,
    )


class TestBuildBestTheoretical:
    def _make_20_segments(self) -> dict[int, list[SegmentSummary]]:
        return {2: [_make_segment(s, s + 5, 180.0 + i * 0.5) for i, s in enumerate(range(0, 100, 5))]}

    def _assert_all_from_lap(self, result, lap_num: int) -> None:
        assert all(seg["lap_number"] == lap_num for seg in result.segments_used)

    def test_valid_segments_produce_theoretical_lap(self) -> None:
        result = build_best_theoretical(self._make_20_segments(), {2: ["SOLO_CLEAN"]}, {2: 51.0}, total_lap_distance_m=4268.56)
        assert result.is_available
        assert len(result.segments_used) == 20
        assert result.confidence_score > 0.9

    def test_tagged_lap_is_not_special_cased(self) -> None:
        segs: dict[int, list[SegmentSummary]] = {2: [_make_segment(0, 5, 180.0)], 3: [_make_segment(0, 5, 185.0)]}
        result = build_best_theoretical(segs, {2: ["SOLO_CLEAN"], 3: ["SOLO_CLEAN"]}, {2: 51.0, 3: 50.5})
        assert result.is_available
        self._assert_all_from_lap(result, 3)

    def test_invalid_laps_excluded(self) -> None:
        segs: dict[int, list[SegmentSummary]] = {1: [_make_segment(0, 5, 170.0, lap_number=1)], 2: [_make_segment(0, 5, 180.0, lap_number=2)]}
        result = build_best_theoretical(segs, {1: ["OUT_LAP"], 2: ["SOLO_CLEAN"]}, {1: None, 2: 51.0})
        assert result.is_available
        self._assert_all_from_lap(result, 2)

    def test_missing_segments_unavailable(self) -> None:
        result = build_best_theoretical({}, {}, {})
        assert not result.is_available

    def test_missing_eligibility_certificate_is_not_treated_as_valid(self) -> None:
        segments = {2: [_make_segment(0, 5, 180.0)]}

        result = build_best_theoretical(segments, {2: []}, {2: 51.0})

        assert result.is_available is False
        assert result.warnings == ["No valid laps available for theoretical best calculation."]

    def test_missing_lap_time_is_not_treated_as_valid(self) -> None:
        segments = {2: [_make_segment(0, 5, 180.0)]}

        result = build_best_theoretical(segments, {2: ["ELIGIBLE_FLYING_LAP"]}, {2: None})

        assert result.is_available is False

    def test_low_confidence_segments_excluded(self) -> None:
        segs: dict[int, list[SegmentSummary]] = {2: [_make_segment(0, 5, 180.0, confidence=0.1), _make_segment(5, 10, 181.0, confidence=0.9)]}
        result = build_best_theoretical(segs, {2: ["SOLO_CLEAN"]}, {2: 51.0})
        assert result.is_available
        assert len(result.segments_used) == 1
        assert result.segments_used[0]["bin"] == "5-10"

    def test_source_laps_recorded(self) -> None:
        segs: dict[int, list[SegmentSummary]] = {2: [_make_segment(0, 5, 180.0, lap_number=2)], 3: [_make_segment(5, 10, 182.0, lap_number=3)]}
        result = build_best_theoretical(segs, {2: ["SOLO_CLEAN"], 3: ["SOLO_CLEAN"]}, {2: 51.0, 3: 50.5})
        assert result.is_available
        lap_numbers = {s["lap_number"] for s in result.segments_used}
        assert 2 in lap_numbers
        assert 3 in lap_numbers

    def test_best_speed_per_bin_selected(self) -> None:
        segs: dict[int, list[SegmentSummary]] = {2: [_make_segment(0, 5, 180.0, lap_number=2)], 3: [_make_segment(0, 5, 185.0, lap_number=3)]}
        result = build_best_theoretical(segs, {2: ["SOLO_CLEAN"], 3: ["SOLO_CLEAN"]}, {2: 51.0, 3: 50.5})
        assert result.is_available
        assert len(result.segments_used) == 1
        assert result.segments_used[0]["lap_number"] == 3


def test_low_confidence_and_missing_speed_segments_are_excluded_without_fake_time() -> None:
    segments = {
        1: [
            SegmentSummary(
                segment_id="low-conf",
                run_id="run",
                lap_number=1,
                segment_name="0-5",
                pct_start=0.0,
                pct_end=5.0,
                avg_speed_mph=180.0,
                confidence_score=0.2,
            ),
            SegmentSummary(
                segment_id="missing-speed",
                run_id="run",
                lap_number=1,
                segment_name="5-10",
                pct_start=5.0,
                pct_end=10.0,
                avg_speed_mph=None,
                confidence_score=0.9,
            ),
        ]
    }

    result = build_best_theoretical(segments, {1: ["SOLO_CLEAN"]}, {1: 50.0}, total_lap_distance_m=1000.0)

    assert result.is_available is False
    assert result.best_theoretical_lap_time_s is None
    assert result.warnings == ["No valid segments found across available laps."]


