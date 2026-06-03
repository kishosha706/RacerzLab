# RacerZLab Setup Knowledge Foundation

This package is the local, deterministic setup-knowledge layer for RacerZLab.
It does not call external AI, does not require API keys, and does not change
telemetry formulas, import behavior, or public API schemas.

The flow is:

1. Parse driver vocabulary into a canonical symptom.
2. Apply car-family capability gates.
3. Rank setup effects by symptom, phase, strength, risk, and placeholder evidence.
4. Return one-change test language with required evidence and validation targets.

Next Gen capability gates disable `track_bar`, `truck_arm_mount`, `bump_stop`,
and `packer`. Those areas remain in the global oval knowledge base for legacy
or car-specific oval packages.

Run:

```powershell
python -B scripts/validate_setup_knowledge.py
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off"
```
