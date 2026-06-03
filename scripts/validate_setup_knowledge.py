from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.knowledge.setup.validator import validate_setup_knowledge


def main() -> int:
    knowledge = load_setup_knowledge()
    problems = validate_setup_knowledge(knowledge)
    if problems:
        print("Setup knowledge validation failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("Setup knowledge validation passed.")
    print(f"Car capabilities: {len(knowledge.car_capabilities)}")
    print(f"Setup areas: {len(knowledge.setup_areas)}")
    print(f"Setup effects: {len(knowledge.setup_effects)}")
    print(f"Symptom phrases: {len(knowledge.symptom_vocabulary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
