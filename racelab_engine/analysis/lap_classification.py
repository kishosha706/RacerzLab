from __future__ import annotations

from racelab_engine.models.lap import LapSummary


def classify_laps(laps: list[LapSummary]) -> list[LapSummary]:
    if not laps:
        return []

    classified: list[LapSummary] = []
    for lap in laps:
        tags = set(lap.classification_tags)
        if lap.is_complete and lap.is_useful:
            tags.add("SOLO_CLEAN")
        else:
            if not lap.is_complete:
                tags.add("PARTIAL")
            if "INVALID_FOR_PLATFORM_TUNING" not in tags:
                tags.add("NO_SETUP_CONCLUSION")
        if hasattr(lap, "model_copy"):
            classified.append(lap.model_copy(update={"classification_tags": sorted(tags)}))
        else:
            classified.append(lap.copy(update={"classification_tags": sorted(tags)}))
    return classified
