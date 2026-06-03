from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.matcher import query_setup_knowledge


def _split_evidence(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Query local deterministic setup knowledge.")
    parser.add_argument("--car-family", required=True)
    parser.add_argument("--symptom", required=True)
    parser.add_argument("--phase")
    parser.add_argument("--evidence", help="Comma-separated evidence tags, e.g. platform,tires,shocks,setup_snapshot")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    result = query_setup_knowledge(
        car_family=args.car_family,
        symptom=args.symptom,
        phase=args.phase,
        evidence=_split_evidence(args.evidence),
        limit=args.limit,
    )

    parsed = result.parsed_symptom
    print("Parsed symptom:")
    print(parsed.canonical_symptom)
    print(f"Phase: {parsed.phase}")
    if parsed.possible_secondary:
        print(f"Context: {', '.join(parsed.possible_secondary)}")
    if result.clarification_question:
        print(f"Clarification: {result.clarification_question}")

    print()
    print("Candidate setup swings:")
    for index, ranked in enumerate(result.candidate_effects, start=1):
        effect = ranked.effect
        print(f"{index}. {effect.direction} - Strength {effect.effect_strength}, Risk {effect.coupling_risk}")
        print(f"   Area: {effect.setup_area}")
        print(f"   Effect: {effect.effect}")
        print(f"   Counter-effect: {effect.counter_effect}")
        print(f"   Evidence required: {', '.join(effect.evidence_required)}")
        print(f"   Validation targets: {', '.join(effect.validation_targets)}")
        print(f"   Test: {effect.test_language}")

    if result.disabled_setup_areas:
        print()
        print(f"Disabled for {args.car_family}:")
        print(", ".join(result.disabled_setup_areas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
