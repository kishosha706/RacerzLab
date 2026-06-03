from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.matcher import query_result_to_dict, query_setup_knowledge


STRENGTH_LABELS = {
    1: "driver feel / small polish",
    2: "fine tuning",
    3: "medium phase-specific lever",
    4: "strong balance lever",
    5: "major package lever",
}


def _split_evidence(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _display_readiness(readiness: str) -> str:
    return readiness.replace("_", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Query local deterministic setup knowledge.")
    parser.add_argument("--car-family", required=True)
    parser.add_argument("--symptom", required=True)
    parser.add_argument("--phase")
    parser.add_argument("--track-family")
    parser.add_argument("--package-archetype")
    parser.add_argument("--evidence", help="Comma-separated evidence tags, e.g. platform,tires,shocks,setup_snapshot")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--show-disabled", action="store_true")
    parser.add_argument("--show-missing-evidence", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = query_setup_knowledge(
        car_family=args.car_family,
        symptom=args.symptom,
        phase=args.phase,
        track_family=args.track_family,
        package_archetype=args.package_archetype,
        evidence=_split_evidence(args.evidence),
        limit=args.limit,
    )

    if args.as_json:
        print(json.dumps(query_result_to_dict(result), indent=2))
        return 0

    parsed = result.parsed_symptom
    print("Parsed symptom:")
    print(parsed.canonical_symptom)
    print(f"Phase: {result.parsed_phase}")
    if result.package_archetype:
        print(f"Package context: {result.package_archetype}")
    if result.track_family:
        print(f"Track family: {result.track_family}")
    if parsed.possible_secondary:
        print(f"Context: {', '.join(parsed.possible_secondary)}")
    if result.clarification_question:
        print(f"Clarification: {result.clarification_question}")

    print()
    print("Ranked setup swings:")
    for index, ranked in enumerate(result.candidate_effects, start=1):
        effect = ranked.effect
        strength_label = STRENGTH_LABELS.get(effect.effect_strength, "setup lever")
        missing = ", ".join(ranked.missing_evidence) if ranked.missing_evidence else "none"
        present = ", ".join(ranked.evidence_matched) if ranked.evidence_matched else "none"
        print()
        print(f"Candidate {index}: {effect.direction}")
        print(f"Area: {effect.setup_area}")
        print(f"Strength: {effect.effect_strength} / {strength_label}")
        print(f"Risk: {effect.coupling_risk}")
        print(f"Effect: {effect.effect}")
        print(f"Counter-effect: {effect.counter_effect}")
        reasons = [_display_readiness(reason) for reason in ranked.ranking_reasons]
        print(f"Why ranked: {'; '.join(reasons)}")
        print(f"Evidence: {_display_readiness(ranked.readiness)}")
        print(f"Evidence present: {present}")
        print(f"Evidence needed: {', '.join(effect.evidence_required)}")
        if args.show_missing_evidence or ranked.readiness != "ready":
            print(f"Missing: {missing}")
        print(f"One-change test: {ranked.one_change_test_plan}")
        print(f"Validate: {', '.join(effect.validation_targets)}")
        if effect.watch_for_targets:
            print(f"Watch for: {', '.join(effect.watch_for_targets)}")
        if effect.setup_package_tags:
            print(f"Package notes: {', '.join(effect.setup_package_tags)}")
        if effect.preferred_when:
            print(f"Preferred when: {', '.join(effect.preferred_when)}")
        if effect.avoid_when:
            print(f"Avoid when: {', '.join(effect.avoid_when)}")

    if args.show_disabled and result.disabled_setup_areas:
        print()
        print(f"Disabled by car capability for {args.car_family}:")
        print(", ".join(result.disabled_setup_areas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
