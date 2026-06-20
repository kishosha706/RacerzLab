from __future__ import annotations

from racelab_engine.analysis.lap_classification import classify_laps
from racelab_engine.models.lap import LapSummary


def _lap(**overrides: object) -> LapSummary:
    data = {
        "lap_id": "run:lap:1",
        "run_id": "run",
        "lap_number": 1,
        "is_complete": True,
        "is_useful": True,
        "classification_tags": [],
    }
    data.update(overrides)
    return LapSummary(**data)


def test_useful_lap_gets_solo_clean_tag() -> None:
    classified = classify_laps([_lap()])

    assert "SOLO_CLEAN" in classified[0].classification_tags
    assert "NO_SETUP_CONCLUSION" not in classified[0].classification_tags


def test_junk_or_short_lap_gets_no_setup_conclusion() -> None:
    classified = classify_laps([_lap(is_complete=False, is_useful=False, classification_tags=["SHORT_RUN"])])

    assert "PARTIAL" in classified[0].classification_tags
    assert "SHORT_RUN" in classified[0].classification_tags
    assert "NO_SETUP_CONCLUSION" in classified[0].classification_tags


def test_existing_invalid_tag_is_preserved() -> None:
    classified = classify_laps([
        _lap(is_complete=False, is_useful=False, classification_tags=["CAUTION", "INVALID_FOR_PLATFORM_TUNING"])
    ])

    assert "CAUTION" in classified[0].classification_tags
    assert "INVALID_FOR_PLATFORM_TUNING" in classified[0].classification_tags


def test_empty_lap_list_stays_empty() -> None:
    assert classify_laps([]) == []
