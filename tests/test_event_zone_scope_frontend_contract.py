from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_null_position_event_clears_an_old_zone_before_dial_in() -> None:
    """A new event cannot inherit an earlier 10-20% zone without a position."""
    focus = _read("ui/src/utils/evidenceFocus.ts")
    reducer = _read("ui/src/store/TelemetrySelectionContext.tsx")
    dial = _read("ui/src/tabs/DialInTab.tsx")

    null_position_guard = focus.split("if (options?.lapPct == null) {", 1)[1].split("}", 1)[0]
    assert "zoneId: null" in null_position_guard
    assert "zoneLabel: null" in null_position_guard
    assert "zoneStartPct: null" in null_position_guard
    assert "zoneEndPct: null" in null_position_guard
    assert "preserveWithoutLapPct" not in focus

    focus_reducer = reducer.split('case "FOCUS_EVIDENCE":', 1)[1].split("default:", 1)[0]
    for field in ("zoneId", "zoneLabel", "zoneStartPct", "zoneEndPct"):
            assert f"ev.{field} ?? null" in focus_reducer

    decision_context = dial.split("const decisionContext = useMemo", 1)[1].split(
        "const currentRequestBinding",
        1,
    )[0]
    assert "selection.selectedZoneStartPct != null" in decision_context
    assert "selection.selectedZoneEndPct != null" in decision_context
    assert "selected_zone_start_pct: zoneIsForRun ? selection.selectedZoneStartPct : undefined" in decision_context
    assert "selected_zone_end_pct: zoneIsForRun ? selection.selectedZoneEndPct : undefined" in decision_context


def test_every_identity_changing_event_handoff_revalidates_zone_location() -> None:
    sources_and_calls = {
        "ui/src/components/PriorityRail.tsx": "buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null })",
        "ui/src/components/EventTimeline.tsx": "buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null })",
        "ui/src/hooks/useKeyboardShortcuts.ts": "buildZoneEvidence(selection, { lapPct: nextEvt.lap_pct ?? null })",
        "ui/src/components/EvidenceInspector.tsx": "buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null })",
        "ui/src/components/EvidenceCard.tsx": "buildZoneEvidence(selection, { lapPct })",
        "ui/src/tabs/PlatformTab.tsx": "buildZoneEvidence(selection, { lapPct })",
    }

    for path, expected_call in sources_and_calls.items():
        source = _read(path)
        assert expected_call in source
        assert "preserveWithoutLapPct" not in source


def test_platform_event_handoff_never_borrows_location_from_an_old_event() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    engineer_handoff = platform.split(
        "const handleOpenEngineerFromPlatformEvent",
        1,
    )[1].split("//", 1)[0]

    assert "const lapPct = event ? event.lap_pct ?? null : selection.selectedLapPct ?? null;" in engineer_handoff
    assert "const sampleIndex = event ? event.sample_index ?? null : selection.selectedSampleIndex ?? null;" in engineer_handoff
    assert "const lapDistFt = event ? event.lap_dist_ft ?? null : selection.selectedLapDistFt ?? null;" in engineer_handoff
    assert "event?.lap_pct ?? selection.selectedLapPct" not in engineer_handoff
    assert "event?.sample_index ?? selection.selectedSampleIndex" not in engineer_handoff
    assert "event?.lap_dist_ft ?? selection.selectedLapDistFt" not in engineer_handoff


def test_platform_zone_survives_only_at_a_proven_in_range_location() -> None:
    focus = _read("ui/src/utils/evidenceFocus.ts")
    zone_resolution = focus.split("export function buildZoneEvidence", 1)[1]

    assert "if (options?.lapPct == null)" in zone_resolution
    assert "lapPctInRange(options.lapPct, zoneContext.zoneStartPct, zoneContext.zoneEndPct)" in zone_resolution
    assert "? zoneContext" in zone_resolution
    assert ": { zoneId: null, zoneLabel: null, zoneStartPct: null, zoneEndPct: null }" in zone_resolution
