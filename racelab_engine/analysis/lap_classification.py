from __future__ import annotations

from racelab_engine.analysis.lap_eligibility import INVALID_TUNING_TAGS
from racelab_engine.models.lap import LapSummary


def classify_laps(laps: list[LapSummary]) -> list[LapSummary]:
    if not laps:
        return []

    classified: list[LapSummary] = []
    for lap in laps:
        tags = set(lap.classification_tags)
        invalid_tags = {tag.upper() for tag in tags} & INVALID_TUNING_TAGS
        eligible = lap.is_complete and lap.is_useful and not invalid_tags
        if eligible:
            # Eligibility says the lap passed the setup-evidence gate. It does
            # not establish traffic or aerodynamic cleanliness.
            tags.discard("SOLO_CLEAN")
            tags.add("ELIGIBLE_FLYING_LAP")
        else:
            tags.discard("ELIGIBLE_FLYING_LAP")
            tags.discard("SOLO_CLEAN")
            if not lap.is_complete:
                tags.add("PARTIAL")
            if "INVALID_FOR_PLATFORM_TUNING" not in tags:
                tags.add("NO_SETUP_CONCLUSION")
        if hasattr(lap, "model_copy"):
            classified.append(lap.model_copy(update={
                "is_useful": eligible,
                "classification_tags": sorted(tags),
            }))
        else:
            classified.append(lap.copy(update={
                "is_useful": eligible,
                "classification_tags": sorted(tags),
            }))
    return classified
