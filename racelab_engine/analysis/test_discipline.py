from __future__ import annotations

from racelab_engine.analysis.comparison import SetupChange, TestDisciplineResult


def score_test_discipline(
    setup_changes: list[SetupChange],
    context_problems: int = 0,
    setup_groups_touched: int = 0,
) -> TestDisciplineResult:
    positive: list[str] = []
    negative: list[str] = []

    if not setup_changes:
        positive.append("No setup changes detected — pure comparison.")
    else:
        groups = {c.group for c in setup_changes}
        setup_groups_touched = max(setup_groups_touched, len(groups))

    if setup_groups_touched == 0:
        score = 95
        label = "clean"
        positive.append("Zero setup groups changed.")
    elif setup_groups_touched == 1:
        score = 88
        label = "clean"
        positive.append("One setup group changed.")
    elif setup_groups_touched == 2:
        score = 75
        label = "mostly_clean"
        negative.append("Two setup groups changed.")
    elif setup_groups_touched <= 3:
        score = 50
        label = "mixed"
        negative.append(f"{setup_groups_touched} setup groups changed.")
    else:
        score = 30
        label = "weak"
        negative.append(f"{setup_groups_touched} setup groups changed — too many areas.")

    if context_problems > 0:
        score = max(0, score - 15 * context_problems)
        negative.append(f"{context_problems} context problem(s) detected (weather, run length).")

    if score < 25:
        label = "invalid"
        negative.append("Too many uncontrolled variables for a valid comparison.")

    recommendation = None
    if label == "clean":
        recommendation = "Good controlled test. The result is trustworthy."
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

