from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence


TRACK_NAME_MAP: dict[str, str] = {
    "atlanta motor speedway": "atlanta",
    "echopark speedway": "atlanta",
    "auto club speedway": "california",
    "autoclub speedway": "california",
    "bristol motor speedway": "bristol",
    "charlotte motor speedway": "charlotte",
    "chicagoland speedway": "chicagoland",
    "darlington raceway": "darlington",
    "daytona international speedway": "daytona",
    "dover international speedway": "dover",
    "gateway motorsports park": "gateway",
    "homestead miami speedway": "homestead",
    "indianapolis motor speedway": "indianapolis",
    "iowa speedway": "iowa",
    "irwindale speedway": "irwindale",
    "kansas speedway": "kansas",
    "kentucky speedway": "kentucky",
    "las vegas motor speedway": "vegas",
    "martinsville speedway": "martinsville",
    "michigan international speedway": "michigan",
    "myrtle beach speedway": "myrtlebeach",
    "new hampshire motor speedway": "newhampshire",
    "new smyrna speedway": "newsmyrna",
    "north wilkesboro speedway": "northwilkesboro",
    "phoenix raceway": "phoenix",
    "richmond raceway": "richmond",
    "rockingham speedway": "rockingham",
    "stafford motor speedway": "stafford",
    "talladega super speedway": "talladega",
    "talladega superspeedway": "talladega",
    "texas motor speedway": "texas",
    "road atlanta": "roadatlanta",
    "roadatlanta": "roadatlanta",
}

FAMILY_ALIASES: dict[str, tuple[str, ...]] = {
    "atlanta": ("atlanta", "echopark speedway", "echopark"),
    "bristol": ("bristol",),
    "california": ("california", "auto club", "autoclub"),
    "charlotte": ("charlotte",),
    "daytona": ("daytona",),
    "indianapolis": ("indianapolis", "indy"),
    "kentucky": ("kentucky",),
    "phoenix": ("phoenix",),
    "roadatlanta": ("road atlanta", "roadatlanta"),
    "talladega": ("talladega",),
    "texas": ("texas",),
}

LAYOUT_ALIASES: dict[str, tuple[str, ...]] = {
    "roval": ("roval",),
    "dirt": ("dirt",),
    "road": ("road course", "roadcourse", "road"),
    "oval": ("quadoval", "trioval", "oval open", "ovalopen", "oval"),
    "fullpit": ("full pit", "fullpit"),
    "outer": ("outer",),
}

VARIANT_ALIASES: dict[str, tuple[str, ...]] = {
    "quadoval": ("quadoval",),
    "fullroadcourse": ("full road course", "fullroadcourse"),
    "indypit": ("indypit", "indy pit"),
    "nascar2020": ("nascar2020", "nascar 2020"),
    "open": ("oval open", "ovalopen", "open"),
}

LAYOUT_DISPLAY_NAMES: dict[str, str] = {
    "default": "",
    "oval": "Oval",
    "road": "Road",
    "roval": "Roval",
    "dirt": "Dirt",
    "fullpit": "Full Pit",
    "outer": "Outer",
}

KNOWN_DISPLAY_NAME_NORMALIZATIONS: dict[str, str] = {
    "brandshatch grandprix": "Brands Hatch Grand Prix",
    "donington gp": "Donington GP",
    "interlagos gp": "Interlagos GP",
    "lagunaseca": "Laguna Seca",
    "midohio full": "Mid-Ohio Full",
    "newhampshire oval": "New Hampshire Oval",
    "oulton fosters": "Oulton Fosters",
    "oulton intbrittens": "Oulton International Brittens",
    "oulton intnochicane": "Oulton International No Chicane",
    "phillipisland": "Phillip Island",
    "roadatlanta full": "Road Atlanta Full",
    "roadamerica full": "Road America Full",
    "sebring international": "Sebring International",
    "sebring modified": "Sebring Modified",
    "silverstone gp": "Silverstone GP",
    "sonoma long": "Sonoma Long",
    "summit summit raceway": "Summit Point Raceway",
    "suzuka east": "Suzuka East",
    "suzuka grandprix": "Suzuka Grand Prix",
    "twinring fullrc": "Twin Ring Full RC",
    "twinring oval": "Twin Ring Oval",
    "virginia full": "Virginia Full",
    "watkinsglen cupcircuit": "Watkins Glen Cup Circuit",
    "watkinsglen fullcourse": "Watkins Glen Full Course",
    "watkinsglen fullnoloop": "Watkins Glen Full No Loop",
    "zandvoort grandprix": "Zandvoort Grand Prix",
    "zolder alt": "Zolder Alt",
    "zolder gp": "Zolder GP",
}

