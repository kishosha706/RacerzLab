from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_p23_is_learning_only_and_has_no_authority_controls():
    engineer = (ROOT / "ui" / "src" / "tabs" / "EngineerTab.tsx").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "P23 first earned capability" in engineer
    assert "No activation earned" in engineer
    assert "P19/P20 authority unchanged" in engineer
    assert "first_activation_audit" in engineer
    assert "P23 first earned capability" not in app
    assert "activateCapability" not in engineer
    assert "manualActivation" not in engineer


def test_p23_audit_route_and_readiness_projection_are_server_owned():
    routes = (ROOT / "api" / "routes_evaluation.py").read_text(encoding="utf-8")
    readiness = (
        ROOT / "racelab_engine" / "evaluation" / "readiness.py"
    ).read_text(encoding="utf-8")
    assert '"/first-activation-audit"' in routes
    assert "build_first_activation_audit()" in routes
    assert "first_activation_audit=first_activation" in readiness
    assert "p23:first_activation" in readiness
