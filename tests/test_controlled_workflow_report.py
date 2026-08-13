from __future__ import annotations

from datetime import datetime, timezone

from racelab_engine.analysis.crew_chief_packet import (
    CauseCandidate,
    OpportunityEvidence,
    build_kaizen_packet,
)
from racelab_engine.analysis.test_director import (
    TestEvidenceLink,
    TestExecution as Execution,
    TestQualityResult as QualityResult,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.reports.markdown_report import generate_controlled_workflow_report


def _workflow() -> ControlledWorkflow:
    link = TestEvidenceLink(
        event_id="entry-42",
        eligible_lap=True,
        valid_for_tuning=True,
        phase="entry",
        related_setup_keys=("cross_weight_percent",),
    )
    packet = build_kaizen_packet(
        opportunity=OpportunityEvidence(
            start_pct=22.0,
            end_pct=27.0,
            phase="entry",
            observed_time_loss_s=0.18,
            empirical_noise_s=0.04,
            alignment_confidence=0.94,
            repeatable=True,
            evidence_links=(link,),
            source_channels=("lap_dist_pct", "speed_mph", "steering_deg"),
            supporting_evidence=("The loss repeated on three eligible laps.",),
            contradictory_evidence=("Exit speed did not change.",),
        ),
        canonical_symptom="tight_entry",
        candidates=[CauseCandidate(
            cause_bucket="corner_balance",
            control_key="cross_weight_percent",
            direction_sign=1,
            score=0.82,
            hypothesis="Test whether one adjacent legal step improves entry rotation.",
            success_metrics=("Entry phase time improves beyond 0.04 s",),
            countereffects=("Exit speed must not worsen",),
            supporting_event_ids=("entry-42",),
        )],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={"cross_weight_percent": {"50.5": ["tech:run-b"]}},
    )
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    return ControlledWorkflow(
        workflow_id="aba-report",
        created_at=now,
        updated_at=now,
        status="scored",
        source_run_id="source-run",
        complaint="Won't rotate on entry",
        packet=packet,
        analysis_version="controlled-workflow-aba2-v2",
        stage_run_ids={"A": "run-a", "B": "run-b", "A2": "run-a2"},
        stage_eligible_lap_numbers={"A": (2, 3, 4), "B": (2, 3, 4), "A2": (2, 3, 4)},
        execution=Execution(
            eligible_laps_a=3,
            eligible_laps_b=3,
            eligible_laps_a2=3,
            unrelated_setup_changes=0,
            control_key="cross_weight_percent",
            planned_b_value=50.5,
            observed_a_value=50.0,
            observed_b_value=50.5,
            observed_a2_value=50.0,
            context_match_score=0.93,
            driver_match_score=0.91,
            sim_integrity_score=0.96,
            phase_effect_b_vs_a_s=-0.08,
            phase_effect_b_vs_a2_s=-0.07,
            empirical_noise_s=0.02,
            empirical_noise_observations=4,
            minimum_alignment_confidence=0.88,
            countereffect_noise_by_phase_s={"exit": 0.006},
            target_effect_distributions_consistent=True,
            target_effect_distribution_state="faster",
            control_guardrails_passed=True,
            control_guardrail_metrics={"yaw_rate_b": 0.12, "yaw_rate_baseline_limit": 0.15},
            countereffect_passed=True,
        ),
        quality=QualityResult(
            protocol_valid=True,
            score=91.0,
            verdict="keep",
            blockers=(),
            supporting_evidence=("B beat A and A2 beyond noise.",),
            contradictory_evidence=("One lap was near the confidence boundary.",),
            controlled_effect_eligible=True,
        ),
        learning_admitted=True,
        reproduction_snapshot={
            "analysis_code_and_config_sha256": "code-and-config-hash",
            "decision_context": {"objective": "race-pace", "priority": "entry-security"},
            "target_effect_distributions_s": {
                "b_vs_a": [-0.09, -0.08, -0.07],
                "b_vs_a2": [-0.08, -0.07, -0.06],
                "within_baseline_noise": [0.01, 0.02, 0.02, 0.03],
            },
            "countereffect_phase_distributions_s": {
                "exit": [0.001, -0.002, 0.003],
            },
            "countereffect_baseline_noise_distributions_s": {
                "exit": [0.004, 0.005, 0.006, 0.005],
            },
            "recording_chronology": {
                "source": {
                    "raw_session_time_start_s": 10.0,
                    "raw_session_time_end_s": 20.0,
                    "provenance": "file-declared session start plus archived SessionTime bounds",
                },
            },
            "stages": {
                "A": {
                    "run_id": "run-a",
                    "source_file_sha256": "file-a",
                    "schema_fingerprint": "schema-a",
                    "cache_version": 7,
                    "compatibility_identity": {"car_path": "car", "track_id_or_path": "track"},
                    "setup_fingerprint": "setup-a",
                    "setup_values": {"cross_weight_percent": 50.0},
                    "eligible_lap_numbers": [2, 3, 4],
                },
            },
        },
    )


def test_controlled_report_reproduces_persisted_evidence_identity_and_missingness() -> None:
    workflow = _workflow()
    markdown = generate_controlled_workflow_report(
        workflow,
        stage_overviews={"A": None, "B": None, "A2": None},
        manifests={
            "A": {
                "schema_fingerprint": "schema-a",
                "cache_version": 7,
                "health_summary": {"status": "healthy"},
                "compatibility_identity": {"car_path": "car", "track_id_or_path": "track"},
            },
        },
    )

    for expected in (
        "Workflow ID: aba-report",
        "Source run ID: source-run",
        "Analysis version: controlled-workflow-aba2-v2",
        "Recommendation score basis:",
        "Recommendation score components:",
        "Driver decision context:",
        "Source/A/B/A2 recording chronology:",
        "Position window: 22.000% to 27.000% lap",
        "Empirical noise: 0.04 s",
        "Evidence event IDs: entry-42",
        "Exact change:",
        "Run ID: run-a2",
        "Canonical eligible lap IDs used: 2, 3, 4",
        "File schema fingerprint: schema-a",
        "Verdict: keep",
        "B vs A target effect: -0.08 s",
        "Qualified empirical-noise observations: 4",
        "Minimum target alignment confidence: 0.88",
        "Lap-level target effects directionally consistent beyond noise: yes",
        "Lap-level target-effect state: faster",
        '"b_vs_a": [-0.09, -0.08, -0.07]',
        "Control-specific telemetry guardrails passed: yes",
        'Control-specific guardrail metrics: {"yaw_rate_b": 0.12, "yaw_rate_baseline_limit": 0.15}',
        'Countereffect noise thresholds by phase (s): {"exit": 0.006}',
        'Countereffect phase distributions (s): {"exit": [0.001, -0.002, 0.003]}',
        'Countereffect baseline-noise distributions (s): {"exit": [0.004, 0.005, 0.006, 0.005]}',
        "Durable setup-effect admission: yes",
        "Exit speed did not change.",
        "Missing evidence is printed as Unavailable",
    ):
        assert expected in markdown
    assert "exact aerodynamic drag" not in markdown.lower()


def test_workflow_report_route_is_registered() -> None:
    from api.main import app

    paths = app.openapi()["paths"]
    assert "/api/engineering/workflows/{workflow_id}/report" in paths
