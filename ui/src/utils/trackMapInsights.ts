/** Track Map insight helpers: summaries, sentences, fingerprints, next-best-click. */

import type { TrackMapOverlayMarker, TrackMapSection } from "../types/trackMap";
import { calculateTrackLocation, friendlySectionName, normalizePct } from "./trackLocation";

// ── Severity ranking ───────────────────────────────────────────

const SEVERITY_RANK: Record<string, number> = {
  critical: 0, high: 1, watch: 2, info: 3,
};

const CATEGORY_PRIORITY: Record<string, number> = {
  whole_car_bottoming: 0,
  rear_platform: 1,
  front_platform: 2,
  platform_risk: 3,
  drag_scrub: 4,
  speed_loss: 5,
  shocks: 6,
  aero_dynamic_pressure: 7,
};

function classifyCategory(o: TrackMapOverlayMarker): string {
  if (o.category) return o.category;
  const l = (o.label || "").toLowerCase();
  if (/whole.?car.?bottoming|bottoming/.test(l)) return "whole_car_bottoming";
  if (/rear.?scrape|rear.?platform/.test(l)) return "rear_platform";
  if (/front.?scrape|splitter/.test(l)) return "front_platform";
  if (/drag|scrub/.test(l)) return "drag_scrub";
  if (/speed.?loss/.test(l)) return "speed_loss";
  if (/shock|damper/.test(l)) return "shocks";
  if (/aero|dynamic.?pressure/.test(l)) return "aero_dynamic_pressure";
  return "other";
}

function categoryLabel(cat: string): string {
  const labels: Record<string, string> = {
    whole_car_bottoming: "Whole-Car Bottoming",
    rear_platform: "Rear Platform",
    front_platform: "Front Platform",
    platform_risk: "Platform Risk",
    drag_scrub: "Drag/Scrub",
    speed_loss: "Speed Loss",
    shocks: "Shocks",
    aero_dynamic_pressure: "Aero",
  };
  return labels[cat] || cat;
}

// ── Summary ────────────────────────────────────────────────────

export interface TrackMapSummary {
  total: number;
  affectedAreas: number;
  worstEvent: TrackMapOverlayMarker | null;
  worstLocation: string;
  dominantCategory: string;
  mostAffectedArea: string;
  pinnedCount: number;
  presetLabel: string;
  problemFocus: boolean;
  manualMap: boolean;
}

export function buildTrackMapSummary(params: {
  visibleOverlays: TrackMapOverlayMarker[];
  sections: TrackMapSection[];
  activePreset?: string;
  problemFocus?: boolean;
  pinnedCount?: number;
  manualMap?: boolean;
}): TrackMapSummary {
  const { visibleOverlays, sections } = params;
  const platformEvents = visibleOverlays.filter((o) => o.kind === "platform_event");

  // Worst event
  const worst = platformEvents.length
    ? platformEvents.reduce((a, b) => {
        const aRank = SEVERITY_RANK[a.severity ?? "info"] ?? 99;
        const bRank = SEVERITY_RANK[b.severity ?? "info"] ?? 99;
        return aRank <= bRank ? a : b;
      })
    : null;

  // Affected areas
  const areaSet = new Set<string>();
  const areaCounts = new Map<string, number>();
  for (const o of platformEvents) {
    const loc = calculateTrackLocation(o.lap_pct, sections);
    const area = loc.friendly_section_name;
    areaSet.add(area);
    areaCounts.set(area, (areaCounts.get(area) ?? 0) + 1);
  }

  // Most affected area
  let mostAffectedArea = "";
  let mostN = 0;
  for (const [area, n] of areaCounts) {
    if (n > mostN) {
      mostN = n;
      mostAffectedArea = area;
    }
  }

  // Dominant category
  const catCounts = new Map<string, number>();
  for (const o of platformEvents) {
    const cat = classifyCategory(o);
    catCounts.set(cat, (catCounts.get(cat) ?? 0) + 1);
  }
  let dominantCat = "";
  let domN = 0;
  for (const [cat, n] of catCounts) {
    if (n > domN) {
      domN = n;
      dominantCat = cat;
    }
  }

  const worstLoc = worst ? calculateTrackLocation(worst.lap_pct, sections) : null;

  return {
    total: platformEvents.length,
    affectedAreas: areaSet.size,
    worstEvent: worst,
    worstLocation: worstLoc?.display_label ?? "unknown",
    dominantCategory: categoryLabel(dominantCat),
    mostAffectedArea,
    pinnedCount: params.pinnedCount ?? 0,
    presetLabel: params.activePreset ?? "All",
    problemFocus: params.problemFocus ?? false,
    manualMap: params.manualMap ?? false,
  };
}

// ── Event sentence ─────────────────────────────────────────────

