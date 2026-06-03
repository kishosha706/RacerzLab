# Setup Guide Digest

Milestone 3A adds a source-backed digestion layer for the RacerZLab master setup
matrix. The matrix remains the source note. Runtime setup logic uses reviewed
local JSON records under `racelab_engine/knowledge/setup/data`.

The digest layer provides:

- guide source records
- accepted setup principles
- term definitions
- matrix-derived setup mappings
- review queue items
- source IDs on setup effects
- query and export scripts

The pre-3B quality review keeps the digest implementation-facing. It reinforces
that source-backed guide records feed deterministic effect/counter-effect
language, phase-aware setup mappings, package context, and review status. Guide
content should teach tradeoffs; it should not become copied guide prose, exact
universal setup values, runtime AI behavior, or telemetry formulas.

Next Gen diffuser/front-feed wording remains conservative: front ride-height
platform helps define diffuser feed, rear ride-height platform helps define
outlet/expansion and scrape/choke context, and diffuser metrics are derived
geometry proxies rather than measured downforce. Shock histogram language stays
as evidence for a phase/zone-specific call, not proof by itself.

This is local and deterministic. It does not call external AI, add API keys,
build a crew-chief UI, alter telemetry formulas, change imports, or change
public API schemas.

Useful commands:

```powershell
python -B scripts/digest_setup_guides.py
python -B scripts/query_guide_knowledge.py --setup-area ls_rebound --car-family next_gen
python -B scripts/query_guide_knowledge.py --topic diffuser --car-family next_gen
python -B scripts/export_setup_knowledge_digest.py
```

CFS/front-feed notes that mention an approximately 0.5 inch opening are stored
as `needs_review` until verified. They are not accepted rules and should not be
used as setup logic before verification.

Next step after source digestion is now implemented: the Evidence Adapter
translates local telemetry, Compare output, setup snapshots, and notebook
context into existing evidence tags without inventing new setup rules outside
the reviewed matrix-backed records. See `docs/setup_evidence_adapter.md`.
