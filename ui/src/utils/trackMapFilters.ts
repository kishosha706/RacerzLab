/** Track Map filter presets, layer classification, severity ranking. */

import type { TrackMapOverlayMarker } from "../types/trackMap";

// ── Types ──────────────────────────────────────────────────────

export type LayerId =
  | "sections" | "target_zone" | "markers"
  | "all_events" | "front_scrape" | "rear_scrape"
  | "whole_car_bottoming" | "drag_scrub" | "speed_loss"
  | "aero" | "shocks" | "delta" | "insights" | "tires" | "notebook";

export type SeverityLevel = "all" | "critical" | "high" | "watch" | "info";

export type PresetId =
  | "all" | "map_only" | "platform" | "scrape" | "rear_scrape"
  | "whole_car" | "drag_scrub" | "aero" | "shocks" | "critical_only" | "custom";

export interface PresetDef {
  id: PresetId;
  label: string;
  layers: LayerId[];
  severity: SeverityLevel;
}

// ── Constants ──────────────────────────────────────────────────

export const SEVERITY_RANK: Record<string, number> = {
  critical: 0, high: 1, watch: 2, info: 3,
};

export const CATEGORY_LAYER_MAP: Record<string, LayerId> = {
  front_platform: "front_scrape",
  rear_platform: "rear_scrape",
  whole_car_bottoming: "whole_car_bottoming",
  platform_risk: "whole_car_bottoming",
  drag_scrub: "drag_scrub",
  speed_loss: "speed_loss",
  aero_dynamic_pressure: "aero",
  shocks: "shocks",
  other: "all_events",
};

export const LAYER_DEFS: { id: LayerId; label: string; group: "map" | "events" | "other" }[] = [
  { id: "sections", label: "Sections", group: "map" },
  { id: "target_zone", label: "Target Zone", group: "map" },
  { id: "markers", label: "Markers", group: "map" },
  { id: "all_events", label: "All Events", group: "events" },
  { id: "front_scrape", label: "Front Scrape", group: "events" },
  { id: "rear_scrape", label: "Rear Scrape", group: "events" },
  { id: "whole_car_bottoming", label: "Bottoming", group: "events" },
  { id: "drag_scrub", label: "Drag/Scrub", group: "events" },
  { id: "speed_loss", label: "Speed Loss", group: "events" },
  { id: "aero", label: "Aero / DP", group: "events" },
  { id: "shocks", label: "Shocks", group: "events" },
  { id: "delta", label: "Delta", group: "other" },
  { id: "insights", label: "Insights", group: "other" },
  { id: "tires", label: "Tires", group: "other" },
  { id: "notebook", label: "Notebook", group: "other" },
];

export const PRESETS: PresetDef[] = [
  { id: "all", label: "All", layers: ["sections", "target_zone", "markers", "all_events", "front_scrape", "rear_scrape", "whole_car_bottoming", "drag_scrub", "speed_loss", "aero", "shocks"], severity: "all" },
  { id: "map_only", label: "Map Only", layers: ["sections", "target_zone", "markers"], severity: "all" },
  { id: "platform", label: "Platform", layers: ["sections", "target_zone", "markers", "all_events"], severity: "watch" },
  { id: "scrape", label: "Scrape", layers: ["sections", "target_zone", "markers", "front_scrape", "rear_scrape", "whole_car_bottoming"], severity: "watch" },
  { id: "rear_scrape", label: "Rear Scrape", layers: ["sections", "target_zone", "markers", "rear_scrape"], severity: "watch" },
  { id: "whole_car", label: "Whole-Car", layers: ["sections", "target_zone", "markers", "whole_car_bottoming"], severity: "watch" },
  { id: "drag_scrub", label: "Drag/Scrub", layers: ["sections", "target_zone", "markers", "drag_scrub", "speed_loss"], severity: "watch" },
  { id: "aero", label: "Aero", layers: ["sections", "target_zone", "markers", "aero"], severity: "watch" },
  { id: "shocks", label: "Shocks", layers: ["sections", "target_zone", "markers", "shocks"], severity: "watch" },
  { id: "critical_only", label: "Critical Only", layers: ["sections", "target_zone", "markers", "all_events", "front_scrape", "rear_scrape", "whole_car_bottoming", "drag_scrub", "speed_loss", "aero", "shocks"], severity: "critical" },
];

// ── Helpers ────────────────────────────────────────────────────

export function classifyOverlayLayer(o: TrackMapOverlayMarker): LayerId {
  if (o.category) return CATEGORY_LAYER_MAP[o.category] ?? "all_events";
  if (o.kind === "delta_annotation") return "delta";
  if (o.kind === "insight") return "insights";
  if (o.kind === "tire_shock") return "tires";
  if (o.kind === "notebook_finding") return "notebook";
  // Check event_type for precise classification
  if (o.event_type) {
    const et = o.event_type;
    if (/MIN_SPLITTER/.test(et)) return "front_scrape";
    if (/REAR_/.test(et) || /MIN_REAR/.test(et)) return "rear_scrape";
    if (/BOTTOMING/.test(et) || /PLATFORM_COMPRESSION/.test(et)) return "whole_car_bottoming";
    if (/DRAG_SCRUB/.test(et)) return "drag_scrub";
    if (/SPEED_LOSS/.test(et)) return "speed_loss";
    if (/SHOCK/.test(et)) return "shocks";
    if (/DYNAMIC_PRESSURE/.test(et) || /RAKE/.test(et)) return "aero";
  }
  const l = (o.label || "").toLowerCase();
  if (/whole.?car.?bottoming|bottoming/.test(l)) return "whole_car_bottoming";
  if (/front.?scrape|front.?platform.?low|splitter/.test(l)) return "front_scrape";
  if (/rear.?scrape|rear.?platform.?low|rear.?ride.?height|rear.?contact|min.?rear/.test(l)) return "rear_scrape";
  if (/drag|scrub/.test(l)) return "drag_scrub";
  if (/speed.?loss/.test(l)) return "speed_loss";
  if (/dynamic.?pressure|aero|rake/.test(l)) return "aero";
  if (/shock|damper/.test(l)) return "shocks";
  return "all_events";
}

export function severityPasses(s: string | undefined, f: SeverityLevel): boolean {
  if (f === "all" || !s) return true;
  return (SEVERITY_RANK[s] ?? 99) <= (SEVERITY_RANK[f] ?? 0);
}

export function detectActivePreset(
  activeLayers: Set<LayerId>,
  severityFilter: SeverityLevel,
): PresetId {
  for (const preset of PRESETS) {
    const pLayers = new Set(preset.layers);
    // Check that all preset layers are active (superset check) AND severity matches
    if ([...pLayers].every((l) => activeLayers.has(l)) && preset.severity === severityFilter) {
      return preset.id;
    }
  }
  return "custom";
}
