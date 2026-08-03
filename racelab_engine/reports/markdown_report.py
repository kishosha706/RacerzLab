from __future__ import annotations

from racelab_engine.models.session import RunOverview


def _value(value: object, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def generate_markdown_report(overview: RunOverview) -> str:
    session = overview.session
    best_lap = overview.best_useful_lap
    setup = overview.setup_snapshot
    platform_events = [event for event in overview.events if event.event_type.startswith("PLATFORM")]
    drag_events = [event for event in overview.events if event.event_type in {"FULL_THROTTLE_SPEED_LOSS", "STEERING_SCRUB"}]
    recommendation = overview.recommendations[0] if overview.recommendations else None

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
            "## Crew Chief Recommendation",
            recommendation.recommendation_text if recommendation else "No recommendation is available without supporting evidence.",
            "",
            "## Next Test",
            overview.next_test or (recommendation.success_metric if recommendation else "Import a real telemetry run and identify a useful lap.") or "",
            "",
            "## Success Metric",
            recommendation.success_metric if recommendation and recommendation.success_metric else "Unavailable until a follow-up run is imported.",
            "",
            "## Warnings",
        ]
    )
    warnings = list(overview.warnings)
    if recommendation:
        warnings.extend(recommendation.do_not_change_warnings)
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None.")

    return "\n".join(lines).rstrip() + "\n"
