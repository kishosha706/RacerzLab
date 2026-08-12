# RacerZLab Adversarial Improvement Log

This append-only ledger records material defects found by hostile review and the
architectural defenses added in response. It does not grant setup authority or
replace the verification evidence in `ROADMAP.md`.

## 2026-08-12 — Crew Chief closed-loop hardening

### AA-001 — Stale investigations silently adopted a new authority reality

- **Severity:** P0
- **Subsystem:** Crew Chief identity and authority boundary
- **Failure mode:** An open investigation could be projected against changed
  P19, P20, P26, setup, runtime, or workflow identities and continue acting
  without an explicit rebase.
- **Root cause:** Workspace revisions included current producer hashes, but the
  investigation did not retain a separately comparable accepted authority
  revision.
- **Fix:** Added a producer-owned authority fingerprint, durable explicit-rebase
  fingerprints, stale folding, read-only critique blocking, and exact rebase
  revision checks.
- **Regression test:**
  `test_investigation_authority_change_requires_explicit_rebase` and
  `test_rebase_rejects_a_foreign_stale_revision`.
- **Authority impact:** Closes a stale-state path; P19 remains the only setup
  authority.
- **Performance impact:** One bounded canonical hash comparison per workspace.
- **Remaining limitation:** Rebase remains an explicit API operation; it does
  not claim that changed evidence is comparable.

### AA-002 — Pending driver dialogue could be bypassed

- **Severity:** P1
- **Subsystem:** Crew Chief executive planner
- **Failure mode:** Calling Continue while a contextual driver question was
  pending emitted a terminal decision and closed the investigation.
- **Root cause:** The planner's terminal branch treated both answered and
  unanswered question states alike.
- **Fix:** Continue now rejects while a question is pending, and answer recording
  requires an open, exact-revision investigation.
- **Regression test:** `test_continue_cannot_bypass_a_pending_driver_question`.
- **Authority impact:** Driver answers remain context-only and cannot be skipped
  to accelerate setup action.
- **Performance impact:** None measurable.
- **Remaining limitation:** Driver reports remain contextual evidence, not
  mechanical proof.

### AA-003 — Run Sentinel collapsed A2 into B and reused recorded runs

- **Severity:** P1
- **Subsystem:** Run Sentinel / A-B-A2 mission control
- **Failure mode:** Every active controlled-test move was displayed as Stage B;
  a run already bound to B could be counted toward a pending A2 mission.
- **Root cause:** Sentinel inferred stage from the generic next-move kind instead
  of the canonical workflow preflight and did not inspect persisted stage-run
  ownership.
- **Fix:** Sentinel now uses the exact A/B/A2 preflight stage, stage-specific lap
  requirement, preflight blockers, and recorded stage-run bindings.
- **Regression test:**
  `test_run_sentinel_uses_exact_a2_stage_and_rejects_reusing_stage_b_run`.
- **Authority impact:** Prevents mission progress from laundering a prior stage;
  P19 still owns scoring and Keep/Undo/Retest/Invalid.
- **Performance impact:** One indexed workflow read already needed by the
  workspace.
- **Remaining limitation:** Sentinel reports deterministic qualification; it
  does not replace P19 score-time A/B/A2 certification.

### AA-004 — Redundant persistence metadata was not fully authenticated

- **Severity:** P2
- **Subsystem:** Crew Chief persistence and restart integrity
- **Failure mode:** Tampered investigation ordering, event workspace metadata,
  driver-memory session ownership, or response-atlas context columns could
  change retrieval scope without disagreeing with the parsed JSON checks.
- **Root cause:** Readers validated only a subset of the duplicated indexed
  columns against immutable typed payloads.
- **Fix:** Every material indexed identity is now cross-checked on read; response
  and driver-memory writes also serialize the check-and-insert transaction.
- **Regression test:** Four direct tamper regressions covering ordering,
  workspace revision, cross-session memory, and context relabeling.
