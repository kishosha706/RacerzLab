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
    def test_valid_segments_produce_theoretical_lap(self):
        """Valid segments across bins should produce a theoretical lap."""
        segments_by_lap: dict[int, list[SegmentSummary]] = {
            2: [_make_segment(s, s + 5, 180.0 + i * 0.5) for i, s in enumerate(range(0, 100, 5))],
        }
        tags = {2: ["SOLO_CLEAN"]}
        lap_times = {2: 51.0}
        result = build_best_theoretical(segments_by_lap, tags, lap_times, total_lap_distance_m=4268.56)
        assert result.is_available
        assert len(result.segments_used) == 20
        assert result.confidence_score > 0.9

    def test_draft_affected_excluded(self):
        """Draft-affected laps should be excluded."""
        segments_by_lap: dict[int, list[SegmentSummary]] = {
            2: [_make_segment(0, 5, 180.0)],
            3: [_make_segment(0, 5, 185.0)],
        }
        tags = {2: ["SOLO_CLEAN"], 3: ["DRAFT_AFFECTED"]}
        lap_times = {2: 51.0, 3: 50.5}
        result = build_best_theoretical(segments_by_lap, tags, lap_times)
        assert result.is_available
        # Only lap 2 segments should be used
        for seg in result.segments_used:
            assert seg["lap_number"] == 2

    def test_invalid_laps_excluded(self):
        """Out/invalid laps should be excluded."""
        segments_by_lap: dict[int, list[SegmentSummary]] = {
            1: [_make_segment(0, 5, 170.0, lap_number=1)],
            2: [_make_segment(0, 5, 180.0, lap_number=2)],
        }
        tags = {1: ["OUT_LAP"], 2: ["SOLO_CLEAN"]}
        lap_times = {1: None, 2: 51.0}
        result = build_best_theoretical(segments_by_lap, tags, lap_times)
        assert result.is_available
        for seg in result.segments_used:
            assert seg["lap_number"] == 2

    def test_missing_segments_unavailable(self):
        """No segments should return unavailable."""
        result = build_best_theoretical({}, {}, {})
        assert not result.is_available

    def test_low_confidence_segments_excluded(self):
        """Segments with low confidence should be excluded."""
        segments_by_lap: dict[int, list[SegmentSummary]] = {
            2: [
                _make_segment(0, 5, 180.0, confidence=0.1),
                _make_segment(5, 10, 181.0, confidence=0.9),
            ],
        }
        tags = {2: ["SOLO_CLEAN"]}
        lap_times = {2: 51.0}
        result = build_best_theoretical(segments_by_lap, tags, lap_times)
        assert result.is_available
        assert len(result.segments_used) == 1  # Only the high-confidence segment
        assert result.segments_used[0]["bin"] == "5-10"

    def test_source_laps_recorded(self):
        """Source lap numbers should be recorded in segments_used."""
        segments_by_lap: dict[int, list[SegmentSummary]] = {
            2: [_make_segment(0, 5, 180.0, lap_number=2)],
            3: [_make_segment(5, 10, 182.0, lap_number=3)],
        }
        tags = {2: ["SOLO_CLEAN"], 3: ["SOLO_CLEAN"]}
        lap_times = {2: 51.0, 3: 50.5}
        result = build_best_theoretical(segments_by_lap, tags, lap_times)
        assert result.is_available
        lap_numbers = {s["lap_number"] for s in result.segments_used}
        assert 2 in lap_numbers
        assert 3 in lap_numbers

    def test_best_speed_per_bin_selected(self):
        """When multiple laps have the same bin, the fastest should be used."""
        segments_by_lap: dict[int, list[SegmentSummary]] = {
            2: [_make_segment(0, 5, 180.0, lap_number=2)],
            3: [_make_segment(0, 5, 185.0, lap_number=3)],  # Faster in same bin
        }
        tags = {2: ["SOLO_CLEAN"], 3: ["SOLO_CLEAN"]}
        lap_times = {2: 51.0, 3: 50.5}
        result = build_best_theoretical(segments_by_lap, tags, lap_times)
        assert result.is_available
        assert len(result.segments_used) == 1
        assert result.segments_used[0]["lap_number"] == 3  # Faster lap
