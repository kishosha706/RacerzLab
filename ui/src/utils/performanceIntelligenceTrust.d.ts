import type { PerformanceIntelligenceProjection } from "../types/performanceIntelligence";
import type { CrewChiefEvidenceEntry } from "../types/crewChief";

export function isPerformanceIntelligenceProjection(
  value: unknown,
  scope: {
    runId: string;
    sessionId: string;
    setupId: string;
    setupSnapshotHash: string;
    buildContextHash: string;
    objectiveId: string;
    p19Hash: string;
    p20Revision: string;
    p26Hash: string;
    projectionHash: string;
    p19Next: string;
    scopeRunIds?: ReadonlySet<string>;
    opportunityEvidence?: Map<string, CrewChiefEvidenceEntry>;
  },
): value is PerformanceIntelligenceProjection;
