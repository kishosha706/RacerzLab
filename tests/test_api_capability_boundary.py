from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import api.main as main_module


CAPABILITY_TOKEN = "a7" * 32
CAPABILITY_HEADER = "X-RacerZLab-Capability"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _configure_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "racelab.sqlite"))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path / "data"))


@pytest.mark.parametrize("supplied", [None, "wrong-token"])
def test_configured_capability_rejects_missing_and_wrong_headers(
    monkeypatch: pytest.MonkeyPatch,
    supplied: str | None,
) -> None:
    monkeypatch.setenv("RACERZLAB_BACKEND_CAPABILITY_TOKEN", CAPABILITY_TOKEN)
    headers = {} if supplied is None else {CAPABILITY_HEADER: supplied}

    response = TestClient(main_module.app).get("/api/sessions", headers=headers)

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "Unauthorized."}
    assert CAPABILITY_TOKEN not in response.text
    assert supplied is None or supplied not in response.text


def test_configured_capability_accepts_constant_time_exact_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    comparisons: list[tuple[str, str]] = []
    real_compare = main_module.secrets.compare_digest

    def tracked_compare(supplied: str, expected: str) -> bool:
        comparisons.append((supplied, expected))
        return real_compare(supplied, expected)

    _configure_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("RACERZLAB_BACKEND_CAPABILITY_TOKEN", CAPABILITY_TOKEN)
    monkeypatch.setattr(main_module.secrets, "compare_digest", tracked_compare)

    client = TestClient(main_module.app)
    wrong = client.get(
        "/api/sessions",
        headers={CAPABILITY_HEADER: "b8" * 32},
    )
    response = client.get(
        "/api/sessions",
        headers={CAPABILITY_HEADER: CAPABILITY_TOKEN},
    )

    assert wrong.status_code == 401
    assert response.status_code == 200
    assert comparisons == [
        ("b8" * 32, CAPABILITY_TOKEN),
        (CAPABILITY_TOKEN, CAPABILITY_TOKEN),
    ]


def test_health_and_options_are_the_only_capability_exemptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("RACERZLAB_BACKEND_CAPABILITY_TOKEN", CAPABILITY_TOKEN)
    client = TestClient(main_module.app)

    health = client.get("/api/health")
    preflight = client.options(
        "/api/sessions",
        headers={
            "Origin": "tauri://localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": CAPABILITY_HEADER,
        },
    )
    protected = client.get("/api/sessions")

    assert health.status_code == 200
    assert CAPABILITY_TOKEN not in health.text
    assert preflight.status_code == 200
    assert protected.status_code == 401


def test_absent_capability_environment_preserves_browser_development(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("RACERZLAB_BACKEND_CAPABILITY_TOKEN", raising=False)

    response = TestClient(main_module.app).get("/api/sessions")

    assert response.status_code == 200


def test_shared_frontend_client_covers_notebook_without_direct_fetch() -> None:
    client = (PROJECT_ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")
    capability = (PROJECT_ROOT / "ui/src/api/localApiCapability.ts").read_text(
        encoding="utf-8"
    )
    notebook = (PROJECT_ROOT / "ui/src/tabs/NotebookTab.tsx").read_text(
        encoding="utf-8"
    )

    assert 'headers.set("X-RacerZLab-Capability", capabilityToken)' in client
    assert 'invoke<string>("backend_capability_token")' in capability
    assert 'import { requestJson } from "../api/client";' in notebook
    assert notebook.count("requestJson<NotebookFinding") == 3
    assert "fetch(" not in notebook
    assert "API_BASE" not in notebook
    assert "async function req" not in notebook
