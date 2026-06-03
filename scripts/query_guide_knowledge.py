from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.source_mapper import query_guide_knowledge


def main() -> int:
    parser = argparse.ArgumentParser(description="Query source-backed setup guide knowledge.")
    parser.add_argument("--source-id")
    parser.add_argument("--topic")
    parser.add_argument("--setup-area")
    parser.add_argument("--symptom")
    parser.add_argument("--car-family")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = query_guide_knowledge(
        source_id=args.source_id,
        topic=args.topic,
        setup_area=args.setup_area,
        symptom=args.symptom,
        car_family=args.car_family,
    )

    payload = {
        "terms": [term.model_dump() for term in result.terms],
        "principles": [principle.model_dump() for principle in result.principles],
        "mappings": [mapping.model_dump() for mapping in result.mappings],
        "setup_effects": [effect.model_dump() for effect in result.setup_effects],
        "cautions": result.cautions,
        "source_ids": result.source_ids,
    }
    if args.as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Source-backed guide query")
    print(f"Sources: {', '.join(result.source_ids) if result.source_ids else 'none'}")
    if result.terms:
        print("\nTerm definitions:")
        for term in result.terms[:10]:
            print(f"- {term.term} -> {term.canonical_term}: {term.definition}")
    if result.principles:
        print("\nRelated principles:")
        for principle in result.principles[:10]:
            print(f"- {principle.title}: {principle.short_ui_wording}")
    if result.mappings:
        print("\nSetup mappings:")
        for mapping in result.mappings[:10]:
            print(f"- {mapping.symptom} / {mapping.phase} / {mapping.setup_area}: {mapping.direction}")
            print(f"  Effect: {mapping.intended_effect}")
            print(f"  Counter-effect: {mapping.counter_effect}")
            print(f"  Review: {mapping.review_status}")
    if result.setup_effects:
        print("\nSetup effects:")
        for effect in result.setup_effects[:10]:
            print(f"- {effect.effect_id} ({effect.setup_area})")
            print(f"  Effect: {effect.effect}")
            print(f"  Counter-effect: {effect.counter_effect}")
            print(f"  Review: {effect.review_status}")
    if result.cautions:
        print("\nCautions:")
        for caution in result.cautions[:10]:
            print(f"- {caution}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
