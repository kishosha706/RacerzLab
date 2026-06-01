"""
Best theoretical lap from valid 5% segment bins.

Uses persisted segments to find the fastest valid segment per bin,
then assembles a theoretical best lap from those segments.

Rules:
- Only complete useful laps
- Only segments with valid confidence
- Exclude cooldown/out/invalid laps
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from racelab_engine.models.segment import SegmentSummary


@dataclass
class BestTheoreticalResult:
    best_theoretical_lap_time_s: float | None = None
    segments_used: list[dict[str, Any]] = field(default_factory=list)
    excluded_laps: list[dict[str, Any]] = field(default_factory=list)
    excluded_segments: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    is_available: bool = False
    warnings: list[str] = field(default_factory=list)


def _is_lap_valid(classification_tags: list[str]) -> tuple[bool, str | None]:
    """Check if a lap is valid for theoretical best calculation."""
    tags = [t.upper() for t in classification_tags]
    if "OUT_LAP" in tags:
        return False, "Out lap"
    if "COOLDOWN" in tags:
        return False, "Cooldown lap"
    if "PIT_ROAD" in tags:
        return False, "Pit road"
    if "WRECK_OR_SPIN" in tags:
        return False, "Wreck or spin"
    if "INVALID_SPEED_EVENT" in tags:
        return False, "Invalid speed event"
    return True, None


def _segment_key(pct_start: float) -> str:
    """Return a bin key for a lap percentage (e.g., '0-5', '5-10')."""
    bin_start = int(pct_start // 5) * 5
    return f"{bin_start}-{bin_start + 5}"


def build_best_theoretical(
    segments_by_lap: dict[int, list[SegmentSummary]],
    lap_classification_tags: dict[int, list[str]],
    lap_times: dict[int, float | None],
    total_lap_distance_m: float | None = None,
) -> BestTheoreticalResult:
    """
    Build a best theoretical lap from valid segment bins.

    Args:
        segments_by_lap: Map of lap_number -> list of SegmentSummary.
        lap_classification_tags: Map of lap_number -> classification tags.
        lap_times: Map of lap_number -> lap time in seconds.
        total_lap_distance_m: Optional total lap distance for context.

    Returns:
        BestTheoreticalResult with best lap time, segments used, exclusions.
    """
    if not segments_by_lap:
        return BestTheoreticalResult(
            is_available=False,
            warnings=["No segment data available."],
        )

    # ── Collect valid laps ─────────────────────────────────────
    valid_laps: set[int] = set()
    for lap_num, tags in lap_classification_tags.items():
        valid, reason = _is_lap_valid(tags)
        if valid and lap_num in segments_by_lap:
            valid_laps.add(lap_num)

    if not valid_laps:
        return BestTheoreticalResult(
            is_available=False,
            warnings=["No valid laps available for theoretical best calculation."],
        )

    # ── Find best segment per 5% bin ───────────────────────────
    best_per_bin: dict[str, tuple[SegmentSummary, int]] = {}  # bin_key -> (segment, lap_number)
    excluded_segments_list: list[dict[str, Any]] = []

    for lap_num in valid_laps:
        segments = segments_by_lap.get(lap_num, [])
        for seg in segments:
            if seg.confidence_score is None or seg.confidence_score < 0.3:
                excluded_segments_list.append({
                    "segment_id": seg.segment_id,
                    "lap_number": lap_num,
                    "reason": f"Low confidence ({seg.confidence_score})",
                })
                continue
            if seg.avg_speed_mph is None:
                excluded_segments_list.append({
                    "segment_id": seg.segment_id,
                    "lap_number": lap_num,
                    "reason": "No speed data",
                })
                continue

            key = _segment_key(seg.pct_start)
            existing = best_per_bin.get(key)
            if existing is None or (existing[0].avg_speed_mph is not None and seg.avg_speed_mph > existing[0].avg_speed_mph):
                best_per_bin[key] = (seg, lap_num)

    if not best_per_bin:
        return BestTheoreticalResult(
            is_available=False,
            warnings=["No valid segments found across available laps."],
        )

    # ── Assemble theoretical lap ───────────────────────────────
    segments_used: list[dict[str, Any]] = []
    total_speed_sum = 0.0
    total_segments = 0

    for key in sorted(best_per_bin.keys(), key=lambda k: int(k.split("-")[0])):
        seg, lap_num = best_per_bin[key]
        segments_used.append({
            "bin": key,
            "segment_id": seg.segment_id,
            "lap_number": lap_num,
            "avg_speed_mph": seg.avg_speed_mph,
            "pct_start": seg.pct_start,
            "pct_end": seg.pct_end,
        })
        if seg.avg_speed_mph is not None:
            total_speed_sum += seg.avg_speed_mph
            total_segments += 1

    # ── Estimate theoretical lap time ──────────────────────────
    # If we have lap distance, compute time from avg speed per segment
    best_theoretical_time: float | None = None
    if total_segments > 0 and total_lap_distance_m is not None and total_lap_distance_m > 0:
        avg_speed_mps = (total_speed_sum / total_segments) * 0.44704  # mph -> m/s
        if avg_speed_mps > 0:
            best_theoretical_time = total_lap_distance_m / avg_speed_mps

    # Confidence: ratio of bins filled vs total possible (20 bins for 0-100%)
    total_possible_bins = 20
    bins_filled = len(best_per_bin)
    confidence = min(1.0, bins_filled / total_possible_bins)

    warnings: list[str] = []
    if bins_filled < total_possible_bins:
        warnings.append(f"Only {bins_filled} of {total_possible_bins} segment bins had valid data.")

    return BestTheoreticalResult(
        best_theoretical_lap_time_s=best_theoretical_time,
        segments_used=segments_used,
        excluded_laps=[{"lap_number": ln, "reason": r} for ln, r in
                       [(ln, _is_lap_valid(lap_classification_tags.get(ln, []))[1])
                        for ln in segments_by_lap if ln not in valid_laps]
                       if r is not None],
        excluded_segments=excluded_segments_list,
        confidence_score=confidence,
        is_available=True,
        warnings=warnings,
    )
