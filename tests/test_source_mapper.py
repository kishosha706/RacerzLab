from __future__ import annotations

from dataclasses import replace

from racelab_engine.knowledge.setup.schema import GuidePrinciple, GuideSetupMapping, GuideTermDefinition
from racelab_engine.knowledge.setup.source_mapper import query_guide_knowledge

from test_setup_validator import _effect, _knowledge


def _guide_knowledge():
    return replace(
        _knowledge(),
        guide_term_definitions=[
            GuideTermDefinition(
                term_id="cross_term",
                term="Cross Weight",
                aliases=["wedge"],
                canonical_term="cross_weight",
                definition="Diagonal load split.",
                domain="oval",
                symptom_hint="tight_entry",
                car_scope="all",
                source_ids=["guide"],
                review_status="accepted",
            ),
            GuideTermDefinition(
                term_id="bar_term",
                term="Track Bar",
                aliases=["panhard bar"],
                canonical_term="track_bar",
                definition="Legacy rear location bar.",
                domain="oval",
                symptom_hint="loose_exit",
                car_scope="legacy_oval",
                source_ids=["guide"],
                review_status="accepted",
            ),
        ],
        guide_principles=[
            GuidePrinciple(
                principle_id="entry_balance",
                source_ids=["guide"],
                title="Entry balance",
                racerzlab_wording="Use setup evidence to calm tight entry.",
                source_summary="Entry balance depends on platform and tire loading.",
                domain="oval",
                car_scope="all",
                setup_areas=["cross_weight"],
                phases=["entry"],
                symptoms=["tight_entry"],
                evidence_links=["setup_snapshot"],
                confidence="medium",
                review_status="accepted",
                cautions=["Watch exit rotation."],
                do_not_overclaim=[],
                short_ui_wording="Calm tight entry.",
                why_it_matters="Entry sets the corner.",
                mistakes_to_avoid=[],
            )
        ],
        guide_setup_mappings=[
            GuideSetupMapping(
                mapping_id="cross_tight_entry",
                source_ids=["guide"],
                setup_area="cross_weight",
                symptom="tight_entry",
                phase="entry",
                direction="raise",
                intended_effect="Add entry security with cross weight.",
                counter_effect="May hurt exit rotation.",
                effect_strength=3,
                coupling_risk="medium",
                evidence_required=["setup_snapshot"],
                validation_targets=["entry balance"],
                applies_to=["all"],
                disabled_for=[],
                exact_value_policy="none",
                review_status="accepted",
                preferred_when=[],
                avoid_when=[],
                watch_for=["exit rotation"],
            ),
            GuideSetupMapping(
                mapping_id="track_bar_loose_exit",
                source_ids=["guide"],
                setup_area="track_bar",
                symptom="loose_exit",
                phase="exit",
                direction="raise",
                intended_effect="Tune legacy loose exit with track bar.",
                counter_effect="May hurt entry.",
                effect_strength=4,
                coupling_risk="high",
                evidence_required=["setup_snapshot"],
                validation_targets=["exit balance"],
                applies_to=["legacy_oval"],
                disabled_for=["next_gen"],
                exact_value_policy="none",
                review_status="accepted",
                preferred_when=[],
                avoid_when=[],
                watch_for=["entry stability"],
            ),
        ],
        setup_effects=[
            _effect(effect_id="cross_tight_entry_effect", setup_area="cross_weight", helps=["tight_entry"], effect="Calm tight entry with cross weight."),
            _effect(
                effect_id="track_bar_loose_exit_effect",
                setup_area="track_bar",
                applies_to=["legacy_oval"],
                disabled_for=["next_gen"],
                helps=["loose_exit"],
                effect="Tune loose exit with track bar.",
                cautions=["Unavailable on Next Gen."],
            ),
        ],
    )


def test_query_guide_knowledge_filters_topic_by_substring() -> None:
    result = query_guide_knowledge(topic="cross", knowledge=_guide_knowledge())

    assert [term.term_id for term in result.terms] == ["cross_term"]
    assert [mapping.mapping_id for mapping in result.mappings] == ["cross_tight_entry"]
    assert [effect.effect_id for effect in result.setup_effects] == ["cross_tight_entry_effect"]


def test_query_guide_knowledge_filters_by_symptom() -> None:
    result = query_guide_knowledge(symptom="loose_exit", knowledge=_guide_knowledge())

    assert [term.term_id for term in result.terms] == ["bar_term"]
    assert [mapping.mapping_id for mapping in result.mappings] == ["track_bar_loose_exit"]
    assert [effect.effect_id for effect in result.setup_effects] == ["track_bar_loose_exit_effect"]


def test_query_guide_knowledge_filters_disabled_car_family() -> None:
    result = query_guide_knowledge(car_family="next_gen", knowledge=_guide_knowledge())

    assert "track_bar_loose_exit" not in {mapping.mapping_id for mapping in result.mappings}
    assert "track_bar_loose_exit_effect" not in {effect.effect_id for effect in result.setup_effects}
    assert "cross_tight_entry" in {mapping.mapping_id for mapping in result.mappings}


def test_query_guide_knowledge_combines_filters() -> None:
    result = query_guide_knowledge(
        topic="entry",
        setup_area="cross_weight",
        symptom="tight_entry",
        car_family="next_gen",
        knowledge=_guide_knowledge(),
    )

    assert [principle.principle_id for principle in result.principles] == ["entry_balance"]
    assert [mapping.mapping_id for mapping in result.mappings] == ["cross_tight_entry"]
    assert [effect.effect_id for effect in result.setup_effects] == ["cross_tight_entry_effect"]
    assert result.source_ids == ["guide"]


def test_query_guide_knowledge_empty_result() -> None:
    result = query_guide_knowledge(topic="diffuser", setup_area="track_bar", car_family="next_gen", knowledge=_guide_knowledge())

    assert result.terms == []
    assert result.principles == []
    assert result.mappings == []
    assert result.setup_effects == []
    assert result.cautions == []
    assert result.source_ids == []
