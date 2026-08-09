from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_corner_cycle_board_uses_only_exact_typed_evidence() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    assert "Corner-cycle crew board" in cards
    assert "Entry → center → exit → carry" in cards
    assert 'data-authority="read-only-synthesis"' in cards
    assert "observation.run_id === report.run_id" in cards
    assert 'observation.authority === "observation_only"' in cards
    assert "observation.qualified" in cards
    assert "observation.blocker_reasons.length === 0" in cards
    assert "signature.run_id === report.run_id" in cards
    assert 'signature.evidence_state === "observed_correlation"' in cards
    assert "signature.repetition_count >= 2" in cards
    assert "signature.median_opportunity_s > signature.empirical_noise_s" in cards
    assert 'report.driver_focus.authority === "driver_coaching_only"' in cards
    assert "driverFocus.focus.setup_authorized === false" in cards
    assert "citation.run_id === report.run_id" in cards


def test_corner_cycle_board_keeps_phase_change_and_next_check_truthful() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    phase_mapper = cards.split("function ovalCrewPhase", 1)[1].split(
        "function exactOvalMechanismObservations", 1
    )[0]
    for typed_phase in (
        "brake_application",
        "threshold_braking",
        "brake_release",
        "turn_in",
        "entry",
        "center",
        "apex_region",
        "initial_throttle",
        "full_throttle_exit",
        "straight",
        "following_straight_carry",
    ):
        assert f'"{typed_phase}"' in phase_mapper
    assert "lap_pct" not in phase_mapper
    assert "metadata" not in phase_mapper

    assert "entry.test_run_id === report.run_id" in cards
    assert "No evidence-qualified current-run change is published." in cards
    assert "causal attribution withheld" in cards
    assert 'move.authority === "setup_authorized"' in cards
    assert "Exact controlled-test target stays in Dial-In." in cards
    assert "Navigation only · no setup change" in cards
    assert "No setup direction is created here" in cards
    assert "telemetry samples are not counted as independent experiments" in cards
    assert 'observation.evidence_state === "estimated_proxy"' in cards
    assert 'observation.mechanism === "resistance_scrub_like"' in cards
    assert "no aerodynamic force or coefficient is measured" in cards


def test_platform_corner_checkpoint_is_a_single_sample_not_a_phase_inference() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    checkpoint = platform.split("function PlatformOvalCheckpoint", 1)[1].split(
        "/** Find the trace sample index", 1
    )[0]
    assert 'data-authority="measurement-only"' in checkpoint
    assert 'data-location-basis="single-sample"' in checkpoint
    assert 'valueAt(trace, "brake_pct", sampleIndex)' in checkpoint
    assert 'valueAt(trace, "steering_deg", sampleIndex)' in checkpoint
    assert 'valueAt(trace, "abs_steering_deg", sampleIndex)' in checkpoint
    assert 'valueAt(trace, "throttle_pct", sampleIndex)' in checkpoint
    assert 'valueAt(trace, "speed_mph", sampleIndex)' in checkpoint
    assert "The crew labels are checkpoints, not detected corner phases." in checkpoint
    assert "Single-sample context cannot grade timing or repeatability." in checkpoint
    assert "Engineer compares eligible same-setup laps at physical position." in checkpoint
    assert "event?.is_proxy_based" in checkpoint
    assert "Proxy evidence only." in checkpoint
    assert "aerodynamic force, coefficient, or vehicle cause" in checkpoint
    assert "lap_pct" not in checkpoint

    render = platform.split("<PlatformOvalCheckpoint", 1)[1].split("/>", 1)[0]
    assert "sampleIndex={localFocusIndex}" in render
    assert "event={focusedPlatformEvent}" in render
    assert "handleOpenEngineerFromPlatformEvent(focusedPlatformEvent)" in render


def test_smart_engineer_renders_corner_board_inside_exact_report_scope() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    assert "<SmartIntelligenceCards" in engineer
    assert "report={report}" in engineer
    assert "runId={runId}" in engineer
    assert "sessionId={sessionId}" in engineer
    assert "<OvalCrewBoard report={report} ledger={ledger} move={move} learning={learning} />" in cards
    assert "const ledger = exactSessionLedger(report.session_ledger, sessionId);" in cards
    assert "trustedNavigationMove(candidateMove, runId, workflowRevision)" in cards
    assert "trustedSetupAuthorizedMove(" in cards


def test_corner_cycle_and_checkpoint_collapse_without_clipping() -> None:
    styles = _read("ui/src/styles.css")
    oval_styles = styles.split(
        "/* Oval crew-chief synthesis and exact-position checkpoint */", 1
    )[1]

    for selector in (
        ".engineer-oval-crew-board",
        ".oval-crew-phase-strip",
        ".oval-crew-repeatability",
        ".oval-crew-change-grid",
        ".platform-oval-checkpoint",
        ".platform-oval-checkpoint-grid",
        ".platform-oval-checkpoint-evidence",
    ):
        assert selector in oval_styles
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in oval_styles
    assert "@media (max-width: 1280px)" in oval_styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in oval_styles
    assert "@media (max-width: 700px)" in oval_styles
    assert "grid-template-columns: 1fr;" in oval_styles
    assert "min-width: 0;" in oval_styles
