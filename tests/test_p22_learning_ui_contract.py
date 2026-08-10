from pathlib import Path


def test_p22_learning_operations_are_learning_only_and_use_no_new_workspace():
    root = Path(__file__).resolve().parents[1]
    engineer = (root / "ui/src/tabs/EngineerTab.tsx").read_text(encoding="utf-8")
    app = (root / "ui/src/App.tsx").read_text(encoding="utf-8")
    client = (root / "ui/src/api/client.ts").read_text(encoding="utf-8")
    imports = (root / "api/routes_imports.py").read_text(encoding="utf-8")
    controlled = (
        root / "racelab_engine/services/controlled_workflow_service.py"
    ).read_text(encoding="utf-8")
    assert "Today&apos;s test session" in engineer
    assert "RacerZLab Learning Ledger" in engineer
    assert "Advanced capability review" in engineer
    assert "Decision: REMAIN LOCKED" in engineer
    assert "onStartCampaign={startCampaign}" in engineer
    assert "/api/evaluation/campaign-operations/start" in client
    assert "/api/evaluation/prospective-predictions" in client
    assert "Freeze P19 prediction before B" in engineer
    assert "assess_active_operations_for_run" in imports
    assert "attach_matching_outcome_after_score" in controlled
    assert "learning && <LearningReadinessCard" in engineer
    assert "Learning Ledger" not in app


def test_p22_director_language_does_not_claim_information_gain_or_setup_authority():
    root = Path(__file__).resolve().parents[1]
    operations = (
        root / "racelab_engine/evaluation/learning_operations.py"
    ).read_text(encoding="utf-8")
    prospective = (
        root / "racelab_engine/evaluation/prospective.py"
    ).read_text(encoding="utf-8")
    assert 'formal_information_gain: Literal[False] = False' in operations
    assert 'authority: Literal["collection_guidance_only"]' in operations
    assert 'authority: Literal["data_collection_only"]' in operations
    assert 'authority: Literal["shadow_only"]' in prospective
    assert "P19 has not authorized one exact controlled setup test" in prospective
