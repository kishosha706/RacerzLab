from __future__ import annotations

import hashlib
import json
from typing import Any

from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.session import RunOverview


def _value(value: object, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def _structured_value(value: object) -> str:
    if value is None or value == {} or value == [] or value == ():
        return "Unavailable"
    return json.dumps(value, sort_keys=True, separators=(", ", ": "), default=str)


def _yes_no(value: bool | None) -> str:
    return "yes" if value is True else "no" if value is False else "Unavailable"


def generate_markdown_report(overview: RunOverview) -> str:
    session = overview.session
    best_lap = overview.best_useful_lap
    setup = overview.setup_snapshot
    platform_events = [event for event in overview.events if event.event_type.startswith("PLATFORM")]
    drag_events = [event for event in overview.events if event.event_type in {"FULL_THROTTLE_SPEED_LOSS", "STEERING_SCRUB"}]

    lines: list[str] = [
        "# RaceLab Garage Auto Report",
        "",
        "## Run",
        f"- Track: {_value(session.track_display_name or session.track_name)}",
        f"- Car: {_value(session.car_name)}",
        f"- Session: {_value(session.session_type)}",
        f"- Setup: {_value(session.setup_name or (setup.setup_name if setup else None))}",
        f"- Date/time: {_value(session.sim_date_time)}",
        f"- Weather: {_value(session.weather_summary)}",
        f"- Telemetry rate: {_value(session.telemetry_rate_hz, ' Hz' if session.telemetry_rate_hz else '')}",
        f"- Records: {_value(session.record_count)}",
        "",
        "## Best Useful Lap",
    ]

    if best_lap:
        lines.extend(
            [
                f"- Lap: {best_lap.lap_number}",
                f"- Time: {_value(best_lap.lap_time, ' sec' if best_lap.lap_time else '')}",
                f"- Avg speed: {_value(best_lap.avg_speed_mph, ' mph' if best_lap.avg_speed_mph else '')}",
                f"- Max speed: {_value(best_lap.max_speed_mph, ' mph' if best_lap.max_speed_mph else '')}",
                f"- RPM range: {_value(best_lap.min_rpm)} - {_value(best_lap.max_rpm)}",
                f"- Throttle: {_value(best_lap.avg_throttle_pct, '%' if best_lap.avg_throttle_pct else '')}",
                f"- Brake: {_value(best_lap.avg_brake_pct, '%' if best_lap.avg_brake_pct is not None else '')}",
                f"- Minimum splitter: {_value(best_lap.min_splitter_mm, ' mm' if best_lap.min_splitter_mm else '')}",
            ]
        )
    else:
        lines.append("- No useful lap identified.")

    lines.extend(["", "## Primary Findings"])
    if overview.primary_findings:
        lines.extend(f"{index}. {finding}" for index, finding in enumerate(overview.primary_findings, start=1))
    else:
        lines.append("1. No primary finding is available yet.")

    lines.extend(
        [
            "",
            "## Platform Events",
            "| Lap | Zone | Lap % | Distance | Speed | Splitter | Risk | Valid for tuning |",
            "|---:|---|---:|---:|---:|---:|---|---|",
        ]
    )
    if platform_events:
        for event in platform_events:
            evidence = event.evidence_json
            lines.append(
                "| "
                f"{_value(event.lap_number)} | "
                f"{_value(event.zone_name)} | "
                f"{_value(event.lap_pct_peak)} | "
                f"{_value(event.distance_m_peak)} | "
                f"{_value(evidence.get('speed_mph'), ' mph' if evidence.get('speed_mph') is not None else '')} | "
                f"{_value(event.primary_metric_value, ' mm' if event.primary_metric_value is not None else '')} | "
                f"{event.severity} | "
                f"{'yes' if event.valid_for_tuning else 'no'} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | unavailable | no |")

    lines.extend(
        [
            "",
            "## Drag/Scrub Risk Zones",
            "| Rank | Zone | Lap % | Evidence | Likely bucket | Confidence |",
            "|---:|---|---:|---|---|---:|",
        ]
    )
    if drag_events:
        for rank, event in enumerate(drag_events, start=1):
            evidence = event.evidence_json
            lines.append(
                "| "
                f"{rank} | "
                f"{_value(event.zone_name)} | "
                f"{_value(event.lap_pct_start)}-{_value(event.lap_pct_end)} | "
                f"{event.primary_metric_name}: {_value(event.primary_metric_value)}; throttle {_value(evidence.get('avg_throttle_pct'))}; brake {_value(evidence.get('avg_brake_pct'))} | "
                "aero/platform + steering scrub suspicion | "
                f"{event.confidence_score:.2f} |"
            )
    else:
        lines.append("| - | - | - | No drag/scrub-like zone identified yet. | unknown | 0.00 |")

    lines.extend(["", "## Setup-Relevant Values"])
    if setup:
        lines.extend(
            [
                f"- Front ride heights: LF {_value(setup.lf_ride_height_mm, ' mm' if setup.lf_ride_height_mm else '')} / RF {_value(setup.rf_ride_height_mm, ' mm' if setup.rf_ride_height_mm else '')}",
                f"- Rear ride heights: LR {_value(setup.lr_ride_height_mm, ' mm' if setup.lr_ride_height_mm else '')} / RR {_value(setup.rr_ride_height_mm, ' mm' if setup.rr_ride_height_mm else '')}",
                f"- Springs: LF {_value(setup.lf_front_spring_n_per_mm)} / RF {_value(setup.rf_front_spring_n_per_mm)} / LR {_value(setup.lr_rear_spring_n_per_mm)} / RR {_value(setup.rr_rear_spring_n_per_mm)}",
                "- Shocks: Unavailable",
                "- Packers/shims: Unavailable",
                f"- Tape: {_value(setup.tape_percent, '%' if isinstance(setup.tape_percent, (int, float)) else '')}",
                f"- Gear: {_value(setup.rear_end_ratio)}",
            ]
        )
    else:
        lines.append("- Setup snapshot unavailable.")

    lines.extend(
        [
            "",
            "## Engineering Observation",
            (
                "Located telemetry observations are available for mechanism qualification; no setup action is authorized."
                if any(event.valid_for_tuning for event in overview.events)
                else "No qualified engineering observation is available."
            ),
            "",
            "## Measurement Mission",
            (
                "Repeat the located behavior on eligible laps with the setup unchanged."
                if any(event.valid_for_tuning for event in overview.events)
                else "Import a real telemetry run and identify a useful lap."
            ),
            "",
            "## Typed Engineering Limitations",
        ]
    )
    if overview.engineering_blockers:
        for blocker in overview.engineering_blockers:
            blocks = ", ".join(target.value for target in blocker.blocks) or "no current surface"
            lines.extend(
                [
                    f"- **{blocker.code}** (`{blocker.scope}`; blocks: {blocks}) — {blocker.message}",
                    f"  Recovery: {blocker.recovery}",
                ]
            )
    else:
        lines.append("- None.")
    lines.extend(["", "## Display Warnings"])
    warnings = list(overview.warnings)
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None.")

    return "\n".join(lines).rstrip() + "\n"


def generate_controlled_workflow_report(
    workflow: ControlledWorkflow,
    *,
    stage_overviews: dict[str, RunOverview | None],
    manifests: dict[str, dict[str, Any]],
) -> str:
    """Render the persisted decision itself, with enough identity to reproduce it."""
    packet = workflow.packet
    opportunity = packet.opportunity
    quality = workflow.quality
    execution = workflow.execution
    reproduction = workflow.reproduction_snapshot
    card = packet.primary_test
    lines = [
        "# RacerZLab Controlled Test Report",
        "",
        "## Decision identity",
        f"- Workflow ID: {workflow.workflow_id}",
        f"- Status: {workflow.status}",
        f"- Created: {workflow.created_at.isoformat()}",
        f"- Updated: {workflow.updated_at.isoformat()}",
        f"- Source run ID: {workflow.source_run_id}",
        "- Analysis surface contract: reproducible_report",
        f"- Analysis version: {workflow.analysis_version}",
        f"- Scoring dependency/config SHA-256: {reproduction.get('analysis_code_and_config_sha256') or 'Unavailable'}",
        f"- Evidence state: {packet.evidence_state.value}",
        f"- Evidence-strength score: {packet.confidence_score:.3f} ({packet.confidence_basis})",
        f"- Recommendation score basis: {packet.recommendation_score_basis or 'Unavailable'}",
        f"- Recommendation score components: {packet.recommendation_score_components or 'Unavailable'}",
        f"- Driver decision context: {reproduction.get('decision_context') or 'Unavailable'}",
        f"- Source/A/B/A2 recording chronology: {_structured_value(reproduction.get('recording_chronology'))}",
        "",
        "## Target opportunity",
        f"- Position window: {opportunity.start_pct:.3f}% to {opportunity.end_pct:.3f}% lap",
        f"- Phase: {opportunity.phase}",
        f"- Canonical symptom: {packet.canonical_symptom}",
        f"- Observed time loss: {_value(opportunity.observed_time_loss_s, ' s')}",
        f"- Empirical noise: {_value(opportunity.empirical_noise_s, ' s')}",
        f"- Alignment confidence: {opportunity.alignment_confidence:.3f}",
        f"- Repeatable: {'yes' if opportunity.repeatable else 'no'}",
        f"- Source channels: {', '.join(opportunity.source_channels) or 'Unavailable'}",
        f"- Evidence event IDs: {', '.join(opportunity.evidence_event_ids) or 'Unavailable'}",
        "",
        "## One controlled change",
    ]
    if card is None:
        lines.extend([
            "- Setup change: Unavailable; the decision is a measurement mission.",
            f"- Mission: {packet.measurement_mission.purpose if packet.measurement_mission else 'Unavailable'}",
        ])
    else:
        lines.extend([
            f"- Control: {card.control_label} (`{card.control_key}`)",
            f"- Exact change: {card.exact_change}",
            f"- Change size: {card.change_size}",
            f"- Expected mechanism: {card.expected_mechanism}",
            f"- Success metrics: {'; '.join(card.success_metrics)}",
            f"- Countereffects: {'; '.join(card.countereffects)}",
            f"- Keep rule: {card.keep_rule}",
            f"- Rollback rule: {card.rollback_rule}",
        ])
    lines.extend(["", "## A/B/A2 source runs"])
    for stage in ("A", "B", "A2"):
        run_id = workflow.stage_run_ids.get(stage)
        overview = stage_overviews.get(stage)
        manifest = manifests.get(stage) or {}
        persisted_stage = (reproduction.get("stages") or {}).get(stage) or {}
        identity = persisted_stage.get("compatibility_identity") or manifest.get("compatibility_identity") or {}
        health = manifest.get("health_summary") or {}
        live_setup_payload = (
            overview.setup_snapshot.model_dump(mode="json")
            if overview is not None and overview.setup_snapshot is not None
            else None
        )
        live_setup_fingerprint = (
            hashlib.sha256(json.dumps(live_setup_payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
            if live_setup_payload is not None else None
        )
        setup_payload = persisted_stage.get("setup_values") or live_setup_payload
        setup_fingerprint = persisted_stage.get("setup_fingerprint") or live_setup_fingerprint
        eligible_numbers = (
            persisted_stage.get("eligible_lap_numbers")
            or workflow.stage_eligible_lap_numbers.get(stage, ())
        )
        live_mismatch = bool(
            persisted_stage.get("setup_fingerprint")
            and live_setup_fingerprint
            and persisted_stage["setup_fingerprint"] != live_setup_fingerprint
        )
        lines.extend([
            f"### {stage}",
            f"- Run ID: {run_id or 'Unavailable'}",
            f"- Source file SHA-256: {persisted_stage.get('source_file_sha256') or 'Unavailable'}",
            f"- File schema fingerprint: {persisted_stage.get('schema_fingerprint') or manifest.get('schema_fingerprint') or 'Unavailable'}",
            f"- Cache/analysis version: {persisted_stage.get('cache_version') or manifest.get('cache_version') or 'Unavailable'}",
            f"- Car/build/track identity: {identity or 'Unavailable'}",
            f"- Telemetry health: {health.get('status') or 'Unavailable'}",
            f"- Canonical eligible lap IDs used: {', '.join(map(str, eligible_numbers)) or 'Unavailable'}",
            f"- Setup fingerprint: {setup_fingerprint or 'Unavailable'}",
            f"- Setup values: {setup_payload or 'Unavailable'}",
            f"- Live data matches persisted setup: {'no - source data changed after scoring' if live_mismatch else 'yes' if persisted_stage else 'Unavailable'}",
        ])
    lines.extend([
        "",
        "## Persisted scoring inputs",
        f"- Planned B value: {_value(execution.planned_b_value if execution else None)}",
        f"- Observed A/B/A2 values: {_value(execution.observed_a_value if execution else None)} / {_value(execution.observed_b_value if execution else None)} / {_value(execution.observed_a2_value if execution else None)}",
        f"- B vs A target effect: {_value(execution.phase_effect_b_vs_a_s if execution else None, ' s')}",
        f"- B vs A2 target effect: {_value(execution.phase_effect_b_vs_a2_s if execution else None, ' s')}",
        f"- Empirical execution noise: {_value(execution.empirical_noise_s if execution else None, ' s')}",
        f"- Qualified empirical-noise observations: {_value(execution.empirical_noise_observations if execution else None)}",
        f"- Minimum target alignment confidence: {_value(execution.minimum_alignment_confidence if execution else None)}",
        f"- Lap-level target effects directionally consistent beyond noise: {_yes_no(execution.target_effect_distributions_consistent if execution else None)}",
        f"- Lap-level target-effect state: {execution.target_effect_distribution_state if execution and execution.target_effect_distribution_state else 'unavailable'}",
        f"- Lap-level target effect distributions (s): {_structured_value(reproduction.get('target_effect_distributions_s'))}",
        f"- Context/driver/integrity scores: {_value(execution.context_match_score if execution else None)} / {_value(execution.driver_match_score if execution else None)} / {_value(execution.sim_integrity_score if execution else None)}",
        f"- Control-specific telemetry guardrails passed: {_yes_no(execution.control_guardrails_passed if execution else None)}",
        f"- Control-specific guardrail metrics: {_structured_value(execution.control_guardrail_metrics if execution else None)}",
        f"- Countereffect noise thresholds by phase (s): {_structured_value(execution.countereffect_noise_by_phase_s if execution else None)}",
        f"- Countereffect phase distributions (s): {_structured_value(reproduction.get('countereffect_phase_distributions_s'))}",
        f"- Countereffect baseline-noise distributions (s): {_structured_value(reproduction.get('countereffect_baseline_noise_distributions_s'))}",
        f"- Countereffect passed: {_value(execution.countereffect_passed if execution else None)}",
        "",
        "## Controlled verdict",
        f"- Verdict: {quality.verdict if quality else 'Unavailable'}",
        f"- Protocol valid: {'yes' if quality and quality.protocol_valid else 'no' if quality else 'Unavailable'}",
        f"- Quality score: {_value(quality.score if quality else None, '/100')}",
        f"- Durable setup-effect admission: {'yes' if workflow.learning_admitted is True else 'no' if workflow.learning_admitted is False else 'Unavailable'}",
        "",
        "## Supporting evidence",
    ])
    supporting = [*packet.supporting_evidence, *(quality.supporting_evidence if quality else ())]
    lines.extend(f"- {item}" for item in supporting or ["Unavailable"])
    lines.extend(["", "## Contradictory evidence and blockers"])
    contradictions = [
        *packet.contradictory_evidence,
        *packet.blockers,
        *(quality.contradictory_evidence if quality else ()),
        *(quality.blockers if quality else ()),
    ]
    lines.extend(f"- {item}" for item in dict.fromkeys(contradictions) or ["None recorded."])
    lines.extend([
        "",
        "## Reproduction note",
        (
            "Re-open this workflow ID to reload the persisted packet, immutable stage identity/setup snapshots, lap IDs, scoring distributions, evidence IDs, memory-admission result, and server-derived verdict. Live source drift is reported against the persisted hashes. Missing evidence is printed as Unavailable and is never converted to zero."
            if reproduction else
            "Legacy workflow: an immutable scoring snapshot is Unavailable, so this report is an audit summary rather than a fully reproducible decision. Missing evidence is never converted to zero."
        ),
    ])
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["generate_controlled_workflow_report", "generate_markdown_report"]
