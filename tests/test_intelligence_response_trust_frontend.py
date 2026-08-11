from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_public_memory_and_narrative_do_not_duplicate_policy_authority() -> None:
    from api.intelligence_schemas import (
        IntelligenceContextMatchResponse,
        IntelligenceNarrativeEntryResponse,
    )

    engineer = (ROOT / "ui/src/tabs/EngineerTab.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    assert "verdict" not in IntelligenceContextMatchResponse.model_fields
    assert "outcome" not in IntelligenceNarrativeEntryResponse.model_fields
    assert "match.verdict" not in engineer
    assert "entry.outcome" not in engineer
    assert "engineer-memory-verdict" not in styles
    assert "engineer-narrative-outcome" not in styles


def test_every_run_intelligence_consumer_inherits_the_identity_guard() -> None:
    client = (ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")
    fetch = client.split("export function fetchRunIntelligence", 1)[1].split(
        "export function fetchVehicleSystems", 1
    )[0]

    assert "requestJson<unknown>" in fetch
    assert "isRunIntelligenceResponse(payload" in fetch
    assert "sessionId: options?.sessionId ?? null" in fetch


def test_intelligence_runtime_guards_reject_stale_and_forged_payloads() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the UI runtime contract test")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            str(ROOT / "ui/tests/intelligenceResponseTrust.runtime.test.mjs"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_dial_in_runtime_guard_rejects_action_bearing_hypotheses() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the UI runtime contract test")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            str(ROOT / "ui/tests/dialInResponseTrust.runtime.test.mjs"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_runtime_guard_covers_every_current_p26_setup_setting_label() -> None:
    from racelab_engine.services import vehicle_systems_service

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the UI runtime contract test")
    component_specs = getattr(vehicle_systems_service, "_COMPONENT_SETTING_SPECS")
    setting_names = sorted({
        name
        for specs in component_specs.values()
        for path, label, _unit, _decimals in specs
        for name in (path, label)
    })
    module_uri = (ROOT / "ui/src/utils/setupAuthorityLanguage.js").resolve().as_uri()
    script = f"""
import {{ hasSetupAuthorityDirective }} from {json.dumps(module_uri)};
const settingNames = {json.dumps(setting_names)};
const missed = settingNames.flatMap((name) => [
  `Set ${{name}} to 17.5.`,
  `${{name}}: 17.5.`,
]).filter((value) => !hasSetupAuthorityDirective(value));
if (missed.length > 0) {{
  throw new Error(`Uncovered setup authority labels: ${{missed.join(" | ")}}`);
}}
"""
    result = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_dial_in_client_parses_unknown_through_the_runtime_guard() -> None:
    client = (ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")
    fetch = client.split("export function analyzeRunDialIn", 1)[1].split(
        "export function startControlledWorkflow", 1
    )[0]

    assert "requestJson<unknown>" in fetch
    assert "isDialInHypothesisResponse(response" in fetch
