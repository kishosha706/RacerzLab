# Future UX Improvements — Design Notes

This file tracks UX improvements that are intentionally deferred or require
architectural changes beyond a single polish pass.

---

## Native Tauri File Dialogs

**Status:** Not implemented. Browser file input is used.

**Future work:**
- Native file picker via Tauri dialog API
- Telemetry folder scanner (Documents/iRacing/telemetry)
- Remember last import folder
- Drag-and-drop support

**Current import flow:** `App.tsx` uses a hidden `<input type="file">` with
`.ibt,.sto,.mt2` accept filter. This works in both browser and Tauri webview.

---

## Global Unit System Toggle

**Status:** Not implemented. Units are hardcoded in `channelMeta.ts`.

**Future design:**
- `UnitSystemContext` with values: `"imperial" | "metric" | "mixed"`
- Default: `"mixed"` (mph, in, psi, °F for iRacing defaults)
- All formatting goes through `channelFormat.ts` which reads the context

**Files that would need conversion:**
- `ui/src/utils/channelMeta.ts` — unit definitions
- `ui/src/utils/channelFormat.ts` — formatting functions
- `ui/src/components/ValueDisplay.tsx` — display component
- `ui/src/tabs/PlatformTab.tsx` — hardcoded unit strings in PRESET_ROWS
- `ui/src/tabs/LapsTab.tsx` — hardcoded "mph", "mm"
- `ui/src/components/EvidenceInspector.tsx` — hardcoded "ft"
- `ui/src/components/DidItWorkCard.tsx` — hardcoded "mph", "mm", "psi", "°C"

**Risk:** High — changing displayed telemetry units globally could confuse users
who are accustomed to iRacing's imperial defaults. Must be opt-in.

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

## Lazy-Load Heavy Tabs

**Status:** Not implemented. Tabs use named exports, incompatible with `React.lazy`.

**Future work:**
- Convert tab components to default exports
- Use `React.lazy(() => import("./tabs/PlatformTab"))` with `<Suspense>`
- Candidates: PlatformTab, TrackMapTab, CompareTab, LapsTab, RawChannelsTab, NotebookTab
