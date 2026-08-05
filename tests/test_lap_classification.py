from __future__ import annotations

from racelab_engine.analysis.lap_classification import classify_laps
from racelab_engine.analysis.lap_eligibility import lap_ineligibility_reasons, lap_is_eligible
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


def test_useful_lap_gets_eligibility_tag_without_claiming_clean_air() -> None:
    classified = classify_laps([_lap()])

    assert "ELIGIBLE_FLYING_LAP" in classified[0].classification_tags
    assert "SOLO_CLEAN" not in classified[0].classification_tags
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


def test_complete_lap_with_caution_tag_is_not_eligible() -> None:
    classified = classify_laps([_lap(classification_tags=["SOLO_CLEAN", "CAUTION"])])

    assert classified[0].is_useful is False
    assert "ELIGIBLE_FLYING_LAP" not in classified[0].classification_tags
    assert "SOLO_CLEAN" not in classified[0].classification_tags
    assert "NO_SETUP_CONCLUSION" in classified[0].classification_tags
    assert lap_is_eligible(classified[0]) is False
    assert "Caution period" in lap_ineligibility_reasons(classified[0])


def test_empty_lap_list_stays_empty() -> None:
    assert classify_laps([]) == []
