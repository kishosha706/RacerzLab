from __future__ import annotations

from racelab_engine.analysis.evidence_contracts import EvidenceEvaluation
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.recommendation import Recommendation


def build_recommendations(
    run_id: str,
    events: list[TelemetryEvent],
    *,
    evidence_evaluation: EvidenceEvaluation | None = None,
) -> list[Recommendation]:
    if evidence_evaluation is None or not evidence_evaluation.eligible:
        return []
    authorized = next(
        (
            output
            for output in evidence_evaluation.authorized_outputs
            if output.key == "controlled_setup_test"
        ),
        None,
    )
    if authorized is None:
        return []
    tuning_events = [
        event
        for event in events
        if event.valid_for_tuning
        and event.evidence_state not in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.BLOCKED_BY_CONTEXT,
        }
        and bool(event.source_channels)
    ]
    primary_event = max(
        tuning_events,
        key=lambda event: (event.confidence_score, event.severity in {"critical", "high"}),
        default=None,
    )
    if primary_event is None:
        return []

    cause_bucket = (
        "observed resistance/scrub-like behavior; cause not established"
        if primary_event.is_proxy_based or primary_event.event_type == "FULL_THROTTLE_SPEED_LOSS"
        else "observed platform-risk evidence"
        if "PLATFORM" in primary_event.event_type or "SPLITTER" in primary_event.event_type
        else "observed telemetry issue; cause not established"
    )
    effective_confidence = min(
        primary_event.confidence_score,
        evidence_evaluation.confidence_cap,
    )
    confidence_limit_reasons = [
        limit.message for limit in evidence_evaluation.confidence_limits
    ]
    evidence_strength = (
        "high" if effective_confidence >= 0.8
        else "medium" if effective_confidence >= 0.5
        else "low"
    )

    return [
        Recommendation(
            recommendation_id=f"{run_id}:rec:1",
            run_id=run_id,
            priority_rank=1,
            issue=primary_event.event_type,
            cause_bucket=cause_bucket,
            recommendation_text=(
                "Run one controlled platform/scrub test. Watch speed in the target zone, "
                "minimum splitter, steering angle, and RPM behavior."
            ),
            confidence_score=effective_confidence,
            evidence_strength=evidence_strength,
            success_metric="Speed improves in the target zone without worsening splitter risk.",
            required_next_data=["same track", "same test type", "one setup change", "lap-distance aligned comparison"],
            do_not_change_warnings=["Do not change gear and tape in the same test."],
            evidence_event_ids=[primary_event.event_id],
            evidence_state=authorized.evidence_state,
            source_channels=sorted(authorized.source_channels),
            blocker_reasons=[],
            confidence_limit_reasons=confidence_limit_reasons,
        )
    ]
