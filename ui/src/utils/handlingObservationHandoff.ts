/**
 * P35.6 P4 Engineer → Dial-In handling-observation handoff.
 *
 * The handoff travels through sessionStorage (the same pattern as the
 * controlled-workflow handoff) and is validated against the exact current
 * Engineering Case identity before Dial-In may display it. A stale or
 * foreign handoff is discarded silently — the observation never fabricates
 * driver wording and never re-attaches to a different case revision.
 */

export type HandlingObservationHandoff = {
  runId: string;
  sessionId: string;
  assessmentId: string;
  phase: string;
  canonicalSymptomId: string | null;
  caseId: string;
  caseRevision: string;
  caseSha256: string;
};

const ASSESSMENT_ID = /^hba_[0-9a-f]{24}$/;
const SHA = /^[0-9a-f]{64}$/;

export function handlingObservationHandoffKey(sessionId: string): string {
  return `racerzlab:handling-observation-handoff:${sessionId}`;
}

export function writeHandlingObservationHandoff(handoff: HandlingObservationHandoff): void {
  try {
    sessionStorage.setItem(
      handlingObservationHandoffKey(handoff.sessionId),
      JSON.stringify(handoff),
    );
  } catch {
    // sessionStorage is best-effort; the handoff just will not survive.
  }
}

export function readHandlingObservationHandoff(sessionId: string): HandlingObservationHandoff | null {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(handlingObservationHandoffKey(sessionId));
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const value = parsed as Record<string, unknown>;
    if (typeof value.runId !== "string" || !value.runId) return null;
    if (typeof value.sessionId !== "string" || value.sessionId !== sessionId) return null;
    if (typeof value.assessmentId !== "string" || !ASSESSMENT_ID.test(value.assessmentId)) return null;
    if (typeof value.phase !== "string" || !value.phase) return null;
    if (value.canonicalSymptomId !== null && typeof value.canonicalSymptomId !== "string") return null;
    if (typeof value.caseId !== "string" || !value.caseId) return null;
    if (typeof value.caseRevision !== "string" || !SHA.test(value.caseRevision)) return null;
    if (typeof value.caseSha256 !== "string" || !SHA.test(value.caseSha256)) return null;
    return {
      runId: value.runId,
      sessionId: value.sessionId,
      assessmentId: value.assessmentId,
      phase: value.phase,
      canonicalSymptomId: value.canonicalSymptomId as string | null,
      caseId: value.caseId,
      caseRevision: value.caseRevision,
      caseSha256: value.caseSha256,
    };
  } catch {
    return null;
  }
}

export function clearHandlingObservationHandoff(sessionId: string): void {
  try {
    sessionStorage.removeItem(handlingObservationHandoffKey(sessionId));
  } catch {
    // Nothing to clear when storage is unavailable.
  }
}
