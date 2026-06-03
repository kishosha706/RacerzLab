from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.knowledge.setup.source_digest import build_digest_summary
from racelab_engine.knowledge.setup.validator import validate_setup_knowledge


REPORT_PATH = Path("docs/generated/setup_knowledge_digest_report.md")


def main() -> int:
    knowledge = load_setup_knowledge()
    problems = validate_setup_knowledge(knowledge)
    summary = build_digest_summary(knowledge)

    areas_by_system: dict[str, list[str]] = defaultdict(list)
    area_kinds = Counter(area.static_or_live for area in knowledge.setup_areas)
    for area in knowledge.setup_areas:
        areas_by_system[area.system].append(area.setup_area)

    effects_by_system: dict[str, list[str]] = defaultdict(list)
    for effect in knowledge.setup_effects:
        area = knowledge.setup_area_by_id.get(effect.setup_area)
        system = area.system if area else "unknown"
        effects_by_system[system].append(effect.effect_id)

    strength_summary = Counter(effect.effect_strength for effect in knowledge.setup_effects)
    lines = [
        "# Setup Knowledge Digest Report",
        "",
        "Generated from reviewed local JSON records derived from the RacerZLab master setup matrix.",
        "",
        "## Guide Sources",
        *[f"- {source.source_id}: {source.title} ({source.status})" for source in knowledge.guide_sources],
        "",
        "## Accepted Principles",
        *[f"- {principle.title}: {principle.short_ui_wording}" for principle in knowledge.guide_principles if principle.review_status == "accepted"],
        "",
        "## Terms",
        f"- Term definitions: {len(knowledge.guide_term_definitions)}",
        "",
        "## Setup Areas",
        f"- Setup areas: {len(knowledge.setup_areas)}",
        *[f"- {system}: {len(ids)}" for system, ids in sorted(areas_by_system.items())],
        "",
        "## Setup Area Types",
        *[f"- {kind}: {count}" for kind, count in sorted(area_kinds.items())],
        "",
        "## Setup Effects By System",
    ]
    for system, ids in sorted(effects_by_system.items()):
        lines.append(f"- {system}: {len(ids)}")
    lines.extend(
        [
            "",
            "## Effect Strength Summary",
            *[f"- Strength {strength}: {count}" for strength, count in sorted(strength_summary.items())],
            "",
            "## Counter-Effect Summary",
            f"- Effects with counter-effect text: {sum(1 for effect in knowledge.setup_effects if effect.counter_effect)}",
            "",
            "## Car Capability Gates",
            "- Next Gen disabled areas: track_bar, truck_arm_mount, bump_stop, packer",
            "- Legacy oval keeps those areas as car-specific knowledge.",
            "",
            "## Next Gen ARB Constraints",
            "- Diameter: 1.375, 2.000",
            "- Arm positions: P1, P2, P3, P4, P5",
            "",
            "## Next Gen Diffuser / Front Feed Rules",
            *[f"- {rule.title}: {rule.wording}" for rule in knowledge.nextgen_platform_rules],
            "",
            "## Shock Interpretation Rules",
            *[f"- {rule.topic}: {rule.wording}" for rule in knowledge.shock_interpretation],
            "",
            "## Oval Matrix-Derived Condition Mapping",
            *[f"- {mapping.symptom}: {mapping.setup_area} / {mapping.direction}" for mapping in knowledge.guide_setup_mappings],
            "",
            "## Flowchart Process Logic",
            "- Exit grip first, entry balance second, driver feel last.",
            "- One change at a time with comparable-window validation.",
            "",
            "## Package Archetypes",
            *[f"- {package.archetype_id}: {package.name}" for package in knowledge.package_archetypes],
            "",
            "## Needs-Review Items",
            *[f"- {item.review_id}: {item.safe_wording}" for item in knowledge.guide_review_queue if item.status == "needs_review"],
            "",
            "## Validation Status",
            "passed" if not problems else "failed",
        ]
    )
    if problems:
        lines.extend([f"- {problem}" for problem in problems])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(summary)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
