from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.dial_in_schema import DialInHypothesisResponse
from racelab_engine.knowledge.setup.dial_in_service import build_dial_in_response


def _print_debug_summary(summary: dict) -> None:
    print()
    print("Debug evidence:")
    print(f"- evidence_flags: {', '.join(summary['evidence_flags']) if summary['evidence_flags'] else 'none'}")
    print(f"- present_evidence: {', '.join(summary['present_evidence']) if summary['present_evidence'] else 'none'}")
    print(f"- missing_evidence: {', '.join(summary['missing_evidence']) if summary['missing_evidence'] else 'none'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query observation-only setup hypotheses from a run context."
    )
    parser.add_argument("--run-id", required=True, help="Run ID to inspect.")
    parser.add_argument("--complaint", required=True, help="Driver complaint to interpret.")
    parser.add_argument("--car-family", help="Optional car-family override.")
    parser.add_argument("--track-family", help="Optional track-family override.")
    parser.add_argument("--baseline-run-id", help="Optional baseline compare run.")
    parser.add_argument("--test-run-id", help="Optional test compare run.")
    parser.add_argument("--package-archetype", help="Optional package archetype hint.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum driver-facing swings to return.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit machine-readable JSON.")
    parser.add_argument("--debug-evidence", action="store_true", help="Include backend evidence detail for development.")
    args = parser.parse_args()

    response = DialInHypothesisResponse.from_internal(
        build_dial_in_response(
            args.run_id,
            args.complaint,
            car_family_override=args.car_family,
            track_family_override=args.track_family,
            baseline_run_id=args.baseline_run_id,
            test_run_id=args.test_run_id,
            package_archetype=args.package_archetype,
            limit=args.limit,
            include_debug_evidence=args.debug_evidence,
        )
    )
    if args.as_json:
        print(json.dumps(response.model_dump(exclude_none=True), indent=2))
        return 0

    print("Dial-In:")
    print(response.driver_message)
    if response.interpreted_phase:
        print(f"Phase: {response.interpreted_phase}")
    print(f"Data profile: {response.readiness_label}")
    print(f"Confidence: {response.confidence_label}")

    if response.clarification.needed:
        print()
        print("Clarification:")
        print(response.clarification.question)
        if response.clarification.options:
            print(f"Options: {', '.join(response.clarification.options)}")
        return 0

    if response.top_swings:
        print()
        print("Control areas to measure:")
        for index, swing in enumerate(response.top_swings, start=1):
            print(f"{index}. {swing.title}")
            print(f"   Candidate control area: {swing.candidate_control_label}")
            print(f"   Mechanism to verify: {swing.mechanism_to_verify}")
            print(f"   Counter-effect to watch: {swing.counter_effect_to_watch}")
            print(f"   Measurement needed: {swing.measurement_needed}")
            watch_targets = list(dict.fromkeys([*swing.validate_with_labels, *swing.watch_for_labels]))
            print(f"   What to watch for: {', '.join(watch_targets)}")
            print(f"   Readiness: {swing.readiness_label}")

    if response.next_step:
        print()
        print(f"Next step: {response.next_step}")
    if response.warnings:
        print()
        print("Warnings:")
        for warning in response.warnings:
            print(f"- {warning}")

    if args.debug_evidence and response.hidden_evidence_summary:
        _print_debug_summary(response.hidden_evidence_summary.model_dump())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
