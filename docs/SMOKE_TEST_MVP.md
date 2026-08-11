# RaceLab Garage - Current Product Smoke Test

Use this workflow to verify the current evidence-to-controlled-test loop. It is
not a compatibility test for removed screens or fields.

Last reviewed: 2026-08-10

## Prerequisites

- Start the desktop app with `npm run desktop`.
- Have one source-owned `.ibt` available. A second compatible run is useful for
  the Laps comparison workbook.
- For an authority-path smoke, use a fixture with a valid server-owned P19
  controlled workflow. An ordinary or traffic-contaminated run should remain
  measurement-only.

## 1. Launch and session

- Confirm the app opens to the session screen and the backend health check
  succeeds at `http://127.0.0.1:8010/api/health`.
- Create a session or open an existing one.
- Confirm the cockpit shows exactly these primary workspaces: Overview,
  Engineer, Laps, Platform, Setup, and Dial-In.
- Toggle Race/Learning mode with the mode badge or `L`. The explanation depth
  may change; authority must not.

## 2. Import and ownership

- Import a `.ibt` through the session tools.
- Confirm the run appears only after persistence and cockpit loading succeed.
- Confirm car, track/configuration, setup, lap count, and run identity match the
  imported source.
- Open telemetry capability detail and confirm declared/cached channel health is
  explicit. Missing or unhealthy channels must appear as debt, not zero.
- Re-importing the same source must not erase controlled-workflow history.

## 3. Overview

- Confirm best-lap and primary findings are based only on currently eligible
  laps.
- Confirm invalid, out, cooldown, pit, wreck, reset, and partial laps do not
  drive a setup call.
- Confirm Overview events show observations and evidence only. There must be no
  recommendation list, crew-chief summary, event action, or next-test field.
- A run with no supported finding must say that no supported finding was
  returned; it must not imply every system is proven healthy.

## 4. Engineer

- Open Engineer and confirm the report belongs to the selected run/session and
  current lap/window scope.
- In Race Mode, confirm one concise trustworthy move is shown.
- In Learning Mode, inspect evidence, competing causes, blockers, citations,
  vehicle-system context, and measurement debt.
- Follow a citation and confirm it opens the exact run, lap/phase, and physical
  region cited.
- Change run or lap while a report is loading. A late response for the old
  scope must not render.

## 5. Laps and comparison workbook

- Confirm the timing sheet and stint map visibly separate eligible and excluded
  laps and break continuity across missing/invalid lap numbers.
- Confirm short or split runs withhold long-run/tire-degradation conclusions.
- Add compatible baseline/test windows to the comparison basket and open the
  workbook.
- Confirm traces align by physical track position, retain gaps, and label proxy
  channels.
- Confirm Compare shows measured deltas, setup/context differences, discipline,
  warnings, and an observation state only. It must not show Keep, Undo, a setup
  recommendation, or a next setup step.

## 6. Platform and Shock Reader

- Open Platform and confirm loading, findings, clear, unavailable, and error are
  visually distinct.
- Confirm Platform uses structured platform events. Overview events must not
  appear as a fallback event set.
- Inspect a platform event and confirm it shows evidence/blockers without a
  recommended action.
- Open shock detail and confirm histograms state the selected lap/window/zone,
  boundary basis, sample coverage, and current damper context.
- Confirm Shock Reader shows `setup authority withheld` and no click direction,
  target, delta, setting action, Keep/Undo, or test-plan text.

## 7. Setup

- Confirm Current view shows the selected run's captured setup and exact setup
  identity.
- Confirm Diff is available only for a distinct, current-scope baseline with a
  real compatible setup snapshot.
- Confirm highlighted related controls are context, not an instruction to
  change them.
- Confirm unavailable geometry/load quantities stay explicitly unavailable or
  proxy-labeled.

## 8. Dial-In without earned authority

- Enter a complaint and, if needed, select its phase/location.
- Confirm public Dial-In returns non-authorizing control-area hypotheses,
  mechanisms to verify, counter-effects, evidence locations, and blockers.
- Confirm it does not publish direction, increment, current/target setup values,
  `Change this`, Keep, or Undo language.
- With insufficient, contaminated, short, mismatched, or unsupported evidence,
  confirm the result requests measurement or refuses a setup call.
- A generic complaint such as `loose` must request clarification instead of
  pretending certainty.

## 9. P19 controlled workflow

Run this section only with a server-qualified controlled workflow.

- Confirm the exact proposed control and legal adjacent value appear only in
  the P19 authority card/workflow.
- Confirm the mission freezes source run/session, setup hash, reasoning hash,
  evidence channels, physical scope, warm-up/measured cohorts, guardrails, and
  rollback.
- Attach A, B, and restored A2 using server-qualified non-overlapping cohorts.
- Confirm scoring keeps mechanism response, control response, countereffects,
  and Keep/Undo policy separate.
- Confirm an unchanged prior Undo or completed stop-testing contract blocks a
  repeated policy while an unrelated control remains independently testable.
- Confirm corrupt, stale, duplicate, overlapping, foreign, or client-attested
  evidence fails closed.

## 10. Persistence and recovery

- Close and reopen the app. Confirm the session, run membership, selected
  context, controlled workflow, immutable attempts, and report history reload
  without being rebound to another run.
- Confirm stale setup/reasoning identity disables authority until a fresh
  server projection is loaded.
- Confirm a failed import or cache cleanup does not remove the original `.ibt`,
  run metadata, setup snapshot, observation records, or controlled history.

## Optional Notebook API check

Notebook is not a primary workspace. If its observation API is exercised,
confirm only save/list/get/update finding operations exist. Records may contain
observation evidence, notes, tags, and `saved`/`archived` state. Requests that
send verdict, setup-change, next-step, test-plan, or setup-memory fields must be
rejected.

## Result checklist

| Area | Expected | Actual |
|---|---|---|
| Import | Source-owned run and complete capability truth | |
| Overview | Eligible observations; no setup action | |
| Engineer | Exact-scope trusted report and citations | |
| Laps/Compare | Position-aligned observations; no policy | |
| Platform | Structured events; honest unavailable/error states | |
| Shock Reader | Movement observation; authority withheld | |
| Setup | Captured values and differences only | |
| Dial-In | Hypotheses/measurement until P19 earns authority | |
| P19 workflow | One exact server-authorized test or refusal | |
| Restart | Identity-bound state reconstructs safely | |
