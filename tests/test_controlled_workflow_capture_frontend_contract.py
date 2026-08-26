from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_controlled_workflow_capture_contract_is_runtime_hostile() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the workflow capture runtime contract")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            str(ROOT / "ui/tests/controlledWorkflowTrust.runtime.test.mjs"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_full_workflow_api_reads_cross_the_capture_trust_boundary() -> None:
    client = (ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")
    trust = (ROOT / "ui/src/utils/controlledWorkflowTrust.ts").read_text(
        encoding="utf-8"
    )
    types = (ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")

    for field in (
        "learning_capture_state",
        "learning_capture_experience_id",
        "learning_capture_experience_sha256",
        "learning_capture_blocker_reason",
    ):
        assert field in types
        assert field in trust
    # Standalone workflow reads cross the full-workflow validator directly;
    # case-mutating reads cross the stricter workflow + successor-case wrapper.
    assert client.count("trustedControlledWorkflow(response)") == 1
    assert client.count("trustedControlledWorkflowMutation(response, {") == 3
    assert "const trustedWorkflow = isControlledWorkflowResponse(response.workflow)" in client
    assert 'schema: "controlled-workflow-revision.v2"' in client
    assert "response.workflow_revision_sha256 !== exactWorkflowRevision" in client
    assert "response.every(isControlledWorkflowResponse)" in client
    assert "requestJson<unknown>(`/api/engineering/workflows?${params.toString()}`)" in client
    assert 'requestJson<unknown>("/api/engineering/workflows"' not in client
    assert "P33 capture-containment check" in client
