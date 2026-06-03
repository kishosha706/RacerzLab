from __future__ import annotations

from collections import Counter

from .loader import SetupKnowledge, load_setup_knowledge


def build_digest_summary(knowledge: SetupKnowledge | None = None) -> dict[str, object]:
    knowledge = knowledge or load_setup_knowledge()
    review_statuses = Counter(
        [
            *(principle.review_status for principle in knowledge.guide_principles),
            *(term.review_status for term in knowledge.guide_term_definitions),
            *(mapping.review_status for mapping in knowledge.guide_setup_mappings),
            *(item.status for item in knowledge.guide_review_queue),
        ]
    )
    effects_by_system = Counter(
        knowledge.setup_area_by_id[effect.setup_area].system
        for effect in knowledge.setup_effects
        if effect.setup_area in knowledge.setup_area_by_id
    )
    return {
        "source_count": len(knowledge.guide_sources),
        "principle_count": len(knowledge.guide_principles),
        "term_count": len(knowledge.guide_term_definitions),
        "mapping_count": len(knowledge.guide_setup_mappings),
        "setup_area_count": len(knowledge.setup_areas),
        "setup_effect_count": len(knowledge.setup_effects),
        "review_statuses": dict(review_statuses),
        "effects_by_system": dict(sorted(effects_by_system.items())),
        "needs_review": [item.review_id for item in knowledge.guide_review_queue if item.status == "needs_review"],
    }
