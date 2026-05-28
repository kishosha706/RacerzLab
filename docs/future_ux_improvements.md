# Future UX Improvements — Design Notes

This file tracks UX improvements that are intentionally deferred or require
architectural changes beyond a single polish pass.

---

## Native Tauri File Dialogs

**Status:** Partially implemented. `tauri-plugin-dialog` is installed and
registered. `ui/src/utils/tauriImport.ts` provides `pickTelemetryFile()`,
`pickTrackMapFile()`, and `pickTelemetryFolder()` helpers with browser
fallback detection via `isTauri()`.

**What's done:**
- `tauri-plugin-dialog` added to Cargo.toml and registered in lib.rs
- Dialog permission added to capabilities
- `@tauri-apps/plugin-dialog` npm package installed
- `ui/src/utils/tauriImport.ts` — native file/folder picker helpers
- `ui/src/utils/env.ts` — `isTauri()` / `isBrowser()` detection
- Browser file input fallback preserved

**Still needed:**
- Wire `pickTelemetryFile()` into the import flow in App.tsx
- Wire `pickTelemetryFolder()` into a folder scanner workflow
- Remember last import folder in localStorage
- Drag-and-drop support
- Documents/iRacing/telemetry default scan path

---

## Global Unit System Toggle

**Status:** Not implemented. Units are hardcoded in `channelMeta.ts`.

**Design scaffolding:**

```typescript
export type UnitSystem = "motorsport_default" | "imperial" | "metric";

export interface UnitConversion {
  channel: string;
  toMotorsport: (v: number) => number;
  toImperial: (v: number) => number;
  toMetric: (v: number) => number;
  motorsportUnit: string;
  imperialUnit: string;
  metricUnit: string;
}
```

**Conversion candidates (safe display-only):**

| Dimension | Motorsport Default | Imperial | Metric |
|---|---|---|---|
| Length (ride height) | mm | in | mm |
| Length (distance) | ft | ft | m |
| Speed | mph | mph | km/h |
| Pressure (tire) | psi | psi | kPa |
| Temperature | °F | °F | °C |
| Force | N | N | N |

**Design helper signatures (not yet implemented):**

```typescript
// Convert a channel value for display only
function convertChannelValue(channel: string, value: number, target: UnitSystem): number;

// Get the display unit for a channel in the target system
function getDisplayUnit(channel: string, target: UnitSystem): string;
```

**Files that would need conversion:**
- `ui/src/utils/channelMeta.ts` — unit definitions
- `ui/src/utils/channelFormat.ts` — formatting functions
- `ui/src/components/ValueDisplay.tsx` — display component
- `ui/src/tabs/PlatformTab.tsx` — hardcoded unit strings in PRESET_ROWS
- `ui/src/tabs/LapsTab.tsx` — hardcoded "mph", "mm"
- `ui/src/components/EvidenceInspector.tsx` — hardcoded "ft"
- `ui/src/components/DidItWorkCard.tsx` — hardcoded "mph", "mm", "psi", "°C"

**Risk:** High — changing displayed telemetry units globally could confuse users
who are accustomed to iRacing's imperial defaults. Must be opt-in with a clear
toggle in the UI. Do NOT change backend stored units or calculation units.

---

## CSS Scalability

**Status:** Single `styles.css` (~56 KB). Not migrated.

**Future split recommendation:**
- `track-map.css` — TrackMapTab, SVG map, overlays, clusters
- `platform.css` — PlatformTab, ECharts, cursor panel, engineering panels
- `laps.css` — LapsTab, stint map, lap table, window cards
- `compare.css` — CompareTab, DidItWorkCard, verdict, discipline
- `motion.css` — All animation keyframes and reduced-motion rules
- `base.css` — Variables, typography, layout, nav, buttons, tables

**Do not migrate until CSS Modules or similar is adopted.**

---

## Chart Zoom Persistence

**Status:** Not implemented.

**Future work:**
- Persist chart zoom state per run/lap in localStorage
- Restore on re-open
- Clear when run changes

**Risk:** Low, but requires stable zoom state serialization from ECharts.

---

## Ghost Lap / Baseline Overlay

**Status:** Not implemented. Design only.

**Goal:** Show a baseline lap ghost marker on the TrackMap or as a trace overlay
in the Platform workbench, so the user can visually compare baseline vs test
at the same normalized track position.

**Design notes:**
- Ghost marker on TrackMap: show baseline event positions alongside test events
- Trace overlay: overlay baseline trace as a dashed line on test charts
- Requires reliable sample alignment between runs (lap percentage grid)
- Warning: raw lap percentage should not be shown in normal UI
- Performance: ghost traces double the series count — use sparingly

**Disabled until:**
- Compare sample alignment is proven reliable across all track types
- Performance impact of double traces is measured
- UI has a clear "Show Baseline Ghost" toggle

**Implementation sketch:**
```typescript
// Future — not implemented
interface GhostOverlay {
  enabled: boolean;
  baselineRunId: string;
  baselineLap: number;
  opacity: number; // 0.3–0.7
}
```

---

## Lazy-Load Heavy Tabs

**Status:** Not implemented. Tabs use named exports, incompatible with `React.lazy`.

**Future work:**
- Convert tab components to default exports
- Use `React.lazy(() => import("./tabs/PlatformTab"))` with `<Suspense>`
- Candidates: PlatformTab, TrackMapTab, CompareTab, LapsTab, RawChannelsTab, NotebookTab
