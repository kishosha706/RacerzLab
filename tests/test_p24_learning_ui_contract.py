from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_p24_campaign_progress_certificate_and_flight_recorder_are_learning_only():
    engineer = (ROOT / "ui" / "src" / "tabs" / "EngineerTab.tsx").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    client = (ROOT / "ui" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    assert "P23 steering workload campaign" in engineer
    assert "Latest session certificate" in engineer
    assert "latest_flight_recorder" in engineer
    assert "latest_flight_recorder_truncated" in engineer
    assert "No qualification certificate yet" in engineer
    assert 'aria-label="P23 evidence gates"' in engineer
    assert "Certificate-owned admission" in engineer
    assert "Exact qualification blockers" in engineer
    assert "latest_telemetry_ownership_state" in engineer
    assert "P23 steering workload / null session 01" in engineer
    assert "latest_null_run_card" in engineer
    assert "P23 steering workload campaign" not in app
    assert "learning &&" in engineer
    assert "LEARNING_READINESS_TIMEOUT_MS" in client
    assert "never blocks Race Mode or cockpit open" in client


def test_p24_routes_are_server_owned_and_expose_no_activation_control():
    routes = (ROOT / "api" / "routes_evaluation.py").read_text(encoding="utf-8")
    imports = (ROOT / "api" / "routes_imports.py").read_text(encoding="utf-8")
    assert '"/p23-pre-run-checklist"' in routes
    assert '"/p23-collection-templates"' in routes
    assert '"/p23-negative-control-expectations"' in routes
    assert '"/p23-negative-control-recipes"' in routes
    assert '"/p23-qualification-certificates"' in routes
    assert '"/p25-null-session-run-card"' in routes
    assert "limit: int = Query(default=50, ge=1, le=200)" in routes
    assert "qualify_p23_operations_for_run" in imports
    assert "activate" not in routes.casefold()


def test_p24_negative_control_catalog_and_certificate_limit_are_typed_api_contracts():
    client = TestClient(app)
    recipes = client.get("/api/evaluation/p23-negative-control-recipes")
    assert recipes.status_code == 200
    assert len(recipes.json()) == 13
    assert all(item["authority"] == "expectation_template_only" for item in recipes.json())
    invalid_limit = client.get("/api/evaluation/p23-qualification-certificates?limit=0")
    assert invalid_limit.status_code == 422
