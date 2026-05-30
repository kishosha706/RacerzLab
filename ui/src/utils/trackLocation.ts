/** Track-location intelligence: section lookup, phase detection, friendly naming. */

import type { TrackMapSection } from "../types/trackMap";

// ── Types ──────────────────────────────────────────────────────

export type TrackLocationPhase =
  | "entry" | "center" | "exit"
  | "early" | "middle" | "late"
  | null;

export type TrackLocationConfidence =
  | "high" | "medium" | "low" | "unknown";

export type TrackLocation = {
  section_id: string | null;
  raw_section_name: string | null;
  section_type: "straight" | "corner" | "unknown";
  friendly_section_name: string;
  phase: TrackLocationPhase;
  display_label: string;
  short_label: string;
  sentence_label: string;
  confidence: TrackLocationConfidence;
  confidence_reason?: string;
  wraps_start_finish: boolean;

  // Internal/debug only:
  debug_lap_pct?: number | null;
  start_lap_pct?: number | null;
  end_lap_pct?: number | null;
  local_fraction?: number | null;
};

export type SectionPoint = {
  label: string;
  section_id: string;
  phase: TrackLocationPhase;
  display_label: string;
  short_label: string;
  x?: number | null;
  y?: number | null;
  heading_rad?: number | null;
  lap_pct?: number | null;
  distance_m?: number | null;
  distance_ft?: number | null;
};

export interface TrackLocationOptions {
  /** When true, straight sections get early/middle/late phase labels. */
  detailed_straights?: boolean;
}

// ── Core helpers ───────────────────────────────────────────────

/** Normalize any percentage into 0 <= pct < 100. */
export function normalizePct(pct: number): number {
  const n = pct % 100;
  return n < 0 ? n + 100 : n;
}

/** Return shortest wrap-aware delta between two percentages. */
export function wrapDeltaPct(a: number, b: number): number {
  const raw = b - a;
  if (raw > 50) return raw - 100;
  if (raw < -50) return raw + 100;
  return raw;
}

/** Check if a lap percentage falls inside a section (supports wraparound). */
export function sectionContainsLapPct(
  section: TrackMapSection,
  lapPct: number | null | undefined,
): boolean {
  if (lapPct == null) return false;
  const start = normalizePct(section.start_lap_pct);
  const end = normalizePct(section.end_lap_pct);
  const value = normalizePct(lapPct);
  if (start <= end) return value >= start && value <= end;
  return value >= start || value <= end;
}

/** Compute local fraction (0–1) through a section for a given lap percentage. */
export function sectionLocalFraction(
  section: TrackMapSection,
  lapPct: number | null | undefined,
): number | null {
  if (lapPct == null) return null;
  const start = normalizePct(section.start_lap_pct);
  const end = normalizePct(section.end_lap_pct);
  const value = normalizePct(lapPct);
  const span = (end - start + 100) % 100;
  if (span === 0) return 0;
  const offset = (value - start + 100) % 100;
  return Math.max(0, Math.min(1, offset / span));
}

/** Determine phase within a section from local fraction. */
export function sectionPhaseForLapPct(
  lapPct: number | null | undefined,
  section: TrackMapSection,
): TrackLocationPhase {
  const lf = sectionLocalFraction(section, lapPct);
  if (lf == null) return null;
  if (section.section_type === "corner") {
    if (lf < 0.33) return "entry";
    if (lf <= 0.66) return "center";
    return "exit";
  }
  // Straight sections
  if (lf < 0.33) return "early";
  if (lf <= 0.66) return "middle";
  return "late";
}

// ── Friendly naming ────────────────────────────────────────────

