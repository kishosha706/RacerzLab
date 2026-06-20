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
    assert '{frontCorner && <Field l="Caster" v={caster} u="deg" />}' in setup


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
