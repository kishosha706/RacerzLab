# Future Track-Profile Weighting — Scaffolding

> **Status:** Deferred — not yet implemented.
> **Reason:** Insufficient real .ibt validation samples across track types.
> **Target:** Revisit after collecting .ibt files from superspeedway, short track,
> mile-and-a-half/intermediate, road course, longer stints, and sparse/missing-channel files.

---

## Why Dynamic Track-Type Weighting Is Deferred

The current scoring system uses fixed weights that are reasonable across all track
types but optimal for none. Dynamic track-type weighting would improve accuracy,
but it risks overfitting to the limited samples we have today (primarily one
superspeedway configuration). We need representative .ibt data from at least
3–5 distinct track types before tuning track-specific profiles.

## Needed Validation Samples

| Track Type | Example Tracks | Priority | Why |
|---|---|---|---|
| Superspeedway | Talladega, Daytona | High | Draft-heavy, high-speed, pack racing |
| Short track | Bristol, Martinsville, Richmond | High | High steering load, frequent braking, tire stress dominant |
| Mile-and-a-half / Intermediate | Charlotte, Kansas, Texas, Las Vegas | High | Balance of speed and tire management |
| Road course | Watkins Glen, Road Atlanta, Spa, Nürburgring | High | Left+right turns, elevation, braking zones |
| Longer stint (40+ laps) | Any track | Medium | Falloff behavior at scale, tire degradation |
| Sparse / missing-channel file | Any track with limited telemetry | Medium | Data completeness scoring validation |

## Future Candidate Profiles

Each profile would adjust the scoring weights and thresholds for its track type:

### `superspeedway`
- **Draft penalty severity:** Higher — draft is more common and more impactful
- **Consistency threshold:** Tighter — pack racing produces naturally consistent times
- **Falloff expected range:** Lower — less tire stress at high speed
- **Tire/shock weighting:** Lower — less cornering load
- **Platform weighting:** Lower — less ride-height sensitivity at high speed

### `intermediate_oval`
- **Draft penalty severity:** Moderate — some draft but not pack racing
- **Consistency threshold:** Moderate
- **Falloff expected range:** Moderate — tire falloff matters
- **Tire/shock weighting:** Moderate
- **Platform weighting:** Moderate

### `short_track`
- **Draft penalty severity:** Low — minimal draft effect
- **Consistency threshold:** Wider — more lap-to-lap variation from traffic
- **Falloff expected range:** Higher — tire degradation is significant
- **Tire/shock weighting:** Higher — cornering load dominates
- **Platform weighting:** Higher — ride height and bump sensitivity

### `road_course`
- **Draft penalty severity:** Low (except long straights)
- **Consistency threshold:** Wider — traffic, track limits, braking variation
- **Falloff expected range:** Moderate — brake fade + tire falloff
- **Tire/shock weighting:** Higher — cornering and braking loads
- **Platform weighting:** Higher — elevation changes, curbs

## Future Candidate Tuning Dimensions

### Consistency threshold by lap time / track type
Currently: `good=0.001, bad=0.007` (percentage of avg lap time)
Future: Could vary by track type — short tracks may need wider bands.

### Falloff expected range by track type
Currently: `good=0.0002, bad=0.0020` (percentage per lap)
Future: Superspeedway falloff should be nearly zero; short track falloff is expected.

### Tire/shock/platform weighting by window length
Currently: Fixed weights regardless of window size.
Future: Longer windows could increase tire/shock weight (degradation matters more).

### Draft penalty severity by track type
Currently: Fixed deduction amounts.
Future: Superspeedway could have higher draft deductions; short track lower.

### Run-shape classification
Future: Classify runs as "sprint", "feature", "qualifying simulation" based on
lap count and adjust expectations accordingly.

## Wiring Plan (Future)

1. Detect track type from session metadata or track name matching
2. Load profile-specific weights/thresholds from a profile dictionary
3. Pass profile to `compute_pace_quality_score()` as an optional parameter
4. Fall back to default (intermediate/general) profile when track type is unknown

```python
# Future sketch — not implemented
TRACK_PROFILES = {
    "superspeedway": {...},
    "intermediate_oval": {...},
    "short_track": {...},
    "road_course": {...},
}

def compute_pace_quality_score(
    ...,
    track_profile: str | None = None,
) -> PaceQualityResult:
    profile = TRACK_PROFILES.get(track_profile, TRACK_PROFILES["intermediate_oval"])
    # Apply profile-specific weights and thresholds
    ...
```

## Risks

- Overfitting to a single track type would degrade scoring on all others
- Track type detection from session metadata may be unreliable for some imports
- Profile switching could cause confusing score jumps when comparing across track types
- Maintaining multiple profiles increases testing surface area significantly

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-28 | Defer dynamic track-type weighting | Insufficient .ibt variety; risk of overfitting to superspeedway data |
