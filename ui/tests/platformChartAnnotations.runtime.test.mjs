import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { stripTypeScriptTypes } from "node:module";

const visibilitySource = await readFile(
  new URL("../src/utils/platformEventVisibility.ts", import.meta.url),
  "utf8",
);
const visibilityModuleUrl = `data:text/javascript;base64,${Buffer.from(
  stripTypeScriptTypes(visibilitySource, { mode: "strip" }),
).toString("base64")}`;
const annotationSource = (
  await readFile(new URL("../src/utils/platformChartAnnotations.ts", import.meta.url), "utf8")
).replace('from "./platformEventVisibility"', `from "${visibilityModuleUrl}"`);
const annotationModuleUrl = `data:text/javascript;base64,${Buffer.from(
  stripTypeScriptTypes(annotationSource, { mode: "strip" }),
).toString("base64")}`;
const { buildPlatformChartAnnotations } = await import(annotationModuleUrl);

const structuredEvent = {
  event_id: "platform-1",
  title: "RF compression contact",
  severity: "high",
  lap_dist_ft: 1250,
  display_scope: "actionable",
  is_visible_default: true,
  diagnostic_state: "finding",
  recommended_action: "Increase RF spring by 100 lb/in",
};

const structured = buildPlatformChartAnnotations({
  platformEvents: [structuredEvent],
  mode: "actionable",
});
assert.deepEqual(structured.annotations, [{
  distFt: 1250,
  label: "RF compression contact",
  severity: "high",
  muted: false,
  source: "platform",
}]);
assert.deepEqual(structured.markLines.map((line) => line.name), ["RF compression contact"]);
assert.equal(JSON.stringify(structured).includes("Increase RF spring"), false);

const hostileOverviewEvent = {
  event_id: "overview-legacy-1",
  event_type: "PLATFORM_BOTTOMING",
  event_subtype: "Increase RF spring by 100 lb/in",
  severity: "critical",
  distance_m_peak: 250,
};

const noFallback = buildPlatformChartAnnotations({
  platformEvents: [],
  legacyEvents: [hostileOverviewEvent],
  mode: "actionable",
});
assert.deepEqual(noFallback.annotations, []);
assert.deepEqual(noFallback.markLines, []);
assert.deepEqual(noFallback.markAreas, []);
