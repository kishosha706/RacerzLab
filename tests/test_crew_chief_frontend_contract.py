from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from api.routes_intelligence import get_run_intelligence
from racelab_engine.identity import canonical_json_sha256
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
@pytest.mark.parametrize(
    ("run_id", "session_id"),
    (
        (
            "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb",
            "session_ed52db305244",
        ),
        (
            "554cd5018d6248f9b28ce39811102a56-stockcars-chevy-3e347305",
            "session_bce98a1e008e",
        ),
    ),
)
def test_real_atlanta_public_workspace_passes_the_client_trust_boundary(
    run_id: str,
    session_id: str,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the real workspace client guard")
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
        "import {hasCanonicalMeasurementMissionDigest} from "
        "'./ui/src/utils/crewChiefResponseTrust.ts';"
        "import {hasCanonicalRunSentinelDigest} from "
        "'./ui/src/utils/crewChiefResponseTrust.ts';"
        "import {hasCanonicalEngineeringLearningDigests} from "
        "'./ui/src/utils/engineeringLearningTrust.js';"
        "const value=JSON.parse(fs.readFileSync(0,'utf8'));"
        "if(!isCrewChiefWorkspaceResponse(value.workspace,value.scope))"
        "throw new Error('real Atlanta public workspace was rejected');"
        "if(!await hasCanonicalEngineeringLearningDigests(value.workspace.learning_prior))"
        "throw new Error('real Atlanta P33 digests were rejected');"
        "if(!await hasCanonicalMeasurementMissionDigest(value.workspace.p19_mission_contract))"
        "throw new Error('real Atlanta P19 mission digest was rejected');"
        "if(!await hasCanonicalRunSentinelDigest(value.workspace.run_sentinel,value.workspace.identity.run_sentinel_sha256))"
        "throw new Error('real Atlanta mission progress digest was rejected');"
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
    assert "Mission ribbon" in deck and "Run sentinel" in deck
    assert "ENGINEERING MEMORY" in deck and "Learning ledger" in deck
    assert "Performance history" not in deck and "Response atlas" not in deck
    assert '"crew_chief"' not in app
    assert "workspaceSequence.current" in deck
    assert "sequence === workspaceSequence.current" in deck
    assert "onNavigateCrewEvidence(entry)" in engineer
    assert "runId: sourceRunId" in app


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
    assert "learning_history_revision" in guard
    assert "learning_projection_sha256" in guard
    assert "isCrewChiefLearningPrior" in guard
    assert 'value.schema_version !== "p33.crew-chief-workspace.v2"' in guard
    assert "hasSetupAuthorityDirective" in guard
    assert "hasCanonicalEngineeringLearningDigests" in client
    assert "await hasCanonicalEngineeringLearningDigests(payload.learning_prior)" in client
    assert "hasCanonicalMeasurementMissionDigest" in client
    assert "await hasCanonicalMeasurementMissionDigest(payload.p19_mission_contract)" in client
    assert "hasCanonicalRunSentinelDigest" in client
    assert "payload.identity.run_sentinel_sha256" in client


def test_crew_history_navigation_loads_the_saved_source_before_focusing() -> None:
    app = (ROOT / "ui/src/App.tsx").read_text(encoding="utf-8")
    navigator = app.split("const openCrewChiefEvidence", 1)[1].split(
        "// ── import", 1
    )[0]
    assert '"provenance" in target' in navigator
    assert "provenance?.session_id" in navigator
    assert "currentSession?.session_id === sourceSessionId" in navigator
    assert "!attachedSessionRunIds.has(sourceRunId)" in navigator
    assert "await fetchSession(sourceSessionId)" in navigator
    assert "!sourceSession.run_ids.includes(sourceRunId)" in navigator
    assert "handleSessionSelected(sourceSessionId, \"existing\", sourceRunId)" in navigator
    assert "await loadSelectedRun(sourceRunId)" in navigator
    assert navigator.index("await fetchSession(sourceSessionId)") < navigator.index(
        "handleSessionSelected(sourceSessionId"
    )
    assert "await fetchRunIntelligence(sourceRunId" in navigator
    assert "await canonicalJsonSha256(runtimeIdentity)" in navigator
    assert "sourceReport.setup_snapshot_sha256 !== sourceSetupHash" in navigator
    assert "runtimeHash === null" in navigator
    assert "runtimeHash !== sourceBuildHash" in navigator
    assert navigator.index("await fetchRunIntelligence(sourceRunId") < navigator.index(
        "handleSessionSelected(sourceSessionId"
    )
    assert navigator.index("handleSessionSelected(sourceSessionId") < navigator.index("focusEvidence({")
    assert navigator.index("await loadSelectedRun(sourceRunId)") < navigator.index("focusEvidence({")
    assert 'lapScope: hasWindow ? "track_zone"' in navigator
    assert 'valueBasis: hasWindow ? "selected_window"' in navigator
    assert "producerId," in navigator
    assert "artifactId," in navigator
    assert "sourceSetupId," in navigator

    session_loader = app.split("const handleSessionSelected", 1)[1].split(
        "const openCrewChiefEvidence", 1
    )[0]
    assert "exactRunId && !session.run_ids.includes(exactRunId)" in session_loader
    assert "exactRunId ?? session.run_ids[session.run_ids.length - 1]" in session_loader


def test_legacy_unvalidated_context_memory_is_not_rendered() -> None:
    engineer = (ROOT / "ui/src/tabs/EngineerTab.tsx").read_text(encoding="utf-8")
    assert "Worked here before" not in engineer
    assert "match.outcome_summary" not in engineer
    assert "Context-memory sources" not in engineer


def test_p33_learning_projection_has_one_exact_deep_client_mirror() -> None:
    types = (ROOT / "ui/src/types/engineeringLearning.ts").read_text(
        encoding="utf-8"
    )
    trust = (ROOT / "ui/src/utils/engineeringLearningTrust.js").read_text(
        encoding="utf-8"
    )
    deck = (ROOT / "ui/src/components/CrewChiefCommandDeck.tsx").read_text(
        encoding="utf-8"
    )
    for field in (
        "recurrence",
        "useful_prior_investigations",
        "known_dead_ends",
        "driver_tendencies",
        "car_response_history",
        "mind_change_history",
        "recommended_attention_order",
        "context_transfers",
        "evidence_references",
        "ledger",
        "post_run_brief",
        "blocker_reasons",
        "context_transfer_level",
        "strength",
    ):
        assert field in types
        assert field in trust
    for authority_boundary in (
        'value.authority !== "attention_only"',
        "value.setup_authorized !== false",
        "value.p19_rank_modified !== false",
        "claims_lap_time_improvement === false",
    ):
        assert authority_boundary in trust
    assert "exactKeys" in trust
    assert "UNSAFE_MEMORY_PROSE" in trust
    assert 'learningReference?.state === "unavailable"' in (
        ROOT / "ui/src/App.tsx"
    ).read_text(encoding="utf-8")
    assert "Open source" in deck
    assert "evidenceSourceLabel(reference.provenance)" in deck
    assert "Technical provenance:" in deck
    assert 'entry.producer_id !== "p33.engineering_experience"' in deck
    assert '.crew-chief-deck[data-mode="race"] .crew-chief-race-brief' in (
        ROOT / "ui/src/styles.css"
    ).read_text(encoding="utf-8")
    assert "Historical evidence must be opened from its typed Engineering Memory" in (
        ROOT / "ui/src/App.tsx"
    ).read_text(encoding="utf-8")


def test_crew_investigation_opening_truth_has_an_exact_deep_client_mirror() -> None:
    types = (ROOT / "ui/src/types/crewChief.ts").read_text(encoding="utf-8")
    trust = (ROOT / "ui/src/utils/crewChiefResponseTrust.ts").read_text(
        encoding="utf-8"
    )
    learning_trust = (
        ROOT / "ui/src/utils/engineeringLearningTrust.js"
    ).read_text(encoding="utf-8")
    for field in (
        "workspace_identity",
        "opening_reasoning",
        "opening_problem",
    ):
        assert field in types
        assert field in trust
    assert "validWorkspaceIdentityShape(value.workspace_identity)" in trust
    assert "isP19ReasoningMemory(value.opening_reasoning)" in trust
    assert "isProblemFingerprint(value.opening_problem)" in trust
    assert "openingProblem.objective === value.objective" in trust
    assert "openingReasoning.reasoning_snapshot_sha256" in trust
    assert "validProblemFingerprint" in learning_trust


def test_historical_build_identity_uses_the_canonical_repository_digest() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the canonical client digest test")
    value = {
        "run_id": "run-history",
        "car_path": "stockcars chevycamarozl1 2022",
        "track_configuration_name": "São Paulo 🏁",
        "available_telemetry_channels": ["speed_mps", "brake_pct"],
        "source": "verified_telemetry_artifact",
    }
    script = (
        "import fs from 'node:fs';"
        "import {canonicalJsonSha256} from './ui/src/utils/canonicalJsonSha256.ts';"
        "console.log(await canonicalJsonSha256(JSON.parse(fs.readFileSync(0,'utf8'))));"
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
        input=json.dumps(value),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == canonical_json_sha256(value)


def test_p33_client_digest_matches_python_float_serialization() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the canonical P33 digest test")
    value = {
        "nested": {
            "elapsed_seconds": 1.0,
            "lap_pct_start": -0.0,
            "lap_pct_end": 1e-6,
            "phase_time_effect_s": 1e20,
            "carry_effect_s": 0.125,
        },
        "integer_count": 1,
    }
    script = (
        "import fs from 'node:fs';"
        "import {canonicalEngineeringLearningSha256} from "
        "'./ui/src/utils/engineeringLearningTrust.js';"
        "console.log(await canonicalEngineeringLearningSha256("
        "JSON.parse(fs.readFileSync(0,'utf8'))));"
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
        input=json.dumps(value),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == canonical_json_sha256(value)
