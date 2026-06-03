from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.knowledge.setup.source_digest import build_digest_summary
from racelab_engine.knowledge.setup.source_loader import load_master_setup_matrix


def main() -> int:
    source = load_master_setup_matrix()
    knowledge = load_setup_knowledge()
    summary = build_digest_summary(knowledge)
    print(f"Loaded source: {source.source_id}")
    print(f"Source path: {source.path}")
    print(f"Source characters: {len(source.text)}")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