- **Authority impact:** Prevents foreign or reordered history from entering the
  workspace.
- **Performance impact:** Constant-time field comparisons per returned record.
- **Remaining limitation:** Hashes provide integrity detection, not protection
  against an attacker who can replace the entire database and application.

### AA-005 — Workspace cache was not database-namespaced

- **Severity:** P2
- **Subsystem:** Crew Chief cache
- **Failure mode:** Two repositories with identical logical IDs and revisions
  could share a process-global cached workspace.
- **Root cause:** The cache key contained only the workspace revision.
- **Fix:** Cache identity now includes resolved database path and filesystem file
  identity while preserving the bounded warm cache.
- **Regression test:** `test_workspace_cache_is_namespaced_by_database_identity`.
- **Authority impact:** Prevents cross-repository history and authority display.
- **Performance impact:** One filesystem metadata read per workspace assembly;
  warm projection reuse remains enabled.
- **Remaining limitation:** The cache is process-local and intentionally bounded
  rather than distributed.

### AA-006 — Late UI mutations could overwrite a newer selected scope

- **Severity:** P2
- **Subsystem:** Engineer Crew Chief command deck
- **Failure mode:** A mutation begun for Run A could resolve after Run B or a new
  objective/report was selected and overwrite the newer workspace.
- **Root cause:** Initial reads had cancellation, but mutation responses had no
  shared latest-request sequence.
- **Fix:** Reads and mutations now share a monotonic latest-only sequence gate;
  superseded success, error, and busy-state writes are ignored.
- **Regression test:** Frontend contract asserts the shared sequence gate.
- **Authority impact:** Prevents stale UI presentation of an otherwise valid old
  workspace.
- **Performance impact:** None measurable.
- **Remaining limitation:** Network requests are not aborted; late results are
  safely discarded.

### AA-007 — Duplicate physical evidence lost memberships and provenance

- **Severity:** P1
- **Subsystem:** Crew Chief evidence index
- **Failure mode:** Repeated references to one event overwrote control keys,
  channels, blockers, and evidence state even though they remained one row.
- **Root cause:** Deduplication used last-write replacement for most metadata.
- **Fix:** One artifact now remains one independence unit while merging all
  mechanism, component, control, channel, lap, blocker, and polarity memberships;
  conflicting physical scope is rejected and conflicting evidence state is
  downgraded.
- **Regression test:**
  `test_one_physical_artifact_merges_memberships_without_multiplying_votes`.
- **Authority impact:** Prevents reference count or ordering from manufacturing
  stronger evidence.
- **Performance impact:** Linear merging within the already bounded evidence
  index.
- **Remaining limitation:** The index remains a navigation/provenance projection,
  not a causal ranker.

### AA-008 — Frontend evidence trust allowed foreign-run relabeling

- **Severity:** P2
- **Subsystem:** UI response trust and evidence navigation
- **Failure mode:** A malformed nested evidence entry could carry an undeclared
  run or reversed/non-finite window, and navigation relabeled it as the currently
  selected run.
- **Root cause:** The guard validated field shapes but not local saved-session run
  membership and the click handler ignored the entry's run identity.
- **Fix:** Crew Chief requests now carry the locally known run scope into the
  runtime guard; nested scope, uniqueness, finite-window, sentinel, and critic
  invariants are checked; navigation uses the evidence run ID.
- **Regression test:** Runtime hostile payload checks plus the frontend navigation
  contract.
- **Authority impact:** Prevents malformed or foreign evidence from being shown as
  current-run proof.
- **Performance impact:** Bounded set membership and uniqueness checks.
- **Remaining limitation:** Client validation is a presentation trust boundary;
  the backend remains authoritative for saved-session membership.

### AA-009 — Missing exact workflow history was silently skipped

- **Severity:** P2
- **Subsystem:** Active workflow and Component Response Atlas integrity
- **Failure mode:** An unreadable active workflow or an exact controlled-history
  record whose workflow/card could not be reproduced degraded to no history.
