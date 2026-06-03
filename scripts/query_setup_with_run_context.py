from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.evidence_adapter import query_setup_for_run_context, run_context_result_to_dict


STRENGTH_LABELS = {
    1: "driver feel / small polish",
    2: "fine tuning",
    3: "medium phase-specific lever",
    4: "strong balance lever",
    5: "major package lever",
}


def _print_evidence_groups(groups: list[dict], *, only_supported: bool = True) -> None:
    for group in groups:
        if only_supported and not group["can_support_setup_knowledge"]:
            continue
        print(f"- {group['group_id']}: {group['status']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Query setup knowledge with real run evidence context.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--symptom", required=True)
    parser.add_argument("--car-family")
    parser.add_argument("--track-family")
    parser.add_argument("--baseline-run-id")
    parser.add_argument("--test-run-id")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--show-evidence", action="store_true")
    parser.add_argument("--show-disabled", action="store_true")
    args = parser.parse_args()

    result = query_setup_for_run_context(
        args.run_id,
        args.symptom,
        baseline_run_id=args.baseline_run_id,
        test_run_id=args.test_run_id,
        car_family_override=args.car_family,
        track_family_override=args.track_family,
        limit=args.limit,
    )
    payload = run_context_result_to_dict(result)

    if args.as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Run:")
    print(f"- car: {payload.get('car_name') or 'unknown'}")
    print(f"- car_family: {payload['car_family']}")
    print(f"- track: {payload.get('track_name') or 'unknown'}")
    print(f"- track_family: {payload['track_family']}")
    print()
    print("Evidence:")
    _print_evidence_groups(payload["evidence_groups"], only_supported=not args.show_evidence)

    print()
    print("Parsed symptom:")
    print(f"- {payload['parsed_symptom']['canonical_symptom']}")
    print(f"- phase: {payload['parsed_phase']}")
    if payload.get("clarification_question"):
        print(f"- clarification: {payload['clarification_question']}")

    print()
    for index, candidate in enumerate(payload["candidates"], start=1):
        strength_label = STRENGTH_LABELS.get(candidate["strength"], "setup lever")
        print(f"Candidate {index}: {candidate['direction']}")
        print(f"Strength: {candidate['strength']} / {strength_label}")
        print(f"Risk: {candidate['risk']}")
        print(f"Evidence: {candidate['readiness'].replace('_', ' ')}")
        if candidate["evidence_missing"]:
            print(f"Missing: {', '.join(candidate['evidence_missing'])}")
        print(f"Effect: {candidate['effect']}")
        print(f"Counter-effect: {candidate['counter_effect']}")
        print(f"Why ranked: {'; '.join(candidate['why_ranked'])}")
        print(f"One-change test: {candidate['one_change_test']}")
        print(f"Validate: {', '.join(candidate['validate_with'])}")
        if candidate["watch_for"]:
            print(f"Watch for: {', '.join(candidate['watch_for'])}")
        if candidate["avoid_when"]:
            print(f"Avoid when: {', '.join(candidate['avoid_when'])}")
        print()

    if args.show_disabled and payload["disabled_setup_areas"]:
        print("Disabled by car capability:")
        print(", ".join(payload["disabled_setup_areas"]))
        print()

    if payload["run_warnings"]:
        print("Warnings:")
        for warning in payload["run_warnings"]:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
