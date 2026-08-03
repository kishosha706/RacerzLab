from __future__ import annotations

from racelab_engine.analysis.comparison import SetupChange, TestDisciplineResult


def score_test_discipline(
    setup_changes: list[SetupChange],
    context_problems: int = 0,
    setup_groups_touched: int = 0,
    setup_data_available: bool = True,
) -> TestDisciplineResult:
    positive: list[str] = []
    negative: list[str] = []

    if not setup_data_available:
        return TestDisciplineResult(
            score=10,
            label="invalid",
            positive_factors=[],
            negative_factors=["One or both setup snapshots are unavailable; change attribution is unknown."],
            recommendation="Capture both setup snapshots before drawing a setup conclusion.",
        )

    exact_changes = len(setup_changes)
    groups = {c.group for c in setup_changes}
    setup_groups_touched = max(setup_groups_touched, len(groups))

    if exact_changes == 0 and setup_groups_touched == 0:
        score = 95
        label = "clean"
        positive.append("No driver-adjustable setup controls changed.")
    elif exact_changes == 0 and setup_groups_touched == 1:
        score = 88
        label = "clean"
        positive.append("One externally supplied setup group changed.")
    elif exact_changes == 0 and setup_groups_touched == 2:
        score = 68
        label = "mostly_clean"
        negative.append("Two externally supplied setup groups changed.")
    elif exact_changes == 0 and setup_groups_touched <= 3:
        score = 45
        label = "mixed"
        negative.append(f"{setup_groups_touched} externally supplied setup groups changed.")
    elif exact_changes == 1 and setup_groups_touched <= 1:
        score = 92
        label = "clean"
        positive.append(f"One setup control changed: {setup_changes[0].label}.")
    elif exact_changes == 2:
        score = 68
        label = "mostly_clean"
        negative.append("Two setup controls changed; attribution is reduced.")
    elif exact_changes == 3:
        score = 45
        label = "mixed"
        negative.append("Three setup controls changed; the cause cannot be isolated cleanly.")
    else:
        score = 20
        label = "weak"
        negative.append(f"{exact_changes} setup controls changed; attribution is not trustworthy.")

    if context_problems > 0:
        score = max(0, score - 15 * context_problems)
        negative.append(f"{context_problems} context problem(s) detected (weather, run length).")

    if score < 25:
        label = "invalid"
        negative.append("Too many uncontrolled variables for a valid comparison.")

    recommendation = None
    if label == "clean":
        recommendation = "Controlled setup scope. Continue only if lap and context evidence also pass."
    elif label == "mostly_clean":
        recommendation = "Comparison is usable, but try to limit to one change per test."
    elif label == "mixed":
        recommendation = "Retest with fewer setup changes or more controlled conditions."
    elif label in ("weak", "invalid"):
        recommendation = "Not reliable for setup conclusions. Repeat the test with one controlled variable."

    return TestDisciplineResult(
        score=score, label=label, positive_factors=positive,
        negative_factors=negative, recommendation=recommendation,
    )