/** Generate a friendly UI label for a section name. */
export function friendlySectionName(
  section: TrackMapSection,
  _allSections: TrackMapSection[],
): string {
  const raw = section.name || "";

  // Detect straights by name pattern
  const lower = raw.toLowerCase();

  // Front Stretch: wraps start/finish or named "Str 0-1" or "front"
  if (section.wraps_start_finish || /front|str\s*0/i.test(lower)) {
    return "Front Stretch";
  }
  // Backstretch: opposite straight
  if (/back|str\s*1/i.test(lower) && !section.wraps_start_finish) {
    return "Backstretch";
  }

  // Combined turns: "Turns 1-2", "Turns 3-4"
  const combinedMatch = raw.match(/[Tt]urns?\s*(\d+)\s*[-–]\s*(\d+)/);
  if (combinedMatch) {
    return "Turns " + combinedMatch[1] + "\u2013" + combinedMatch[2];
  }

  // Single turn: "Turn 1", "Turn 2", etc.
  const singleMatch = raw.match(/[Tt]urns?\s*(\d+)/);
  if (singleMatch) {
    return `Turn ${singleMatch[1]}`;
  }

  // Generic straight fallback
  if (section.section_type === "straight") {
    // Try to determine if it's front or back based on position
    const mid = (normalizePct(section.start_lap_pct) + normalizePct(section.end_lap_pct)) / 2;
    if (mid > 75 || mid < 25) return "Front Stretch";
    if (mid >= 25 && mid <= 75) return "Backstretch";
  }

  // Preserve raw name as fallback
  return raw || "Unknown section";
}

// ── Main calculator ────────────────────────────────────────────

/** Calculate a full TrackLocation for a lap percentage. */
export function calculateTrackLocation(
  lapPct: number | null | undefined,
  sections: TrackMapSection[],
  options?: TrackLocationOptions,
): TrackLocation {
  const fallback: TrackLocation = {
    section_id: null,
    raw_section_name: null,
    section_type: "unknown",
    friendly_section_name: "Unknown section",
    phase: null,
    display_label: "Unknown section",
    short_label: "Unknown",
    sentence_label: "Unknown section",
    confidence: "unknown",
    confidence_reason: "No section data available",
    wraps_start_finish: false,
    debug_lap_pct: lapPct ?? null,
  };

  if (lapPct == null || sections.length === 0) return fallback;

  const section = sections.find((s) => sectionContainsLapPct(s, lapPct));
  if (!section) {
    return {
      ...fallback,
      confidence: "low",
      confidence_reason: "Lap percentage does not fall within any known section",
    };
  }

  const friendly = friendlySectionName(section, sections);
  const phase = sectionPhaseForLapPct(lapPct, section);
  const lf = sectionLocalFraction(section, lapPct);

  // Build labels
  const phaseLabel = phaseToLabel(phase, section.section_type, options?.detailed_straights);
  const displayLabel = phaseLabel ? `${phaseLabel} ${friendly}` : friendly;
  const shortLabel = phaseLabel ? `${phaseLabel} ${shortenSection(friendly)}` : shortenSection(friendly);
  const sentenceLabel = phaseLabel
    ? `in ${phaseLabel.toLowerCase()} ${friendly}`
    : `in ${friendly}`;

  // Confidence
  let confidence: TrackLocationConfidence = "high";
  let confidenceReason = "Event falls cleanly inside section";
  if (!section.name || section.name === "Unknown") {
    confidence = "medium";
    confidenceReason = "Section name is generic";
  }

  return {
    section_id: section.section_id,
    raw_section_name: section.name,
    section_type: section.section_type,
    friendly_section_name: friendly,
    phase,
    display_label: displayLabel,
    short_label: shortLabel,
    sentence_label: sentenceLabel,
    confidence,
    confidence_reason: confidenceReason,
    wraps_start_finish: section.wraps_start_finish,
    debug_lap_pct: lapPct,
    start_lap_pct: section.start_lap_pct,
    end_lap_pct: section.end_lap_pct,
    local_fraction: lf,
  };
}

// ── Phase helpers ──────────────────────────────────────────────

function phaseToLabel(
  phase: TrackLocationPhase,
  sectionType: "straight" | "corner" | "unknown",
  detailedStraights?: boolean,
): string {
  if (!phase) return "";
  if (sectionType === "corner") {
    switch (phase) {
      case "entry": return "Entry";
      case "center": return "Center";
      case "exit": return "Exit";
      default: return "";
    }
  }
  // Straight
  if (!detailedStraights) return "";
  switch (phase) {
    case "early": return "Early";
    case "middle": return "Middle";
    case "late": return "Late";
    default: return "";
  }
}

