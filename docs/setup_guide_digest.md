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
as `needs_review` until verified.
