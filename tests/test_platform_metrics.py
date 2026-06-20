from __future__ import annotations

import math

from racelab_engine.analysis.platform_metrics import classify_splitter_height_mm


def test_splitter_height_classification_boundaries() -> None:
    assert classify_splitter_height_mm(0.0) == "scrape"
    assert classify_splitter_height_mm(3.0) == "critical"
    assert classify_splitter_height_mm(6.0) == "high"
    assert classify_splitter_height_mm(10.0) == "watch"
    assert classify_splitter_height_mm(10.1) == "safe"


def test_splitter_height_missing_and_nan_stay_unavailable() -> None:
    assert classify_splitter_height_mm(None) == "unavailable"
    assert classify_splitter_height_mm(math.nan) == "unavailable"
    assert classify_splitter_height_mm(math.inf) == "unavailable"