export function buildEventSentence(
  overlay: TrackMapOverlayMarker,
  sections: TrackMapSection[],
): string {
  const loc = calculateTrackLocation(overlay.lap_pct, sections);
  const severity = overlay.severity ?? "";
  const sevLabel = severity ? `${severity} ` : "";
  return `${sevLabel}${overlay.label} ${loc.sentence_label}.`;
}

// ── Problem fingerprints ───────────────────────────────────────

export interface ProblemFingerprint {
  pattern: string;
  areas: string[];
  severity: string;
}

export function buildProblemFingerprints(
  overlays: TrackMapOverlayMarker[],
  sections: TrackMapSection[],
): ProblemFingerprint[] {
  const fingerprints: ProblemFingerprint[] = [];

  // Group by area
  const byArea = new Map<string, TrackMapOverlayMarker[]>();
  for (const o of overlays) {
    const loc = calculateTrackLocation(o.lap_pct, sections);
    const area = loc.friendly_section_name;
    if (!byArea.has(area)) byArea.set(area, []);
    byArea.get(area)!.push(o);
  }

  for (const [area, evts] of byArea) {
    const rearScrape = evts.filter((e) => classifyCategory(e) === "rear_platform");
    const bottoming = evts.filter((e) => classifyCategory(e) === "whole_car_bottoming");
    const dragScrub = evts.filter((e) => classifyCategory(e) === "drag_scrub");
    const speedLoss = evts.filter((e) => classifyCategory(e) === "speed_loss");
    const shocks = evts.filter((e) => classifyCategory(e) === "shocks");

    if (rearScrape.length >= 2) {
      fingerprints.push({
        pattern: `Repeated rear scrape in ${area}`,
        areas: [area],
        severity: "high",
      });
    }
    if (bottoming.length >= 1 && speedLoss.length >= 1) {
      fingerprints.push({
        pattern: `Bottoming and speed loss overlap in ${area}`,
        areas: [area],
        severity: "critical",
      });
    }
    if (dragScrub.length >= 1 && evts.some((e) => /steering|scrub/i.test(e.label || ""))) {
      fingerprints.push({
        pattern: `Possible scrub-related speed loss in ${area}`,
        areas: [area],
        severity: "high",
      });
    }
    if (shocks.length >= 2) {
      fingerprints.push({
        pattern: `Repeated shock activity in ${area}`,
        areas: [area],
        severity: "watch",
      });
    }
  }

  return fingerprints;
}

// ── Next Best Click ────────────────────────────────────────────

export function buildNextBestClick(
  overlays: TrackMapOverlayMarker[],
  sections: TrackMapSection[],
  selectedId?: string | null,
): string {
  const visible = overlays.filter((o) => o.kind === "platform_event" && o.marker_id !== selectedId);
  if (visible.length === 0) return "";

  // Score each event
  const scored = visible.map((o) => {
    const sevRank = SEVERITY_RANK[o.severity ?? "info"] ?? 99;
    const cat = classifyCategory(o);
    const catRank = CATEGORY_PRIORITY[cat] ?? 99;
    const loc = calculateTrackLocation(o.lap_pct, sections);
    // Check if same area has repeated events
    const sameArea = visible.filter(
      (v) => v.marker_id !== o.marker_id && calculateTrackLocation(v.lap_pct, sections).friendly_section_name === loc.friendly_section_name,
    ).length;
    const score = sevRank * 10 + catRank - sameArea * 2;
    return { overlay: o, score, loc };
  });

  scored.sort((a, b) => a.score - b.score);
  const best = scored[0];
  return `Review ${best.overlay.label} in ${best.loc.display_label} — highest severity${scored.filter((s) => s.score === best.score).length > 1 ? " and repeated in this area" : ""}.`;
}

// ── Area comparison ────────────────────────────────────────────

export function buildAreaComparison(
  overlays: TrackMapOverlayMarker[],
  sections: TrackMapSection[],
): string {
  const byArea = new Map<string, TrackMapOverlayMarker[]>();
  for (const o of overlays) {
    const loc = calculateTrackLocation(o.lap_pct, sections);
    const area = loc.friendly_section_name;
    if (!byArea.has(area)) byArea.set(area, []);
    byArea.get(area)!.push(o);
  }

  let mostAffected = "";
  let mostN = 0;
  for (const [area, evts] of byArea) {
    if (evts.length > mostN) {
      mostN = evts.length;
      mostAffected = area;
    }
  }

  if (!mostAffected) return "";

  const areaEvts = byArea.get(mostAffected)!;
  const catCounts = new Map<string, number>();
  for (const e of areaEvts) {
    const cat = classifyCategory(e);
    catCounts.set(cat, (catCounts.get(cat) ?? 0) + 1);
  }
  const details = [...catCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([cat, n]) => `${n} ${categoryLabel(cat).toLowerCase()} event${n > 1 ? "s" : ""}`)
    .join(", ");

  return `Most affected area: ${mostAffected}. ${mostAffected} has ${areaEvts.length} visible event${areaEvts.length > 1 ? "s" : ""}, including ${details}.`;
}
