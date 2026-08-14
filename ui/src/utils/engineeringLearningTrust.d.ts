import type {
  CrewChiefLearningPrior,
  P19ReasoningMemory,
  ProblemFingerprint,
} from "../types/engineeringLearning";

export type EngineeringLearningTrustScope = {
  runId: string;
  sessionId: string;
  objectiveId: string;
  selectedScopeHash: string;
  p19Hash: string;
  p32Hash: string;
  historyRevision: string;
  projectionHash: string;
};

export function isCrewChiefLearningPrior(
  value: unknown,
  scope: EngineeringLearningTrustScope,
): value is CrewChiefLearningPrior;

export function isP19ReasoningMemory(value: unknown): value is P19ReasoningMemory;

export function isProblemFingerprint(value: unknown): value is ProblemFingerprint;

export function learningSourceArtifactIds(value: unknown): string[];

export function hasCanonicalEngineeringLearningDigests(value: unknown): Promise<boolean>;

export function canonicalEngineeringLearningSha256(value: unknown): Promise<string>;
