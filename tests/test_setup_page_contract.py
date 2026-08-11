from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_setup_page_hides_noisy_corner_fields_from_default_view() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    assert "Shock Collar" not in setup
    assert "shock_collar_offset_mm" not in setup
    assert "Rear Caster" not in setup
    assert 'const frontCorner = corner === "lf" || corner === "rf";' in setup
    assert '{frontCorner && <Field l="Caster" v={caster} u="deg" relevant={relevant("caster_deg", "caster")} />}' in setup


def test_setup_page_hides_low_value_diff_side_fields_from_default_view() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    diff_block = setup.split('className="gr-card setup-system-card setup-system-diff"', 1)[1].split("</div>\n        </div>", 1)[0]
    assert "Diff Preload" in diff_block
    assert "Rear End Ratio" in diff_block
    assert "Drive Side" not in diff_block
    assert "Coast Side" not in diff_block
    assert "diff_drive_side" not in diff_block
    assert "diff_coast_side" not in diff_block


def test_setup_page_surfaces_key_system_cards_before_corner_tables() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    system_row = setup.split('{/* 2) High-value setup systems */}', 1)[1].split('{/* 3) 2x2 Corner Board */}', 1)[0]
    assert "Steering / Control" in system_row
    assert "Balance" in system_row
    assert "ARB" in system_row
    assert "Diff" in system_row
    assert "setup-system-steering" in system_row
    assert "setup-system-balance" in system_row
    assert "setup-system-arb" in system_row
    assert "setup-system-diff" in system_row
    assert system_row.index("Steering / Control") < setup.index('{/* 3) 2x2 Corner Board */}')


def test_setup_page_uses_unambiguous_driver_control_names() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    assert 'label: "Front Brake Bias"' in setup
    assert 'label: "Rear End Ratio"' in setup
    assert 'label: "Tape / Cooling"' in setup
    assert 'label: "Steering Ratio / Pinion"' in setup
    assert 'displayRatio.toLowerCase().includes("mm/rev")' in setup
    assert '? "Steering Pinion"' in setup


def test_setup_page_consumes_corner_weight_as_newtons_not_mass() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    assert 'evCorner(setup, corner, "corner_weight_n")' in setup
    assert 'evCorner(setup, "lf", "corner_weight_n")' in setup
    assert "corner_weight_kg" not in setup


def test_setup_page_uses_full_width_garage_layout_and_distinct_system_colours() -> None:
    styles = _read("ui/src/styles.css")

    garage_block = styles.split(".garage-board {", 1)[1].split("}", 1)[0]
    top_row_block = styles.split(".gr-toprow {", 1)[1].split("}", 1)[0]
    corners_block = styles.split(".gr-corners {", 1)[1].split("}", 1)[0]

    assert "width: 100%" in garage_block
    assert "max-width: none" in garage_block
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in top_row_block
    assert "width: 100%" in top_row_block
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in corners_block
    assert ".setup-system-steering" in styles
    assert ".setup-system-balance" in styles
    assert ".setup-system-arb" in styles
    assert ".setup-system-diff" in styles


def test_setup_values_use_dash_for_unavailable_and_muted_units() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")
    styles = _read("ui/src/styles.css")

    assert 'missing ? "—"' in setup
    assert '<span className="gr-value" role="cell">{missing ? "—" : v}</span>' in setup
    assert 'className="gr-value-unit"' in setup
    assert ".gr-value-unit" in styles
    assert ".gr-row.missing .gr-value" in styles


def test_setup_rows_align_label_value_and_unit_columns() -> None:
    styles = _read("ui/src/styles.css")

    row_block = styles.split(".gr-row {", 1)[1].split("}", 1)[0]
    value_block = styles.split(".gr-value {", 1)[1].split("}", 1)[0]
    unit_block = styles.split(".gr-value-unit {", 1)[1].split("}", 1)[0]

    assert "display: grid" in row_block
    assert "grid-template-columns: minmax(118px, 1fr) minmax(68px, max-content) minmax(44px, max-content)" in row_block
    assert "align-items: baseline" in row_block
    assert "text-align: right" in value_block
    assert 'font-feature-settings: "tnum"' in value_block
    assert "font-variant-numeric: tabular-nums" in value_block
    assert "min-width: 44px" in unit_block
    assert "text-align: left" in unit_block


def test_setup_page_uses_axle_oriented_two_by_two_corner_board() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")
    styles = _read("ui/src/styles.css")

    corners = setup.split('{/* 3) 2x2 Corner Board */}', 1)[1].split('{/* 5) Related Evidence Links */}', 1)[0]
    assert 'className="gr-axle-label front"' in corners
    assert 'className="gr-axle-label rear"' in corners
    assert corners.index('corner="lf"') < corners.index('corner="rf"') < corners.index('corner="lr"') < corners.index('corner="rr"')
    assert 'aria-label="Setup by car corner"' in corners
    assert ".gr-axle-label" in styles


def test_setup_defaults_to_diff_only_for_a_real_distinct_available_baseline() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    assert "const hasValidBaselineComparison = Boolean(" in setup
    assert "basket.baseline.has_setup_snapshot" in setup
    assert "!basket.baseline.stale" in setup
    assert "basket.baseline.run_id !== overview.run_id" in setup
    assert 'useState<"current" | "diff">(hasValidBaselineComparison ? "diff" : "current")' in setup
    assert 'if (comparisonKey && comparisonKey !== defaultedComparisonKeyRef.current)' in setup
    assert 'setDiffMode("diff")' in setup
    assert 'else if (!comparisonKey && defaultedComparisonKeyRef.current)' in setup
    assert 'setDiffMode("current")' in setup
    assert 'onClick={() => setDiffMode("current")}' in setup


def test_setup_highlights_only_explicit_evidence_linked_controls() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "selectedEvent?.related_setup_keys" in setup
    assert "isEvidenceLinkedControl" in setup
    assert 'data-evidence-linked={relevant ? "true" : undefined}' in setup
    assert "Evidence-linked" in setup
    assert '.gr-row.evidence-linked' in styles
    assert '.setup-system-card[data-evidence-relevant="true"]' in styles
    assert 'window.sessionStorage.setItem("racelab_setup_evidence_focus"' in platform
    assert 'related_setup_keys: []' in platform
    assert 'handoff.run_id !== overview.run_id || handoff.event_id !== selection.selectedEventId' in setup
    assert 'data-evidence-context=' in setup
    assert '.setup-system-card[data-evidence-context="true"]' in styles
