from __future__ import annotations

from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.recommendation import Recommendation


def build_recommendations(run_id: str, events: list[TelemetryEvent]) -> list[Recommendation]:
    tuning_events = [event for event in events if event.valid_for_tuning]
    first_tuning_event = tuning_events[0] if tuning_events else None
    if first_tuning_event is None:
        return []

    return [
        Recommendation(
            recommendation_id=f"{run_id}:rec:1",
            run_id=run_id,
            priority_rank=1,
            issue=first_tuning_event.event_type,
            cause_bucket="aero/platform + steering scrub suspicion",
            recommendation_text=(
                "Run one controlled platform/scrub test. Watch speed in the target zone, "
                "minimum splitter, steering angle, and RPM behavior."
            ),
            confidence_score=first_tuning_event.confidence_score,
            evidence_strength="medium" if first_tuning_event.confidence_score < 0.8 else "high",
            success_metric="Speed improves in the target zone without worsening splitter risk.",
            required_next_data=["same track", "same test type", "one setup change", "lap-distance aligned comparison"],
            do_not_change_warnings=["Do not change gear and tape in the same test."],
            evidence_event_ids=[first_tuning_event.event_id],
        )
    ]