- **Root cause:** Broad lookup catches converted integrity failures to `None` or
  continued past them.
- **Fix:** Active and exact-history workflow lookup now fails closed with explicit
  integrity debt; no cached workspace or response record is produced.
- **Regression test:** Covered by surrounding Crew Chief, workflow-integrity, and
  real-workspace suites; a malformed workflow cannot reach presentation.
- **Authority impact:** Prevents silent repair or relabeling of controlled history.
- **Performance impact:** No added lookup; existing lookup failures are surfaced.
- **Remaining limitation:** Corrupt history must be repaired or removed through an
  explicit owner-approved recovery process.

### AA-010 — Warm Crew Chief assembly rebuilt full lap context

- **Severity:** P3
- **Subsystem:** Run intelligence / lap engineering context performance
- **Failure mode:** A warm real-Atlanta Crew Chief request remained about 3.38
  seconds because every call rebuilt 29 eligible-lap contexts from 63,657 rows.
- **Root cause:** Context building scanned the full row set once per eligible lap,
  and no immutable-artifact cache retained the finished typed report.
- **Fix:** Rows are grouped by lap in one pass, and the finished report is cached
  by database, data root, run, source-file hash, and telemetry-cache hash.
- **Regression test:** `test_lap_context_groups_rows_in_one_pass` plus the existing
  context semantic and real-fixture suites.
- **Authority impact:** None; cached results remain bound to immutable source and
  cache identities.
- **Performance impact:** Real Atlanta Crew Chief measured 3,317.595 ms warm
  before and 148.147 ms warm after final immutable-identity rechecks (95.5%
  reduction). Direct lap context measured 2,971.191 ms cold and 10.437 ms warm.
- **Remaining limitation:** Cold assembly is still dominated by row materialization
  and channel-semantic aggregation; further optimization requires a separately
  measured frame-native implementation.

### AA-011 — Event-stream tail deletion was not detectable

- **Severity:** P2
- **Subsystem:** Crew Chief append-only event history
- **Failure mode:** Deleting the final event left a shorter but internally
  contiguous sequence, so restart folding could silently forget the latest
  question, answer, critique, or decision.
- **Root cause:** Each event was hashed and sequence-checked, but the owning
  investigation did not retain an independently checked stream count and head.
- **Fix:** Investigation rows now hold an atomically advanced event count and head
  hash. Every fold verifies the persisted count and final hash after validating
  each event. Existing databases receive an additive one-time backfill.
- **Regression test:** `test_event_store_rejects_silent_tail_deletion`.
- **Authority impact:** Prevents deletion from reopening an older actionable
  investigation reality.
- **Performance impact:** One atomic row update per append and one indexed owner
  read per fold.
- **Remaining limitation:** This detects accidental or partial tampering; an
  attacker able to coherently rewrite the database and all hashes is outside the
  local integrity model.

### AA-012 — Crew Chief path identities were unbounded

- **Severity:** P3
- **Subsystem:** Public API input boundary
- **Failure mode:** Request bodies were bounded and extra-forbid, but run and
  investigation path identities accepted arbitrarily large strings before the
  repository lookup.
- **Root cause:** Route path parameters used unconstrained strings.
- **Fix:** All seven Crew Chief routes now require non-empty path identities with
  the same 160-character ceiling as session identities.
- **Regression test:** OpenAPI contract verifies min/max bounds on every Crew
  Chief path parameter.
- **Authority impact:** None; reduces malformed-input and resource-abuse surface.
- **Performance impact:** Rejects oversized identities before storage access.
- **Remaining limitation:** Deployment-level request-size and rate limits remain
  the responsibility of the API host.

### Validation evidence

Final whole-repository and focused release evidence is recorded in the commit
that closes this audit. Data-locked P21/P22/P30 capabilities remain locked.
