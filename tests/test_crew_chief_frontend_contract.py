from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_engineer_uses_one_atomic_command_deck_without_a_new_top_level_tab() -> None:
    engineer = (ROOT / "ui/src/tabs/EngineerTab.tsx").read_text(encoding="utf-8")
    deck = (ROOT / "ui/src/components/CrewChiefCommandDeck.tsx").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "ui/src/App.tsx").read_text(encoding="utf-8")
    assert "<CrewChiefCommandDeck" in engineer
    assert "WHAT" in deck and "UNCERTAIN" in deck and "NEXT" in deck
    assert (
        "Mission ribbon" in deck and "Run sentinel" in deck and "Response atlas" in deck
    )
    assert '"crew_chief"' not in app


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
