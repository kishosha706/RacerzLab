# Future UX Improvements — Design Notes

This file tracks UX improvements that are intentionally deferred or require
architectural changes beyond a single polish pass. Based on the comprehensive
UX audit (2026-05-28), items are organized by priority.

Authority guardrail (reviewed 2026-08-10): deferred UX may improve navigation,
explanation, and evidence visibility, but it must not add setup direction,
exact targets, Keep/Undo, stop-testing, or persistent policy outside the
canonical P19 workflow.

---

## P0: Must Fix Before Calling App Stable

### Full Lap Playback Scrubber

**Page/Component:** EventTimeline, PlatformTab, TrackMapTab

**Status:** Implemented in the 2026-08-18 alpha-hardening pass. EventTimeline
retains event anchors and adds requestAnimationFrame playback plus a continuous
0-100% physical-position scrubber using the selected lap's recorded duration.

**Recommendation:** Implement the full playback scrubber, allowing users to
"play" through a lap at various speeds, with all synchronized elements
(traces, map marker, cursor readout, inspector) updating in real-time.

**Why it matters:** Essential for dynamic analysis, understanding event
sequences, and feeling like a "live" workstation.

**Implementation risk:** Medium. Requires careful state management and
performance optimization to ensure smooth animation across all linked
components.

### Baseline/Test Badges in RunContextBar

**Page/Component:** RunContextBar.tsx, TelemetrySelectionContext.tsx

**Status:** Implemented. RunContextBar binds BASELINE/TEST badges to the current
run's exact persisted Compare Basket role.

**Recommendation:** Add a small, distinct badge (e.g., "BASELINE", "TEST")
next to the run name in the RunContextBar when applicable. State needs to
be managed persistently.

**Why it matters:** Provides immediate context for the user, especially when
navigating between runs, reinforcing the comparison workflow.

**Implementation risk:** Low. Requires adding a new state to
TelemetrySelectionContext and updating the RunContextBar component.

---

## P1: High-Value Next Sprint

### Enhanced Zero-Event State in Overview

**Page/Component:** OverviewTab.tsx

**Status:** Implemented. The empty state says no supported platform finding
exists in the current scope and explicitly denies that this is a health certificate.

**Recommendation:** Refine the empty state without turning absence of a finding
into a health certificate. Prefer "No supported platform finding in this
scope" and distinguish that from unavailable/error states. Offer evidence-only
handoffs such as reviewing Laps or inspecting the Platform trace; never imply
that Compare can validate a setup policy.

**Implementation risk:** Low. Primarily copy and minor UI adjustments.

### Richer Tooltips for Engineering Metrics

**Page/Component:** EngineeringMetricCard.tsx, PlatformTab.tsx

**Status:** Basic tooltips exist.

**Recommendation:** Implement richer, context-aware tooltips for
EngineeringMetricCard and other complex metrics. Explain what the metric
represents, why it's important, and how it's calculated (briefly, or link
to a definition).

**Implementation risk:** Medium. Requires populating tooltip content for
many metrics, potentially from channelMeta.ts or a new metricMeta.ts.

### Degradation Trend Chart in Laps

**Page/Component:** LapsTab.tsx

**Status:** Lap falloff/degradation logic exists in backend, but no visual
trend chart in UI.

**Recommendation:** Add a small line chart in the LapsTab (above the stint
map) that plots lap time or a degradation index over lap number.

**Implementation risk:** Medium. Requires a new ECharts instance and data
aggregation.

### Clearer Evidence-Debt Grouping in Compare

**Page/Component:** CompareTab.tsx, DidItWorkCard.tsx

**Status:** Implemented. Compare groups context, test discipline, simulator
integrity, and eligibility/evidence debt without creating policy authority.

**Recommendation:** Implement a dedicated evidence-debt summary that groups
context, eligibility, discipline, integrity, and missing-channel blockers.
Compare remains observation-only and must not render Keep/Undo or a recommended
next setup step.

**Implementation risk:** Low. Primarily UI/CSS work.

### Direct "Open Setup with Focus" from EvidenceInspector

**Page/Component:** EvidenceInspector.tsx, SetupTab.tsx

**Status:** Implemented. EvidenceInspector and Platform provide an exact-event
"Open Setup" handoff that preserves focus scope.

**Recommendation:** Add a prominent "Open Setup with Focus" button in the
EvidenceInspector that directly navigates to the SetupTab and activates
Setup Focus Mode for the selected event.

**Implementation risk:** Low. Requires navigation state management.

### Enhanced Test Discipline and Confidence Explanations

**Page/Component:** DidItWorkCard.tsx

**Status:** Implemented. Compare displays supporting and limiting test-discipline
factors and labels the underlying value as ordinal evidence strength, never probability.

