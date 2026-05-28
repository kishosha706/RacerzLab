"""
Draft / solo classification for iRacing telemetry.

Outputs:
  LIKELY_SOLO          — Speed profile consistent with solo running
  POSSIBLE_DRAFT_ASSIST — Speed gain without matching RPM/acceleration
  DRAFT_AFFECTED       — Strong draft signature detected
  UNKNOWN_DRAFT_STATUS — Insufficient signals to classify

Signals considered:
  - Speed increase without matching RPM increase (straightaway)
  - Speed gain at same throttle position
  - Segment speed jump inconsistent with previous baseline
  - Sustained high speed delta without setup explanation
  - Unusual closing rate (if relative data available)

Do not overclaim. Use confidence and warning flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DraftStatus(str, Enum):
    LIKELY_SOLO = "LIKELY_SOLO"
    POSSIBLE_DRAFT_ASSIST = "POSSIBLE_DRAFT_ASSIST"
    DRAFT_AFFECTED = "DRAFT_AFFECTED"
    UNKNOWN_DRAFT_STATUS = "UNKNOWN_DRAFT_STATUS"


@dataclass
class DraftResult:
    status: DraftStatus
    confidence: float  # 0.0–1.0
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Thresholds ────────────────────────────────────────────────
# Speed gain (mph) on a straight at same throttle that suggests draft
DRAFT_SPEED_GAIN_THRESHOLD = 1.5  # mph
# RPM difference threshold — draft gain typically doesn't increase RPM proportionally
DRAFT_RPM_DIFF_RATIO = 0.3  # RPM gain / speed gain ratio below this suggests draft
# Minimum straightaway speed for draft to be relevant
MIN_DRAFT_SPEED_MPH = 150.0
# Segment speed jump threshold
SEGMENT_SPEED_JUMP_MPH = 2.0
# Throttle must be near full for draft suspicion
DRAFT_THROTTLE_MIN = 95.0  # percent


def classify_draft_status(
    rows: list[dict[str, Any]],
    lap_number: int | None = None,
) -> DraftResult:
    """
    Classify draft status for a lap or full run.

    Args:
        rows: Normalized telemetry rows (from normalize_telemetry_rows).
        lap_number: If set, filter to this lap only.

    Returns:
        DraftResult with status, confidence, signals, and warnings.
    """
    if not rows:
        return DraftResult(
            status=DraftStatus.UNKNOWN_DRAFT_STATUS,
            confidence=0.0,
            signals=["No telemetry data available."],
            warnings=["Cannot determine draft status without telemetry."],
        )

    if lap_number is not None:
        rows = [row for row in rows if int(row.get("lap") or row.get("lap_number") or -1) == lap_number]
    if not rows:
        return DraftResult(
            status=DraftStatus.UNKNOWN_DRAFT_STATUS,
            confidence=0.0,
            signals=["No rows for the specified lap."],
        )

    signals: list[str] = []
    warnings: list[str] = []

    # ── Signal 1: Speed/RPM ratio check ──────────────────────
    # On straightaways, draft-assisted speed gain shows higher speed at same RPM
    straight_segments = _find_straight_segments(rows)
    speed_rpm_anomalies = 0
    total_straight_samples = 0

    for seg_start, seg_end in straight_segments:
        seg_rows = rows[seg_start:seg_end]
        if len(seg_rows) < 3:
            continue
        total_straight_samples += len(seg_rows)

        # Check for speed increase without proportional RPM increase
        for i in range(1, len(seg_rows)):
            prev = seg_rows[i - 1]
            curr = seg_rows[i]
            speed_prev = _numeric(prev.get("speed_mph"))
            speed_curr = _numeric(curr.get("speed_mph"))
            rpm_prev = _numeric(prev.get("rpm"))
            rpm_curr = _numeric(curr.get("rpm"))
            throttle = _numeric(curr.get("throttle_pct"))

            if speed_prev is None or speed_curr is None or rpm_prev is None or rpm_curr is None or throttle is None:
                continue
            if throttle < DRAFT_THROTTLE_MIN:
                continue
            if speed_curr < MIN_DRAFT_SPEED_MPH:
                continue

            speed_delta = speed_curr - speed_prev
            rpm_delta = rpm_curr - rpm_prev

            # Speed gain without proportional RPM gain
            if speed_delta > DRAFT_SPEED_GAIN_THRESHOLD:
                if rpm_delta / speed_delta < DRAFT_RPM_DIFF_RATIO:
                    speed_rpm_anomalies += 1

    # ── Signal 2: Segment speed jump ─────────────────────────
    segment_speed_jumps = 0
    seg_size = max(1, len(rows) // 20)  # ~5% segments
    for i in range(seg_size, len(rows) - seg_size, seg_size):
        before_avg = _mean_of([_numeric(r.get("speed_mph")) for r in rows[i - seg_size:i]])
        after_avg = _mean_of([_numeric(r.get("speed_mph")) for r in rows[i:min(i + seg_size, len(rows))]])
        if before_avg is None or after_avg is None:
            continue
        jump = after_avg - before_avg
        if jump > SEGMENT_SPEED_JUMP_MPH:
            # Check throttle stayed high
            throttle_after = _mean_of([_numeric(r.get("throttle_pct")) for r in rows[i:min(i + seg_size, len(rows))]])
            if throttle_after is not None and throttle_after > DRAFT_THROTTLE_MIN:
                segment_speed_jumps += 1

    # ── Signal 3: Speed variation at high speed ──────────────
    high_speed_rows = [r for r in rows if (_numeric(r.get("speed_mph")) or 0) > MIN_DRAFT_SPEED_MPH]
    if high_speed_rows:
        speeds = [_numeric(r.get("speed_mph")) for r in high_speed_rows]
        if speeds_clean := [s for s in speeds if s is not None]:
            speed_range = max(speeds_clean) - min(speeds_clean)
            # High speed variation at full throttle can indicate draft
            full_throttle_high_speed = [
                r for r in high_speed_rows
                if (_numeric(r.get("throttle_pct")) or 0) > DRAFT_THROTTLE_MIN
            ]
            ft_speeds = [_numeric(r.get("speed_mph")) for r in full_throttle_high_speed]
            if (ft_speeds_clean := [s for s in ft_speeds if s is not None]) and len(ft_speeds_clean) > 10:
                ft_range = max(ft_speeds_clean) - min(ft_speeds_clean)
                if ft_range > DRAFT_SPEED_GAIN_THRESHOLD * 2:
                    signals.append(
                        f"Speed range at full throttle above {MIN_DRAFT_SPEED_MPH:.0f} mph: "
                        f"{ft_range:.1f} mph (suggests draft variation)"
                    )

    # ── Classify ─────────────────────────────────────────────
    if speed_rpm_anomalies > 0:
        signals.append(
            f"{speed_rpm_anomalies} straightaway sample(s) with speed gain "
            f"without proportional RPM increase"
        )

    if segment_speed_jumps > 0:
        signals.append(
            f"{segment_speed_jumps} segment speed jump(s) at full throttle"
        )

    # Weighted scoring
    draft_score = 0.0
    if total_straight_samples > 0:
        draft_score += min(1.0, speed_rpm_anomalies / max(1, total_straight_samples) * 3)
    draft_score += min(1.0, segment_speed_jumps * 0.25)

    if draft_score >= 0.6:
        status = DraftStatus.DRAFT_AFFECTED
        confidence = min(1.0, draft_score)
        warnings.append("Draft detected — speed data may not reflect solo setup performance.")
    elif draft_score >= 0.25:
        status = DraftStatus.POSSIBLE_DRAFT_ASSIST
        confidence = draft_score
        warnings.append("Possible draft assist — verify with a known solo lap.")
    elif draft_score < 0.1 and total_straight_samples > 50:
        status = DraftStatus.LIKELY_SOLO
        confidence = 0.8
        signals.append("Speed/RPM profile consistent with solo running.")
    else:
        status = DraftStatus.UNKNOWN_DRAFT_STATUS
        confidence = 0.0
        if total_straight_samples <= 50:
            warnings.append("Insufficient straightaway data for draft classification.")

    return DraftResult(
        status=status,
        confidence=confidence,
        signals=signals,
        warnings=warnings,
    )


def _find_straight_segments(rows: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Find straightaway segments where steering is near center."""
    segments: list[tuple[int, int]] = []
    in_straight = False
    start = 0
    min_straight_samples = 5

    for i, row in enumerate(rows):
        steering = abs(_numeric(row.get("abs_steering_deg")) or _numeric(row.get("steering_deg")) or 0)
        is_straight = steering < 2.0  # degrees

        if is_straight and not in_straight:
            start = i
            in_straight = True
        elif not is_straight and in_straight:
            if i - start >= min_straight_samples:
                segments.append((start, i))
            in_straight = False

    if in_straight and len(rows) - start >= min_straight_samples:
        segments.append((start, len(rows)))

    return segments


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        return None if (v != v or v == float("inf") or v == float("-inf")) else v
    except (TypeError, ValueError):
        return None


def _mean_of(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None
