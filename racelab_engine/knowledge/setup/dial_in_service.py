from __future__ import annotations

from typing import Any

from .dial_in_schema import Clarification, DialInResponse, DialInSwing, HiddenEvidenceSummary
from .display_labels import DIAL_IN_STRENGTH_LABELS, format_target_label
from .evidence_adapter import build_run_evidence_context, query_setup_for_run_context
from .loader import load_setup_knowledge
from .matcher import RankedSetupEffect, parse_symptom


RISK_LABELS = {
    "low": "Low risk",
    "medium": "Medium risk",
    "high": "High risk",
}
CANDIDATE_READINESS_LABELS = {
    "ready": "Data profile clean",
    "partially_ready": "Data profile partial",
    "missing_key_evidence": "Need cleaner data",
}
GENERIC_COMPLAINTS = {"loose", "tight", "push", "free", "bad", "weird", "off"}
GENERIC_CLARIFICATION_QUESTION = "Where is it happening?"
GENERIC_CLARIFICATION_OPTIONS = ["Entry", "Center", "Exit", "Whole corner", "On brake", "On throttle"]


def _normalize_complaint(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _balance_label(value: str | None) -> str | None:
    return value.replace("_", " ") if value else None


def _confidence_label(complaint: str, *, needs_clarification: bool, supported: bool) -> str:
    if not supported:
        return "Unsupported"
    if needs_clarification and _normalize_complaint(complaint) in GENERIC_COMPLAINTS:
        return "Needs phase"
    if needs_clarification:
        return "Needs clarification"
    return "Clear read"


def _evidence_status_hint(context_warnings: list[str], *, baseline_run_id: str | None, test_run_id: str | None) -> str | None:
    if baseline_run_id:
        return "Compare baseline is missing."
    if test_run_id:
        return "Compare test run is missing."
    for warning in context_warnings:
        lower = warning.lower()
        if "car family could not be resolved" in lower:
            return "Car family is still generic."
        if "track family could not be resolved" in lower:
            return "Track family is still generic."
    return None


def _readiness_label(candidate_readiness: list[str], *, missing_hint: str | None) -> str:
    if not candidate_readiness:
        return "Need cleaner data"
    if all(item == "ready" for item in candidate_readiness) and not missing_hint:
        return "Data profile looks clean"
    if all(item == "missing_key_evidence" for item in candidate_readiness):
        return "Need cleaner data"
    return "Data profile is partial"


def _is_major_package_swing(effect: RankedSetupEffect) -> bool:
    return effect.effect.exact_value_policy == "reference_only" or effect.effect.effect_strength >= 5


def _filter_swings(candidates: list[RankedSetupEffect], limit: int) -> list[RankedSetupEffect]:
    selected: list[RankedSetupEffect] = []
    major_package_count = 0
    for item in candidates:
        if len(selected) >= limit:
            break
        if _is_major_package_swing(item):
            if major_package_count >= 1:
                continue
            major_package_count += 1
        selected.append(item)
    return selected


def _build_swing(item: RankedSetupEffect, *, include_debug_evidence: bool) -> DialInSwing:
    debug: dict[str, Any] | None = None
    if include_debug_evidence:
        debug = {
            "readiness": item.readiness,
            "evidence_present": item.evidence_matched,
            "evidence_missing": item.missing_evidence,
            "ranking_reasons": item.ranking_reasons,
            "score": round(item.score, 3),
        }
    return DialInSwing(
        id=item.effect.effect_id,
        title=item.effect.direction,
        setup_area=item.effect.setup_area,
        strength_label=DIAL_IN_STRENGTH_LABELS.get(item.effect.effect_strength, "Setup lever"),
        risk_label=RISK_LABELS.get(item.effect.coupling_risk, item.effect.coupling_risk.title()),
        effect=item.effect.effect,
        counter_effect=item.effect.counter_effect,
        one_change_test=item.one_change_test_plan,
        validate_with=item.effect.validation_targets,
        validate_with_labels=[format_target_label(target) for target in item.effect.validation_targets],
        watch_for=item.effect.watch_for_targets,
        watch_for_labels=[format_target_label(target) for target in item.effect.watch_for_targets],
        readiness_label=CANDIDATE_READINESS_LABELS.get(item.readiness, item.readiness.replace("_", " ").title()),
        debug=debug,
    )


def _validation_summary(swings: list[DialInSwing]) -> str | None:
    targets: list[str] = []
    for swing in swings:
        for target in swing.validate_with:
            if target not in targets:
                targets.append(target)
    if not targets:
        return None
    return f"What to watch for: {', '.join(targets[:5])}."


def _readiness_sentence(readiness_label: str) -> str:
    if readiness_label == "Data profile looks clean":
        return "Data profile looks clean. High confidence."
    if readiness_label == "Data profile is partial":
        return "Data profile is partial. Pick one change and validate it."
    if readiness_label == "Need cleaner data":
        return "I need a cleaner run to be sure."
    return f"Readiness: {readiness_label}."


def _driver_warnings(warnings: list[str], *, include_debug_evidence: bool) -> list[str]:
    if include_debug_evidence:
        return warnings
    cleaned: list[str] = []
    for warning in warnings:
        if "measured downforce" in warning.lower():
            cleaned.append("Derived diffuser geometry proxy is available. Treat it as geometry context.")
        else:
            cleaned.append(warning)
    return cleaned


def _driver_message(
    complaint: str,
    interpreted_symptom: str | None,
    readiness_label: str,
    missing_hint: str | None,
    swings: list[DialInSwing],
) -> str:
    if not interpreted_symptom:
        return f'I could not map "{complaint}" to a supported setup complaint yet. Try a cleaner run or narrow the complaint.'
    opening = f"You said {complaint}. I'm reading that as {interpreted_symptom.replace('_', ' ')}."
    if not swings:
        if missing_hint:
            return f"{opening} I need a cleaner run to be sure. {missing_hint}"
        return f"{opening} I need a cleaner run to be sure."
    if missing_hint:
        return f"{opening} {_readiness_sentence(readiness_label)} {missing_hint}"
    return f"{opening} {_readiness_sentence(readiness_label)}"


def _hidden_summary(result, context) -> HiddenEvidenceSummary:
    present_evidence: list[str] = []
    missing_evidence: list[str] = []
    for item in result.setup_query.candidate_effects:
        for evidence in item.evidence_matched:
            if evidence not in present_evidence:
                present_evidence.append(evidence)
        for evidence in item.missing_evidence:
            if evidence not in missing_evidence:
                missing_evidence.append(evidence)
    disabled = [
        {"effect_id": effect.effect_id, "setup_area": effect.setup_area, "direction": effect.direction}
        for effect in result.setup_query.disabled_by_car_capability
    ]
    return HiddenEvidenceSummary(
        evidence_flags=context.evidence_flags,
        evidence_groups=context.evidence_groups,
        present_evidence=present_evidence,
        missing_evidence=missing_evidence,
        readiness_by_candidate=result.candidate_readiness,
        ranking_reasons=result.setup_query.ranking_reasons,
        disabled_by_capability=disabled,
    )


def build_dial_in_response(
    run_id: str,
    complaint: str,
    *,
    car_family_override: str | None = None,
    track_family_override: str | None = None,
    baseline_run_id: str | None = None,
    test_run_id: str | None = None,
    package_archetype: str | None = None,
    limit: int = 3,
    include_debug_evidence: bool = False,
) -> DialInResponse:
    context = build_run_evidence_context(
        run_id,
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        car_family_override=car_family_override,
        track_family_override=track_family_override,
    )
    knowledge = load_setup_knowledge()
    try:
        parsed = parse_symptom(complaint, knowledge)
    except ValueError:
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            confidence_label=_confidence_label(complaint, needs_clarification=False, supported=False),
            readiness_label="Need cleaner data",
            driver_message=f'I could not map "{complaint}" to a supported setup complaint yet. Try a cleaner run or narrow the complaint.',
            next_step="Try naming the phase, trigger, or main behavior first.",
            clarification=Clarification(needed=False),
            warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
        )

    normalized_complaint = _normalize_complaint(complaint)
    question = parsed.clarification_question
    options = parsed.clarification_options
    if question is not None and normalized_complaint in GENERIC_COMPLAINTS:
        question = GENERIC_CLARIFICATION_QUESTION
        options = GENERIC_CLARIFICATION_OPTIONS
    clarification = Clarification(
        needed=question is not None,
        question=question,
        options=options,
    )
    confidence_label = _confidence_label(complaint, needs_clarification=clarification.needed, supported=True)

    if clarification.needed:
        message = f"I need to narrow it down. {clarification.question}"
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            interpreted_symptom=parsed.canonical_symptom,
            interpreted_phase=parsed.phase,
            balance_direction=_balance_label(parsed.balance),
            confidence_label=confidence_label,
            readiness_label="Need cleaner data",
            driver_message=message,
            next_step="Answer the clarification first. Then pick one change, not a handful.",
            clarification=clarification,
            warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
            hidden_evidence_summary=_hidden_summary(
                query_setup_for_run_context(
                    run_id,
                    complaint,
                    evidence_context=context,
                    baseline_run_id=baseline_run_id,
                    test_run_id=test_run_id,
                    car_family_override=car_family_override,
                    track_family_override=track_family_override,
                    package_archetype=package_archetype,
                    limit=max(limit, 1),
                ),
                context,
            )
            if include_debug_evidence
            else None,
        )

    query_result = query_setup_for_run_context(
        run_id,
        complaint,
        evidence_context=context,
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        car_family_override=car_family_override,
        track_family_override=track_family_override,
        package_archetype=package_archetype,
        limit=max(limit * 2, limit),
    )
    selected = _filter_swings(query_result.setup_query.candidate_effects, limit)
    swings = [_build_swing(item, include_debug_evidence=include_debug_evidence) for item in selected]

    missing_hint = _evidence_status_hint(
        context.warnings,
        baseline_run_id=baseline_run_id if context.unavailable_reasons.get("compare_baseline") else None,
        test_run_id=test_run_id if context.unavailable_reasons.get("compare_test") else None,
    )
    readiness_label = _readiness_label([item.readiness for item in selected], missing_hint=missing_hint)
    next_step = "Test one swing at a time and compare like-for-like laps."
    if readiness_label == "Need cleaner data":
        next_step = "Data's noisy here. Try a cleaner run or narrow the complaint."
    if missing_hint:
        next_step = f"{next_step} {missing_hint}"

    return DialInResponse(
        run_id=run_id,
        complaint_raw=complaint,
        interpreted_symptom=parsed.canonical_symptom,
        interpreted_phase=query_result.setup_query.parsed_phase,
        balance_direction=_balance_label(parsed.balance),
        confidence_label=confidence_label,
        readiness_label=readiness_label,
        driver_message=_driver_message(complaint, parsed.canonical_symptom, readiness_label, missing_hint, swings),
        top_swings=swings,
        next_step=next_step,
        validation_summary=_validation_summary(swings),
        clarification=clarification,
        hidden_evidence_summary=_hidden_summary(query_result, context) if include_debug_evidence else None,
        warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
    )