**Recommendation:** Expand the confidence score display to include a brief,
bulleted list of factors contributing to the score (e.g., "Positive: Clean
laps, single change. Negative: Weather difference.").

**Implementation risk:** Low.

---

## P2: Polish / Quality Improvement

### Refined buildWhyText for Overview Hero

**Page/Component:** OverviewTab.tsx

**Status:** buildWhyText exists but can feel generic.

**Recommendation:** Pull more specific details from event.evidence_json or
event.primary_metric_value. For example, "Splitter reached 3.58mm at
67.02% lap" instead of "Splitter low nearby."

**Implementation risk:** Low.

### Improved Event Clustering on Track Map

**Page/Component:** TrackMapTab.tsx

**Status:** Clustering exists but interaction model is unclear.

**Recommendation:** When multiple events cluster, provide a numbered badge.
Clicking the cluster should expand them or open a mini-list/modal of events
within that cluster.

**Implementation risk:** Medium. Requires new UI components.

### Cross-Session Search and Filtering in Laps

**Page/Component:** LapsTab.tsx

**Status:** "All Sessions" lists runs but lacks search/filter.

**Recommendation:** Add search and filter inputs to find laps based on car,
track, lap type, or performance metrics.

**Implementation risk:** Medium. May require backend API support.

### "Why This Setup Field Matters" Tooltips

**Page/Component:** SetupTab.tsx

**Status:** Fields are highlighted but reason for relevance is not explained.

**Recommendation:** Add tooltips to highlighted setup fields explaining
their impact on car behavior and relation to the selected telemetry event.

**Implementation risk:** Medium. Requires populating tooltip content.

### Observation Notebook Card Redesign

**Page/Component:** NotebookTab.tsx

**Status:** The observation component exists but is not a primary workspace.

**Recommendation:** If the observation archive is exposed again, summarize
scope, key measured deltas, evidence type, confidence context, and saved/archive
state. Do not restore verdict colors, setup changes, next steps, test plans, or
setup-memory suggestions; those would create a second policy surface outside
P19.

**Implementation risk:** Medium.

### RawChannelsTab Filters and Metadata Drawer

**Page/Component:** RawChannelsTab.tsx

**Status:** Channel search exists but no category/proxy/unit filters.

**Recommendation:** Add filters for channel category, proxy/estimate status,
and unit type. Implement a collapsible "Metadata Drawer" for the selected
channel.

**Implementation risk:** Medium.

### Chart Zoom Persistence

**Status:** Implemented per exact run/lap in localStorage. Invalid or stale
serialized ranges fail closed to full range and reset clears the stored range.

**Recommendation:** Persist chart zoom state per run/lap in localStorage,
restore on re-open, clear when run changes.

**Risk:** Low, but requires stable zoom state serialization from ECharts.

---

## P3: Future / Nice-to-Have

### Semantic CSS Organization

**Status:** Single `styles.css` (~56 KB). Not migrated.

**Future split recommendation:**
- `track-map.css` — TrackMapTab, SVG map, overlays, clusters
- `platform.css` — PlatformTab, ECharts, cursor panel, engineering panels
- `laps.css` — LapsTab, stint map, lap table, window cards
- `compare.css` — CompareTab, DidItWorkCard, observation, discipline
- `motion.css` — All animation keyframes and reduced-motion rules
- `base.css` — Variables, typography, layout, nav, buttons, tables

**Do not migrate until CSS Modules or similar is adopted.**

### Lazy-Load Heavy Tabs

**Status:** Partially implemented. Platform, Laps, Dial In, and Setup are
loaded with dynamic imports from `App.tsx`.

**Bundle audit (2026-08-18):** Domain trust registries now load with the Crew
workspace instead of the cockpit shell. Together with the audited Vite 8 move,
the entry fell from 450.99 KB to about 191 KB raw. The ECharts 6.1 security
upgrade leaves the charting chunk about 608 KB decimal / 593 KiB raw and lazy. Enforced
entry and CSS budgets were tightened to preserve the gain.

**Future work:**
- Extract the stacked chart workbench from `PlatformTab` behind its own lazy
  component boundary, then verify chart initialization, zoom, cursor, toolbox,
  mark-line, and mark-area behavior in the packaged desktop app.
- Profile whether the ECharts canvas renderer or registered toolbox/annotation
  components dominate the remaining bundle before removing any feature.
- Keep TrackMap, Compare, and Raw Channels as candidates where a measured
  initial-load benefit justifies the added boundary. Notebook is not a current
  primary workspace.

### Ghost Lap / Baseline Overlay

**Status:** Not implemented. Design only.

**Goal:** Show a baseline lap ghost marker on the TrackMap or as a trace
overlay in the Platform workbench.

**Design notes:**
- Ghost marker on TrackMap: show baseline event positions alongside test
- Trace overlay: overlay baseline trace as a dashed line on test charts
- Requires reliable sample alignment between runs (lap percentage grid)
- Performance: ghost traces double the series count — use sparingly

**Disabled until:**
- Compare sample alignment is proven reliable across all track types
- Performance impact of double traces is measured
- UI has a clear "Show Baseline Ghost" toggle

### Global Unit System Toggle

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

**Risk:** High — changing displayed telemetry units globally could confuse
users accustomed to iRacing's imperial defaults. Must be opt-in.

---

## Implementation Phases

### Phase 1: Small UX Fixes & Core Playback (P0/P1)
1. Full playback scrubber
2. Baseline/Test badges in RunContextBar
3. Enhanced zero-event state in OverviewTab
4. Refined buildWhyText for OverviewTab hero
5. Richer tooltips for EngineeringMetricCard
6. Improved Test Discipline and Confidence Score explanations
7. High-impact accessibility fixes (keyboard nav, color contrast)

### Phase 2: Workflow Completion & Context (P1/P2)
1. Degradation trend chart in LapsTab
2. Interactive event clustering on TrackMapTab
3. Direct "Open Setup with Focus" button in EvidenceInspector
4. Observation archive cards, only if that non-authorizing surface is restored
5. Cross-session search/filter in LapsTab
6. Consolidated warnings in EvidenceInspector and CompareTab

### Phase 3: Laps/Compare Improvements & Setup Depth (P2/P3)
1. Read-only P19 controlled-outcome history, with no independent suggestions
2. Detailed tooltips for highlighted setup fields
3. RawChannelsTab filters and metadata drawer
4. Chart zoom persistence

### Phase 4: Visual Polish & Performance (P2/P3)
1. Remaining visual polish (animations, hover effects)
2. List virtualization for RawChannelsTab and LapsTab
3. ECharts instance management optimization

### Phase 5: Accessibility & Data Hardening (P2/P3)
1. Remaining accessibility improvements
2. Final audit of data contract adherence and missing-state handling
