from __future__ import annotations

import re
from pathlib import Path

from racelab_engine.knowledge.setup import compile_engineering_knowledge_coverage
from racelab_engine.models.engineering_knowledge import (
    ControlledKnowledgeHistory,
    CurrentEngineeringKnowledgeProjection,
    CurrentKnowledgeHypothesis,
    P19TestableControl,
)


ROOT = Path(__file__).resolve().parents[1]


def _typescript_fields(source: str, name: str) -> set[str]:
    match = re.search(
        rf"export type {name} = \{{(.*?)^\}};",
        source,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"missing TypeScript type {name}"
    return set(re.findall(r"^  ([a-z0-9_]+):", match.group(1), flags=re.MULTILINE))


def _guard_keys(source: str, name: str) -> set[str]:
    match = re.search(
        rf"const {name} = new Set\(\[(.*?)\]\);",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, f"missing exact-key guard {name}"
    return set(re.findall(r'"([a-z0-9_]+)"', match.group(1)))


def test_p351_client_exact_keys_match_all_public_models() -> None:
    types = (ROOT / "ui/src/types/engineeringKnowledge.ts").read_text(
        encoding="utf-8"
    )
    trust = (ROOT / "ui/src/utils/engineeringKnowledgeTrust.ts").read_text(
        encoding="utf-8"
    )
    for type_name, key_name, model in (
        (
            "CurrentEngineeringKnowledgeProjection",
            "PROJECTION_KEYS",
            CurrentEngineeringKnowledgeProjection,
        ),
        ("CurrentKnowledgeHypothesis", "HYPOTHESIS_KEYS", CurrentKnowledgeHypothesis),
        ("ControlledKnowledgeHistory", "HISTORY_KEYS", ControlledKnowledgeHistory),
        ("P19TestableControl", "CONTROL_KEYS", P19TestableControl),
    ):
        backend = set(model.model_fields)
        assert _typescript_fields(types, type_name) == backend
        assert _guard_keys(trust, key_name) == backend


def test_p351_client_pins_complete_reviewed_bridge_inventory_and_authority() -> None:
    trust = (ROOT / "ui/src/utils/engineeringKnowledgeTrust.ts").read_text(
        encoding="utf-8"
    )
    coverage = compile_engineering_knowledge_coverage()

    assert coverage.catalog_effect_count == coverage.bridge_count == 92
    assert coverage.report_sha256 in trust
    assert "value.hypotheses.length !== 92" in trust
    assert "new Set(bridgeIds).size !== bridgeIds.length" in trust
    assert "projectedMechanisms.size !== candidateMechanisms.size" in trust
    assert "exactP19Control(value.p19_control, workspace)" in trust
    assert "workspace.learning_prior.car_response_history.some" in trust


def test_p351_learning_spine_is_learning_only_and_keeps_p19_as_sole_action() -> None:
    deck = (ROOT / "ui/src/components/CrewChiefCommandDeck.tsx").read_text(
        encoding="utf-8"
    )
    component = (ROOT / "ui/src/components/EngineeringKnowledgeSpine.tsx").read_text(
        encoding="utf-8"
    )
    learning_index = deck.index("{learning && (")
    spine_index = deck.index("<EngineeringKnowledgeSpine")

    assert spine_index > learning_index
    assert "<EngineeringKnowledgeSpine" not in deck[:learning_index]
    for heading in (
        "Why this system is relevant",
        "What it physically changes",
        "What the car is doing now",
        "What evidence is missing",
        "What would separate the candidates",
        "What history says",
        "NEXT · P19",
    ):
        assert heading in component
    assert "P19 ONLY FOR ACTION" in component
    assert "Driver report is a prior only" in component
    assert "Static possibility map" in component
    assert "none is supported yet" in component
    assert "onFocusEvidence(entry)" in component
    assert "onFocusEvidence(discriminatorFocus)" in component


def test_p351_dial_in_uses_shared_projection_and_only_mirrors_level_three() -> None:
    schema = (ROOT / "racelab_engine/knowledge/setup/dial_in_schema.py").read_text(
        encoding="utf-8"
    )
    tab = (ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    trust = (ROOT / "ui/src/utils/dialInResponseTrust.ts").read_text(
        encoding="utf-8"
    )
    client = (ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")

    assert '"measurable_hypothesis"' in schema
    assert '== "p19_testable_control"' in schema
    assert "Only the controlled " in schema
    assert "P19 workflow may authorize one exact setup target" in schema
    assert "knowledge_level" in tab
    assert "P19-testable control family" in tab
    assert "session_id: sessionId" in tab
    assert "same Crew / Engineer / P19 opportunity" in tab
    assert "isStandaloneEngineeringKnowledgeProjection" in trust
    assert "item.p19_control.proposed_value === p19TerminalDecision.proposed_value" in (
        ROOT / "ui/src/utils/engineeringKnowledgeTrust.ts"
    ).read_text(encoding="utf-8")
    assert "hasCanonicalEngineeringKnowledgeDigest" in client