GENERIC_SUFFIXES = (
    " international raceway",
    " international speedway",
    " motor speedway",
    " super speedway",
    " superspeedway",
    " motorsports park",
    " speedway",
    " raceway",
    " circuit",
    " park",
)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    lower = Path(value).stem.lower()
    lower = lower.replace("_", " ").replace("-", " ")
    lower = re.sub(r"[^a-z0-9]+", " ", lower)
    return re.sub(r"\s+", " ", lower).strip()


def _extract_years(value: str) -> set[str]:
    return set(re.findall(r"\b(19\d{2}|20\d{2})\b", value))


def _contains_phrase(value: str, phrase: str) -> bool:
    if not value or not phrase:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
    return re.search(pattern, value) is not None


def _extract_family_key(name: str | None) -> str:
    normalized = _normalize_text(name)
    if not normalized:
        return "unknown"
    for alias, family in sorted(TRACK_NAME_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in normalized:
            return family
    for family, aliases in FAMILY_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if _contains_phrase(normalized, alias):
                return family
    if " " in normalized:
        return normalized.split()[0]
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    return compact or "unknown"


def _extract_variant_tokens(value: str) -> set[str]:
    variants: set[str] = set()
    compact_value = re.sub(r"[^a-z0-9]", "", value)
    for variant, aliases in VARIANT_ALIASES.items():
        for alias in aliases:
            alias_compact = re.sub(r"[^a-z0-9]", "", alias.lower())
            if _contains_phrase(value, alias) or (alias_compact and alias_compact in compact_value):
                variants.add(variant)
                break
    return variants


def _collect_entry_aliases(entry: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for key in ("display_name", "track_key", "source_filename", "map_id"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            aliases.append(value)
    raw_aliases = entry.get("match_aliases")
    if isinstance(raw_aliases, list):
        aliases.extend(str(alias) for alias in raw_aliases if alias)
    return aliases


def normalize_track_key(name: str | None) -> str:
    family = _extract_family_key(name)
    if family != "unknown":
        return family
    normalized = _normalize_text(name)
    for suffix in GENERIC_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    key = re.sub(r"[^a-z0-9]", "", normalized)
    return key or "unknown"


def infer_layout_key(filename_or_name: str | None) -> str:
    lower = _normalize_text(filename_or_name)
    if not lower:
        return "default"
    if any(_contains_phrase(lower, alias) for alias in LAYOUT_ALIASES["roval"]):
        return "roval"
    if any(_contains_phrase(lower, alias) for alias in LAYOUT_ALIASES["dirt"]):
        return "dirt"
    if any(_contains_phrase(lower, alias) for alias in LAYOUT_ALIASES["fullpit"]):
        return "fullpit"
    if any(_contains_phrase(lower, alias) for alias in LAYOUT_ALIASES["outer"]):
        return "outer"
    if any(_contains_phrase(lower, alias) for alias in ("road course", "roadcourse")):
        return "road"
    if "fullroadcourse" in lower or "roadatlanta" in lower or " road " in f" {lower} ":
        return "road"
    if any(_contains_phrase(lower, alias) for alias in LAYOUT_ALIASES["oval"]):
        return "oval"
    return "default"


def build_map_id(track_key: str, layout_key: str, sha_or_name: str) -> str:
    return f"{track_key}_{layout_key}_{sha_or_name.lower()[:12]}"


def build_match_aliases(track_name: str, source_filename: str, layout_key: str) -> list[str]:
    normalized_track = _normalize_text(track_name)
    normalized_file = _normalize_text(source_filename)
    family = normalize_track_key(track_name)
    aliases = {
        normalized_track,
        family,
        normalized_file,
        f"{family} {layout_key}".strip(),
    }
    if family in FAMILY_ALIASES:
        aliases.update(FAMILY_ALIASES[family])
    for token in _extract_variant_tokens(normalized_track):
        aliases.add(f"{family} {token}")
    years = _extract_years(normalized_track) | _extract_years(normalized_file)
    for year in years:
        aliases.add(f"{family} {year}")
        aliases.add(f"{family} {year} {layout_key}".strip())
    return sorted(alias for alias in aliases if alias)


def normalize_layout_label(layout_key: str | None) -> str:
    return LAYOUT_DISPLAY_NAMES.get((layout_key or "default").lower(), "")


def _known_display_name(source_text: str) -> str | None:
    return KNOWN_DISPLAY_NAME_NORMALIZATIONS.get(source_text)


def suggest_track_map_display_name(
    current_display_name: str | None,
    *,
    source_filename: str | None,
    map_id: str | None,
    layout_key: str | None,
) -> dict[str, Any]:
    current = (current_display_name or "").strip()
    source_text = _normalize_text(source_filename or current_display_name or map_id or "")
    family = normalize_track_key(current or source_filename or map_id)
    layout = (layout_key or infer_layout_key(source_text) or "default").lower()
    years = sorted(_extract_years(source_text))
    variants = _extract_variant_tokens(source_text)
    current_compact = re.sub(r"\s+", " ", current).strip()

    suggested = current_compact or current
    reason = ""
    classification = "display-name cleanup only"
    auto_fixable = False

    if family == "atlanta":
        if "2022" in years and layout == "oval":
            suggested = "Atlanta 2022 Oval"
            reason = "Preserve the distinguishing year and use a clean title-cased oval label."
            auto_fixable = True
        elif "quadoval" in source_text or current_compact.lower() == "atlanta quadoval (oval)":
            suggested = "Atlanta Quad Oval"
            reason = "Expand the variant into a human-readable display name."
            auto_fixable = True
    elif family == "bristol":
        if layout == "dirt":
            suggested = "Bristol Dirt"
            reason = "Keep the real dirt layout and drop the year because it does not distinguish another dirt map."
            auto_fixable = True
        elif layout == "fullpit":
            suggested = "Bristol Full Pit"
            reason = "Expand the compact layout token into readable words."
            auto_fixable = True
        elif layout == "default":
            suggested = "Bristol"
            reason = "Use the plain track name for the base map."
            auto_fixable = True
    elif family == "charlotte":
        if layout == "roval" and years == ["2018", "2019"]:
            suggested = "Charlotte 2018-2019 Roval"
            reason = "Keep the shared year range because it distinguishes this roval variant."
            auto_fixable = True
        elif "2025" in years and layout == "oval":
            suggested = "Charlotte 2025 Oval"
            reason = "Preserve the distinguishing year and normalize the oval label."
            auto_fixable = True
        elif "fullroadcourse" in source_text or layout == "road":
            suggested = "Charlotte Full Road Course"
            reason = "Expand the road-course variant into readable words."
            auto_fixable = True
        elif "quadoval" in source_text:
            suggested = "Charlotte Quad Oval"
            reason = "Expand the oval variant into readable words."
            auto_fixable = True
    elif family == "daytona":
        if "nascar2020" in variants or "nascar 2020" in source_text:
            suggested = "Daytona Road NASCAR 2020"
            reason = "Keep the NASCAR 2020 token because it distinguishes this road configuration."
            auto_fixable = True
            classification = "display-name cleanup only; alias cleanup"
        elif layout == "road":
            suggested = "Daytona Road"
            reason = "Use the clean road layout label because no extra year token is needed to distinguish this road map."
            auto_fixable = True
        elif layout == "oval":
            suggested = "Daytona Oval"
            reason = "Use the clean oval layout label because there is only one oval map."
            auto_fixable = True
    elif family == "indianapolis":
        if "2022" in years and layout == "oval":
            suggested = "Indianapolis 2022 Oval"
            reason = "Preserve the distinguishing year for the 2022 oval variant."
            auto_fixable = True
        elif "indypit" in variants:
            suggested = "Indianapolis Oval Indy Pit"
            reason = "Separate the pit variant into readable words."
            auto_fixable = True
        elif layout == "road":
            suggested = "Indianapolis Road"
            reason = "Use the clean road layout label."
            auto_fixable = True
        elif layout == "oval":
            suggested = "Indianapolis Oval"
            reason = "Use the clean oval layout label."
            auto_fixable = True
    elif family == "kentucky":
        if "2020" in years and layout == "oval":
            suggested = "Kentucky 2020 Oval"
            reason = "Preserve the distinguishing year for the 2020 oval variant."
            auto_fixable = True
        elif layout == "oval":
            suggested = "Kentucky Oval"
            reason = "Use the clean oval layout label."
            auto_fixable = True
    elif family == "phoenix":
        if "2021" in years and "open" in variants:
            suggested = "Phoenix 2021 Oval Open"
            reason = "Expand the compact open-layout token and keep the distinguishing year."
            auto_fixable = True
            classification = "display-name cleanup only; alias cleanup"
        elif "2012" in years and "open" in variants:
            suggested = "Phoenix 2012 Oval Open"
            reason = "Expand the compact open-layout token and keep the distinguishing year."
            auto_fixable = True
            classification = "display-name cleanup only; alias cleanup"
        elif layout == "oval":
            suggested = "Phoenix Oval"
            reason = "Use the clean oval layout label for the base map."
            auto_fixable = True
    elif family == "talladega":
        suggested = "Talladega"
        reason = "Use the plain track name for the base map."
        auto_fixable = True
    elif family == "texas":
        if "2020" in years and layout == "oval":
            suggested = "Texas 2020 Oval"
            reason = "Preserve the distinguishing year for the 2020 oval variant."
            auto_fixable = True
        elif layout == "oval":
            suggested = "Texas Oval"
            reason = "Use the clean oval layout label."
            auto_fixable = True

    known_name = _known_display_name(source_text)
    if known_name:
        suggested = known_name
        if "gp" in source_text or "grandprix" in source_text or "fullcourse" in source_text or "cupcircuit" in source_text or "roadatlanta" in source_text:
            classification = "display-name cleanup only; alias cleanup"
        reason = "Expand compact road-course tokens into a clean human-readable track name."
        auto_fixable = True

    if not suggested:
        title = " ".join(part.capitalize() for part in source_text.split())
        layout_label = normalize_layout_label(layout)
        suggested = title or current_compact
        if layout_label and layout_label.lower() not in suggested.lower():
            suggested = f"{suggested} {layout_label}".strip()
        reason = "Fallback title-casing cleanup."
        auto_fixable = True

    if not reason and suggested != current_compact:
        reason = "Normalize compact tokens into a human-readable display name."
        auto_fixable = True

    return {
        "current_display_name": current_compact,
        "suggested_display_name": suggested,
        "reason": reason,
        "classification": classification,
        "auto_fixable": auto_fixable and suggested != current_compact,
    }


def _candidate_text(map_track_name: str, map_filename: str, map_aliases: Sequence[str] | None) -> str:
    parts = [map_track_name, map_filename]
    if map_aliases:
        parts.extend(map_aliases)
    return " ".join(_normalize_text(part) for part in parts if part)


def _confidence_for_score(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= 70:
        return "medium"
    if score >= 45:
        return "low"
    return "none"


def score_track_map_match(
    run_track_name: str,
    run_layout: str | None,
    map_track_name: str,
    map_layout: str | None,
    map_filename: str,
    *,
    map_aliases: Sequence[str] | None = None,
    run_context: str | None = None,
) -> tuple[str, int]:
    """Return (confidence: high/medium/low/none, score) for a track map match."""
    run_text = _normalize_text(" ".join(part for part in (run_track_name, run_context) if part))
    map_text = _candidate_text(map_track_name, map_filename, map_aliases)

    family_run = _extract_family_key(run_text or run_track_name)
    family_map = _extract_family_key(map_text or map_track_name)
    inferred_run_layout = infer_layout_key(run_text or run_track_name)
    layout_run = run_layout if run_layout and run_layout != "default" else inferred_run_layout
    layout_map = map_layout or infer_layout_key(map_text or map_filename or map_track_name)

    if family_run == "unknown" or family_map == "unknown":
        return "none", 0
    if family_run != family_map:
        return "none", 0

    score = 55

    alias_matches = 0
    for alias in map_aliases or ():
        normalized_alias = _normalize_text(alias)
        if normalized_alias and _contains_phrase(run_text, normalized_alias):
            alias_matches += 1
    if alias_matches:
        score += min(20, alias_matches * 10)

    if run_text and _contains_phrase(run_text, _normalize_text(map_track_name)):
        score += 12

    run_has_specific_layout = layout_run != "default"
    map_has_specific_layout = layout_map != "default"
    if run_has_specific_layout:
        if layout_run == layout_map:
            score += 28
        else:
            score -= 25
    elif not map_has_specific_layout:
        score += 12
    elif layout_map == "oval":
        score += 4

    run_years = _extract_years(run_text)
    map_years = _extract_years(map_text)
    if run_years and map_years:
        if run_years & map_years:
            score += 16
        else:
            score -= 14
    elif not run_years and map_years:
        score -= 6

    run_variants = _extract_variant_tokens(run_text)
    map_variants = _extract_variant_tokens(map_text)
    if run_variants:
        if run_variants & map_variants:
            score += 18
        elif map_variants:
            score -= 18
        else:
            score -= 10
    elif map_variants:
        score -= 6

    if not run_has_specific_layout and not run_years and not run_variants and not map_years and not map_variants:
        score += 8

    if _contains_phrase(run_text, "dirt") and layout_map != "dirt":
        score -= 30
    if _contains_phrase(run_text, "road") and layout_map not in {"road", "roval"}:
        score -= 18
    if _contains_phrase(run_text, "roval") and layout_map != "roval":
        score -= 30

    return _confidence_for_score(score), max(score, 0)


def rank_track_map_matches(
    run_track_name: str,
    run_layout: str | None,
    available_maps: list[dict[str, Any]],
    *,
    run_context: str | None = None,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for entry in available_maps:
        aliases = _collect_entry_aliases(entry)
        confidence, score = score_track_map_match(
            run_track_name,
            run_layout,
            str(entry.get("display_name") or entry.get("track_key") or ""),
            entry.get("layout_key"),
            str(entry.get("source_filename", "")),
            map_aliases=aliases,
            run_context=run_context,
        )
        ranked.append(
            {
                "entry": entry,
                "score": score,
                "confidence": confidence,
                "aliases": aliases,
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def match_track_map_for_run(
    run_track_name: str,
    run_layout: str | None,
    available_maps: list[dict[str, Any]],
    preferred_map_id: str | None = None,
    *,
    run_context: str | None = None,
) -> dict[str, Any] | None:
    """Return the best matching map entry dict, or None.

    If *preferred_map_id* is given:
      - returns the entry with confidence='manual' if found
      - returns None if not found (caller should 404)
    """
    if preferred_map_id:
        for entry in available_maps:
            if entry.get("map_id") == preferred_map_id:
                entry["match_confidence"] = "manual"
                entry["match_score"] = 100
                return entry
        return None

    ranked = rank_track_map_matches(
        run_track_name,
        run_layout,
        available_maps,
        run_context=run_context,
    )
    if not ranked:
        return None

    best = ranked[0]
    if best["confidence"] not in {"high", "medium"}:
        return None

    tied_top = [item for item in ranked if item["score"] == best["score"]]
    if len(tied_top) > 1:
        return None

    best_match = best["entry"]
    best_match["match_confidence"] = best["confidence"]
    best_match["match_score"] = best["score"]
    return best_match
