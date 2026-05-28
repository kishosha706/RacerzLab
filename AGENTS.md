# RaceLab Garage Agent Rules

- Evidence first. Recommendations must point to telemetry evidence.
- No junk-lap conclusions. Out-laps, cooldowns, wrecks, pit-road laps, invalid-speed laps, and partial laps cannot drive setup recommendations unless the user explicitly overrides that.
- Do not overclaim exact drag from `.ibt`. The app may identify drag/scrub-like behavior, but it must not claim an exact aerodynamic drag force or coefficient.
- Treat aero/load values as proxies unless directly supported by measured channels and complete vehicle constants. Prefer reliable run-to-run comparison over unsupported absolute force claims.
- Compare future runs by track position, not sample index.
- One setup change at a time. Multiple unrelated setup changes reduce confidence.
- Draft and solo laps must not be treated the same.
- Short runs cannot support strong tire degradation or cooling conclusions.
- Setup values must link back to telemetry events.
- Prefer small, tested increments.
- Do not implement unsafe cheating, live manipulation, input automation, or anything that violates iRacing rules.

## UI Mode Behavior

- **Race Mode** (default): short, direct, decision-first. Minimal explanation. Strong action verbs.
- **Learning Mode**: verbose, coaching style. Explains *why* this matters. Includes channel definitions, confidence caveats, related setup areas.
- Mode toggle: `L` key or click the mode badge in RunContextBar. Store value is `selection.selectedMode` (`"race"` | `"learning"`).

## Vectorized Engine

- Row engine (`normalize_telemetry_rows`) is the **production default**.
- Vectorized engine (`normalize_telemetry_frame`) is **opt-in** via `RACELAB_ANALYSIS_ENGINE=vectorized`.
- Do not switch the default without road course + short-track real .ibt validation.
- See `racelab_engine/analysis/DESIGN_NOTES_vectorized_future.md` for full status.