function shortenSection(name: string): string {
  return name.replace(/^Turns?\s*/i, "T").replace(/^Front\s+Stretch$/i, "Front Str")
    .replace(/^Backstretch$/i, "Back Str");
}

// ── Range description ──────────────────────────────────────────

/** Describe a lap-percentage range as location language. */
export function describeLapPctRangeAsLocations(
  startPct: number,
  endPct: number,
  sections: TrackMapSection[],
): string {
  const startLoc = calculateTrackLocation(startPct, sections);
  const endLoc = calculateTrackLocation(endPct, sections);

  // Same section
  if (startLoc.section_id === endLoc.section_id && startLoc.section_id != null) {
    const startPhase = startLoc.phase ? phaseToLabel(startLoc.phase, startLoc.section_type, true) : "";
    const endPhase = endLoc.phase ? phaseToLabel(endLoc.phase, endLoc.section_type, true) : "";
    if (startPhase && endPhase && startPhase !== endPhase) {
      return `${startPhase}–${endPhase} ${startLoc.friendly_section_name}`;
    }
    return startLoc.friendly_section_name;
  }

  // Collect all sections in between
  const startIdx = sections.findIndex((s) => s.section_id === startLoc.section_id);
  const endIdx = sections.findIndex((s) => s.section_id === endLoc.section_id);
  const between: string[] = [];
  if (startIdx >= 0 && endIdx >= 0) {
    if (startIdx <= endIdx) {
      for (let i = startIdx + 1; i < endIdx; i++) {
        between.push(friendlySectionName(sections[i], sections));
      }
    } else {
      // Wraparound
      for (let i = startIdx + 1; i < sections.length; i++) {
        between.push(friendlySectionName(sections[i], sections));
      }
      for (let i = 0; i < endIdx; i++) {
        between.push(friendlySectionName(sections[i], sections));
      }
    }
  }

  const startPhase = startLoc.phase ? phaseToLabel(startLoc.phase, startLoc.section_type, true) : "";
  const endPhase = endLoc.phase ? phaseToLabel(endLoc.phase, endLoc.section_type, true) : "";
  const startPart = startPhase ? `${startPhase} ${startLoc.friendly_section_name}` : startLoc.friendly_section_name;
  const endPart = endPhase ? `${endPhase} ${endLoc.friendly_section_name}` : endLoc.friendly_section_name;

  if (between.length === 0) {
    return `${startPart} into ${endPart}`;
  }
  if (between.length <= 2) {
    return `${startPart} through ${between.join(", ")} into ${endPart}`;
  }
  return `${startPart} through ${between[0]}…${between[between.length - 1]} into ${endPart}`;
}

// ── Section point helpers ──────────────────────────────────────

function sectionPointAtFraction(
  sections: TrackMapSection[],
  sectionId: string,
  fraction: number,
  phase: TrackLocationPhase,
): SectionPoint | null {
  const section = sections.find((s) => s.section_id === sectionId);
  if (!section) return null;
  const friendly = friendlySectionName(section, sections);
  const phaseLbl = phaseToLabel(phase, section.section_type);
  const displayLabel = phaseLbl ? `${phaseLbl} ${friendly}` : friendly;
  return {
    label: friendly,
    section_id: sectionId,
    phase,
    display_label: displayLabel,
    short_label: phaseLbl ? `${phaseLbl} ${shortenSection(friendly)}` : shortenSection(friendly),
    lap_pct: section.start_lap_pct + fraction * ((section.end_lap_pct - section.start_lap_pct + 100) % 100),
    distance_m: section.start_distance_m + fraction * (section.end_distance_m - section.start_distance_m),
    distance_ft: section.start_distance_ft + fraction * (section.end_distance_ft - section.start_distance_ft),
  };
}

export function sectionCenter(sections: TrackMapSection[], sectionId: string): SectionPoint | null {
  return sectionPointAtFraction(sections, sectionId, 0.5, "center");
}

export function sectionEntryPoint(sections: TrackMapSection[], sectionId: string): SectionPoint | null {
  return sectionPointAtFraction(sections, sectionId, 0.0, "entry");
}

export function sectionExitPoint(sections: TrackMapSection[], sectionId: string): SectionPoint | null {
  return sectionPointAtFraction(sections, sectionId, 1.0, "exit");
}
