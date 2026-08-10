from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_p24_campaign_progress_certificate_and_flight_recorder_are_learning_only():
    engineer = (ROOT / "ui" / "src" / "tabs" / "EngineerTab.tsx").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "P23 steering workload campaign" in engineer
    assert "Latest session certificate" in engineer
    assert "latest_flight_recorder" in engineer
    assert "Certificate-owned admission" in engineer
    assert "P23 steering workload campaign" not in app
    assert "learning &&" in engineer


def test_p24_routes_are_server_owned_and_expose_no_activation_control():
    routes = (ROOT / "api" / "routes_evaluation.py").read_text(encoding="utf-8")
    imports = (ROOT / "api" / "routes_imports.py").read_text(encoding="utf-8")
    assert '"/p23-pre-run-checklist"' in routes
    assert '"/p23-collection-templates"' in routes
    assert '"/p23-negative-control-expectations"' in routes
    assert '"/p23-qualification-certificates"' in routes
    assert "qualify_p23_operations_for_run" in imports
    assert "activate" not in routes.casefold()
