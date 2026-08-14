from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from api.routes_intelligence import get_run_intelligence
from racelab_engine.services.crew_chief_service import build_crew_chief_workspace
from racelab_engine.services.session_service import get_session
from racelab_engine.storage.repository import RaceLabRepository

ROOT = Path(__file__).resolve().parents[1]


def test_crew_chief_runtime_guard_rejects_forged_authority() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the UI runtime contract test")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            str(ROOT / "ui/tests/crewChiefResponseTrust.runtime.test.mjs"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
def test_real_atlanta_public_workspace_passes_the_client_trust_boundary() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the real workspace client guard")
    run_id = "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb"
    session_id = "session_ed52db305244"
    if RaceLabRepository().get_overview(run_id) is None:
        pytest.skip("Persisted real Next Gen Atlanta fixture is unavailable")
    session = get_session(session_id)
    if session is None or run_id not in session.run_ids:
        pytest.skip("Persisted real Next Gen Atlanta session is unavailable")
    workspace = build_crew_chief_workspace(run_id, session_id=session_id)
    report = get_run_intelligence(run_id, session_id)
    payload = json.dumps(
        {
            "workspace": workspace.model_dump(mode="json"),
            "scope": {
                "runId": run_id,
                "sessionId": session_id,
                "report": report.model_dump(mode="json"),
                "scopeRunIds": list(session.run_ids),
                "objectiveId": workspace.identity.objective_id.value,
            },
        }
    )
    script = (
        "import fs from 'node:fs';"
        "import {isCrewChiefWorkspaceResponse} from "
        "'./ui/src/utils/crewChiefResponseTrust.ts';"
        "const value=JSON.parse(fs.readFileSync(0,'utf8'));"
        "if(!isCrewChiefWorkspaceResponse(value.workspace,value.scope))"
        "throw new Error('real Atlanta public workspace was rejected');"
    )
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            script,
        ],
        cwd=ROOT,
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_engineer_uses_one_atomic_command_deck_without_a_new_top_level_tab() -> None:
    engineer = (ROOT / "ui/src/tabs/EngineerTab.tsx").read_text(encoding="utf-8")
    deck = (ROOT / "ui/src/components/CrewChiefCommandDeck.tsx").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "ui/src/App.tsx").read_text(encoding="utf-8")
    assert "<CrewChiefCommandDeck" in engineer
    for label in (
        "NEXT · P19",
        "OBSERVED",
        "ATTRIBUTION",
        "STRONGEST CONTRADICTION",
    ):
        assert label in deck
    assert deck.index("NEXT · P19") < deck.index("OBSERVED")
    assert 'aria-label="Measured Speed Story"' in deck
    assert (
        "Mission ribbon" in deck and "Run sentinel" in deck and "Response atlas" in deck
    )
    assert '"crew_chief"' not in app
    assert "workspaceSequence.current" in deck
    assert "sequence === workspaceSequence.current" in deck
    assert "runId: entry.run_id" in engineer


def test_client_parses_crew_chief_as_unknown_through_exact_report_guard() -> None:
    client = (ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")
    block = client.split("export function fetchCrewChiefWorkspace", 1)[1].split(
        "export function openCrewChiefInvestigation", 1
    )[0]
    assert "requestJson<unknown>" in block
    assert "trustedCrewChiefResponse" in block
    guard = (ROOT / "ui/src/utils/crewChiefResponseTrust.ts").read_text(
        encoding="utf-8"
    )
    assert "reasoning_snapshot_sha256" in guard
    assert "setup_snapshot_sha256" in guard
    assert "hasSetupAuthorityDirective" in guard
