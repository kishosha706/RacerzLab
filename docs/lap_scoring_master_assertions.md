# Lap Scoring — Master Assertions

These assertions govern the design and behavior of the RaceLab Garage lap scoring
system. Every scoring decision, label, and UI element must be consistent with
these principles.

---

## The Assertions

### 1. Fast does not mean trustworthy.
A lap or window can be fast because of traffic, favorable conditions, or limited context.
Performance and Trust are independent dimensions. High Performance with low Trust
should produce a "Fast but not trustworthy" classification.

### 2. Clean does not mean fast.
A solo, clean, well-measured lap may simply be slow. High Trust with low
Performance should produce a "Clean but not fast" classification.

### 3. Context can improve pace while reducing setup confidence.
High pace with weak context quality should reduce Trust via confidence penalties.
Performance may remain high, but Engineering Value (which weights Trust more
heavily) should drop when context confidence is weak.

### 4. Invalid laps should never strengthen a setup recommendation.
Wrecks, pit road, out laps, cooldown laps, and invalid speed events must cap
both Performance and Trust very low. They provide no useful setup signal.

### 5. Fastest single-lap pace and sustained pace are different rankings.
Fastest individual N-lap groups rank by raw lap time. Best consecutive windows
rank by average lap time of consecutive laps. These are conceptually separate
and must remain so. Fastest groups carry a warning: "peak pace, not sustained pace."

### 6. Falloff must eventually be interpreted by track type and run length.
The current falloff thresholds are general-purpose. Once track-type profiles are
available, falloff expectations should vary: superspeedways should show near-zero
falloff, while short tracks may show significant tire-driven falloff.

### 7. Tire/platform/shock stress matters more as windows get longer.
In short windows (5–10 laps), tire and shock data is less informative. In longer
windows (20–40 laps), degradation trends become meaningful. Future weighting
should increase tire/shock/platform weight with window size.

### 8. Missing data should reduce trust, not create fake bad performance.
When tire, shock, or platform data is unavailable, the Evidence Confidence score
should be reduced via deductions. The Performance score must NOT be penalized —
missing data does not mean the driver drove poorly.

### 9. RaceLab does not score driver skill.
The system scores lap data quality and setup usefulness, not driver ability.
Labels like "Performance" and "Trust" reflect data characteristics, not driver
talent. Never rename scores to imply driver skill assessment.

### 10. Every score must explain itself.
All three scores (Performance, Trust, Engineering Value) must be decomposable
into component scores. Deductions and caps must be enumerable. Warnings must be
exposed. Users should always be able to understand *why* a score is what it is.

---

## Implementation Checklist

- [x] Performance and Trust are independent dimensions
- [x] Confidence penalties can reduce Trust while Performance remains high
- [x] Wreck/spin caps both scores very low
- [x] Pit road caps both scores very low
- [x] <60% valid laps caps Trust
- [x] Missing data reduces Trust, not Performance
- [x] Fastest groups ranked by raw lap time, not Engineering Value
- [x] Best windows ranked by average lap time of consecutive laps
- [x] Fastest groups carry "peak pace" warning
- [x] Component scores are exposed in the result
- [x] Deductions and caps are enumerable
- [x] Warnings are exposed
- [ ] Track-type-specific profiles (deferred — see `lap_scoring_track_profiles_future.md`)
- [ ] Window-length-dependent tire/shock weighting (deferred)
