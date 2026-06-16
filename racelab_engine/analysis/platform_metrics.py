from __future__ import annotations

from racelab_engine.analysis.constants import (
    SPLITTER_CRITICAL_MM,
    SPLITTER_HIGH_MM,
    SPLITTER_SCRAPE_MM,
    SPLITTER_WATCH_MM,
)


def classify_splitter_height_mm(splitter_height_mm: float | None) -> str:
    if splitter_height_mm is None:
        return "unavailable"
    if splitter_height_mm <= SPLITTER_SCRAPE_MM:
        return "scrape"
    if splitter_height_mm <= SPLITTER_CRITICAL_MM:
        return "critical"
    if splitter_height_mm <= SPLITTER_HIGH_MM:
        return "high"
    return "watch" if splitter_height_mm <= SPLITTER_WATCH_MM else "safe"


__all__ = ["classify_splitter_height_mm"]
