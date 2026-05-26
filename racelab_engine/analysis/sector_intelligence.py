from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from racelab_engine.analysis.comparison import build_lap_grid, interpolate_run_to_grid


SECTOR_BOUNDARIES = [
    (0.0, 33.33, "Sector 1"),
    (33.33, 66.67, "Sector 2"),
    (66.67, 100.0, "Sector 3"),
]


@dataclass(frozen=True)
class SectorDelta:
    sector_name: str
    start_pct: float
    end_pct: float
    avg_speed_delta: float | None = None
    min_cfs_delta: float | None = None
    avg_steering_delta: float | None = None
    avg_drag_delta: float | None = None
    avg_rpm_delta: float | None = None
    speed_direction: str = "unchanged"
    platform_risk_direction: str = "unchanged"


@dataclass(frozen=True)
class SectorIntelligenceResult:
    sectors: list[SectorDelta] = field(default_factory=list)
    summary: str | None = None


def compute_sector_deltas(
    baseline_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    channels: list[str] | None = None,
) -> SectorIntelligenceResult:
    """Compute per-sector delta summaries for the full lap."""
    selected = channels or [
        "speed_mph", "cfs_ride_height_in", "abs_steering_deg",
        "drag_scrub_suspicion", "rpm",
    ]

    sectors: list[SectorDelta] = []
    for start_pct, end_pct, name in SECTOR_BOUNDARIES:
        grid = build_lap_grid(start_pct, end_pct, 0.5)
        bl_grid = interpolate_run_to_grid(baseline_rows, selected, grid)
        t_grid = interpolate_run_to_grid(test_rows, selected, grid)

        def _avg(ch: str) -> float | None:
            bl = [v for v in (bl_grid.get(ch) or []) if v is not None]
            t = [v for v in (t_grid.get(ch) or []) if v is not None]
            return (sum(t) / len(t)) - (sum(bl) / len(bl)) if bl and t else None

        def _min(ch: str) -> float | None:
            t = [v for v in (t_grid.get(ch) or []) if v is not None]
            bl = [v for v in (bl_grid.get(ch) or []) if v is not None]
            return min(t) - min(bl) if t and bl else None

        avg_speed = _avg("speed_mph")
        min_cfs = _min("cfs_ride_height_in")
        avg_steer = _avg("abs_steering_deg")
        avg_drag = _avg("drag_scrub_suspicion")
        avg_rpm = _avg("rpm")

        speed_dir = "gained" if avg_speed and avg_speed > 0.05 else "lost" if avg_speed and avg_speed < -0.05 else "unchanged"
        risk_dir = "improved" if min_cfs and min_cfs > 0.001 else "worsened" if min_cfs and min_cfs < -0.001 else "unchanged"

        sectors.append(SectorDelta(
            sector_name=name,
            start_pct=start_pct,
            end_pct=end_pct,
            avg_speed_delta=avg_speed,
            min_cfs_delta=min_cfs,
            avg_steering_delta=avg_steer,
            avg_drag_delta=avg_drag,
            avg_rpm_delta=avg_rpm,
            speed_direction=speed_dir,
            platform_risk_direction=risk_dir,
        ))

    # Build summary
    gained = [s for s in sectors if s.speed_direction == "gained"]
    lost = [s for s in sectors if s.speed_direction == "lost"]
    risky = [s for s in sectors if s.platform_risk_direction == "worsened"]

    parts: list[str] = []
    if gained:
        parts.append(f"Gained in {len(gained)} sector(s): {', '.join(s.sector_name for s in gained)}")
    if lost:
        parts.append(f"Lost in {len(lost)} sector(s): {', '.join(s.sector_name for s in lost)}")
    if risky:
        parts.append(f"Platform risk worsened in {len(risky)} sector(s): {', '.join(s.sector_name for s in risky)}")
    summary = " | ".join(parts) if parts else "No significant sector-level changes."

    return SectorIntelligenceResult(sectors=sectors, summary=summary)
