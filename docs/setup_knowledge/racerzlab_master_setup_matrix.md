# RacerZLab Master Setup Matrix v1  
## Oval + NASCAR Next Gen Setup Knowledge Pack

> **Purpose:** This document consolidates the oval setup matrices, oval setup flowcharts, iRacing setup process notes, NASCAR Next Gen manual facts, shock tuning guide concepts, and RacerZLab product logic into one implementation-ready knowledge source.  
>  
> **Use this as a seed/source note for RacerZLab’s local setup-knowledge system.** It is not a copied setup guide. It is RacerZLab-owned wording, built to become structured rules, effects, counter-effects, evidence requirements, package archetypes, and crew-chief responses.

---

## 0. Where this document belongs

Recommended repo location:

```text
racelab-garage/docs/setup_knowledge/racerzlab_master_setup_matrix.md
```

Also copy locally for guide ingestion/dev tooling if the app expects local source guides here:

```text
racelab-garage/data/knowledge/source_guides/racerzlab_master_setup_matrix.md
```

Recommended `guide_sources.json` record:

```json
{
  "source_id": "racerzlab_master_setup_matrix_v1",
  "title": "RacerZLab Master Setup Matrix v1",
  "source_type": "research_report",
  "domain": "oval",
  "car_scope": "next_gen_and_legacy_oval",
  "file_name": "racerzlab_master_setup_matrix.md",
  "local_path": "docs/setup_knowledge/racerzlab_master_setup_matrix.md",
  "status": "accepted",
  "notes": "RacerZLab-owned consolidated setup knowledge from user-provided setup guides, matrices, flowcharts, and Next Gen notes."
}
```

Runtime should not require raw PDFs or images. Runtime should use reviewed JSON rules derived from this document.

---

# 1. Core RacerZLab Setup Philosophy

## 1.1 The setup loop

RacerZLab should operate like a disciplined crew chief:

```text
Driver complaint
→ vocabulary parser
→ canonical symptom
→ corner phase
→ car capability gate
→ package/archetype interpretation
→ evidence check
→ setup-effect ranking
→ effect/counter-effect explanation
→ one small swing
→ compare validation
→ quiet memory
```

## 1.2 The non-negotiable rules

1. **Baseline first.**  
   Start from a known baseline setup or known reference package.

2. **One change at a time.**  
   Do not stack major changes unless the user explicitly marks it as an experiment.

3. **Every change has a counter-effect.**  
   A setup swing that helps entry may hurt center or exit. A spring/collar swing may change ride height, cross, platform, and tire load together.

4. **Do not judge one setup value alone.**  
   A fast setup is a package.

5. **Static setup is not dynamic telemetry.**  
   Garage values are static. Platform/rake/shock/tire behavior happens dynamically on track.

6. **Proxy is not measured downforce.**  
   Diffuser/platform channels are derived geometry proxies, not measured downforce.

7. **If evidence is missing, say so.**  
   Do not fill missing values with zeros. Do not guess.

8. **Use crew-chief language.**  
   Driver-facing responses should say:
   - “Try one small swing.”
   - “Effect: …”
   - “Counter-effect: …”
   - “Watch: …”
   - “Validate: …”

9. **Do not sound robotic.**  
   Avoid:
   - “AI recommends…”
   - “Guaranteed…”
   - “Always…”
   - “This value is wrong…”
   - “Set this exact value…”

---

# 2. Car Capability Gating

## 2.1 NASCAR Next Gen available setup areas

Next Gen available areas:

```text
tire_pressure
camber
caster
toe
spring_rate
shock_collar
ride_height
front_ride_height_platform
rear_ride_height_platform
diffuser_platform
cross_weight
nose_weight
front_arb_diameter
front_arb_arm
front_arb_preload
front_arb_attach
rear_arb_diameter
rear_arb_arm
rear_arb_preload
rear_arb_attach
brake_bias
front_master_cylinder
rear_master_cylinder
ls_compression
hs_compression
hs_comp_slope
ls_rebound
hs_rebound
hs_reb_slope
diff_preload
final_drive
```

## 2.2 NASCAR Next Gen disabled setup areas

Next Gen does **not** have these legacy oval adjustment families in the guide system:

```text
track_bar
truck_arm_mount
bump_stop
packer
```

Rules:

- Never recommend track bar, truck arm, bump stop, or packer adjustments for Next Gen.
- Keep these in the global oval knowledge base for supported legacy cars.
- If a driver asks about them while on Next Gen, respond:

```text
That adjustment is not available on this car. For Next Gen, inspect rear platform, spring/collar, ARB, shocks, crossweight, tire pressure, or diffuser/platform evidence instead.
```

## 2.3 Next Gen ARB constraints

Next Gen ARB must be modeled as discrete car-specific controls.

### ARB diameter

```text
1.375 in = soft bar
2.000 in = stiff bar
```

ARB diameter is a **package-level swing**.

```text
Effect strength: 4–5
Coupling risk: high
```

### ARB arm

```text
P1 = softest
P2
P3
P4
P5 = stiffest
```

ARB arm is a **tuning swing** within the selected bar package.

```text
Effect strength: 3–4
Coupling risk: medium/high
```

### ARB preload

ARB preload is a load/detail swing.

```text
Effect strength: 2–4 depending evidence
Coupling risk: medium/high
```

### ARB attach

ARB attach is a setup/procedure state, not a normal “go race like this” recommendation.

---

# 3. Effectiveness Scale

## 3.1 Strength scale

| Strength | Label | Meaning | Driver-facing wording |
|---:|---|---|---|
| 5 | Major package lever | Can move the whole car package. | “This is a package-level lever. Test carefully.” |
| 4 | Strong balance/platform lever | Can fix a phase but may hurt another. | “Strong swing. Watch the counter-effect.” |
| 3 | Medium phase lever | Useful when symptom and evidence agree. | “Good phase-specific test.” |
| 2 | Fine tuning | Best once the main balance is close. | “Polish swing.” |
| 1 | Driver feel | Mostly feel/comfort/response. | “Feel adjustment.” |

## 3.2 Coupling risk

| Risk | Meaning | Product behavior |
|---|---|---|
| High | Changes multiple phases or package balance | Warn clearly. Do not stack with another major change. |
| Medium | Strong in one phase/system | Show phase counter-effect. |
| Low | Mostly localized or feel-based | Still validate, but lower warning. |

## 3.3 Starting strength priors for oval / Next Gen

| Setup area | Strength | Risk | Notes |
|---|---:|---|---|
| Diffuser/platform / dynamic ride-height package | 5 | High | Major speed/balance/window lever. |
| Ride height / shock collar / platform support | 5 | High | Changes platform, corner load, aero attitude, cross. |
| Springs | 4–5 | High | Holds platform; trades aero attitude vs mechanical grip. |
| Cross weight | 4 | High | Strong oval stability/rotation lever. |
| ARB diameter | 4–5 | High | Big package change. |
| ARB arm | 3–4 | Medium/high | Tuning swing. |
| Diff preload | 4 | High | Affects accel/decel/mid behavior. |
| Final drive | 4 | Medium | Exit acceleration vs top speed. |
| Tire pressure | 3–4 | Medium | Grip, response, heat, support, drag. |
| Brake bias | 3 | Medium | Entry/braking phase lever. |
| Camber | 3 | Medium | Center grip vs braking/traction/tire life. |
| Toe | 3 | Medium | Response/stability/scrub/straight speed. |
| Shocks | 2–4 | Medium | Usually tuning/polish unless evidence points to transition/bump/platform issue. |
| Caster | 1–2 | Low/medium | Driver feel, dynamic load feel, steering weight. |

---

# 4. Phase Model

| Phase | Driver terms | Definition | Evidence | Setup areas |
|---|---|---|---|---|
| Braking | brake zone, whoa-up, on pedal | Deceleration before/with steering | brake %, decel, rear yaw, front dive, wheel speed | brake bias, front LS compression, rear rebound, diff preload, front support |
| Turn-in | initial cut, set, take a set | Steering onset and first yaw response | steering rate, yaw response, speed loss, platform pitch | toe, caster, front ARB, front spring, LS damping |
| Entry | in, entry, getting in | Brake release to early corner rotation | yaw gain, rear slip, correction, brake release | brake bias, cross, front support, rear rebound, diff coast/preload |
| Center | middle, center, apex | Minimum-speed / steady-state balance | steering demand, yaw, min speed, tire temps, ride heights | cross, ARB, spring package, camber, tire pressure, platform |
| Exit | off, drive off, throttle up | Throttle pickup to track-out | throttle, yaw, wheelspin, exit speed, rear shock | diff/preload, rear spring/ARB, rear LS comp/rebound, rear toe, cross |
| Straight | straightaway, pulls, draggy | Full-throttle speed section | speed, RPM, gear, throttle, steering/yaw scrub, contact | gearing, toe, platform contact, aero trim, ride height, scrub |
| Transition | bumps, curb, banking change | Load spike or direction/load change | shock velocity spikes, ride-height min, yaw spike | HS compression/rebound/slope, spring, collar, bumpstop/packer if supported |
| Whole run | falls off, burns tire | Multi-lap trend | lap falloff, tire temps, wear, steering growth, speed fade | pressures, camber, cross, ARB, platform consistency |
| Short run | fires off, first laps | Early stabilized laps | early balance/speed, cold-to-warm pressure | pressures, qualifying setup, aggressive platform |
| Long run | run, stint, falls off | Later laps | degradation rate, tire temp/pressure/wear trend | tire protection package, camber, pressure, cross, shocks |

---

# 5. Driver Vocabulary → Canonical Symptoms

## 5.1 Core oval vocabulary

| Driver phrase | Canonical symptom | Phase | Notes / clarification |
|---|---|---|---|
| tight | tight_unknown | unknown | Ask entry/center/exit. |
| push | tight_unknown | unknown | Ask phase. |
| plowing | tight_center / tight_exit | center/exit | Usually nose misses line. |
| washed up track | tight_center / tight_exit / drag_scrub | center/exit | Ask if steering/speed loss. |
| bound up | tight_center / drag_scrub | center | Often cross/ARB/platform bind. |
| lazy | tight_entry / lazy_turn_in | entry | Ask if slow to take set or rotate. |
| won’t rotate | tight_center | center | Could be entry if said “in.” |
| won’t point | tight_entry / tight_center | entry/center | Steering builds without yaw. |
| tight in | tight_entry | entry | Entry/brake/turn-in. |
| tight center | tight_center | center | Direct. |
| tight off | tight_exit | exit | Under throttle wash. |
| free | loose_unknown | unknown | Ask where. |
| loose | loose_unknown | unknown | Ask where. |
| loose in | loose_entry | entry | Rear yaw on entry. |
| loose center | loose_center | center | Rear slip steady-state. |
| loose off | loose_exit | exit | Rear step under throttle. |
| free off | loose_exit | exit | Same as loose off. |
| snaps loose | unstable_entry / unstable_exit | transition | Ask input trigger. |
| snaps loose on throttle | unstable_exit / loose_exit | exit | Throttle transition. |
| rear stepping out | loose_entry / loose_exit | entry/exit | Ask brake or throttle. |
| skating | shock_overactive / platform_instability | transition | Ask bumps/center/exit. |
| burns RF | tire_overwork / tight_center | long_run/center | Check tire trend. |
| burns RR | tire_overwork / loose_exit | long_run/exit | Check tire/drive. |
| falls off | long_run_falloff | whole_run | Ask tight/loose/speed fade. |
| lacks drive | poor_drive_off | exit | Spin or bound? |
| draggy | low_straight_speed / drag_scrub | straight | Normalize exit speed first. |
| bottoming | platform_contact | transition/high-load | Clarify front or rear. |
| splitter hitting | front_platform_contact | braking/high-load | Front platform. |
| rear scrape | rear_scrape | high-load/straight/exit | Rear platform/contact. |
| pack unstable | diffuser_instability / unstable | traffic | Worse in traffic. |
| tight rolling center | tight_center | center | Direct. |
| tight under throttle | tight_exit | exit | Throttle-wash. |
| won’t stay on bottom | tight_center / tight_exit | center/exit | Check line + steering. |
| misses apex | tight_entry / tight_center | entry/center | Ask timing. |
| pushes up | tight_center / tight_exit | center/exit | Direct. |
| sideways off | loose_exit | exit | Throttle/yaw. |
| wheel hop | shock_overactive / driveline | transition | Check shocks/diff/track. |
| chatters | shock_overactive / tire_overwork | transition | Check bumps/tire. |
| too planted | tight_center / bound | center | Could mean stable but slow. |
| too stuck | tight_center | center | Bound/over-secure. |
| won’t take a set | tight_entry / platform_instability | entry | Entry platform. |
| takes too long to set | tight_entry | entry | Transient control. |
| nose falls over | front_platform_contact / brake_entry | braking/entry | Front support. |
| rear hikes up | rear_platform_instability | entry/transition | Rear rebound/platform. |
| RF angry | tire_overwork | run/center | RF tire trend. |
| LR loaded | cross/platform | center/exit | Check cross and LR tire/shock. |
| rear won’t stay under me | loose_exit / unstable_exit | exit | Rear security. |

## 5.2 Generic phrase rules

```text
"off" = exit
"in" = entry
"center", "middle", "rolling" = center
"draggy", "straight", "slow down straight" = low_straight_speed / drag_scrub
"bottoming", "scrape", "hitting" = platform_contact, ask front/rear if unclear
generic "tight" or "loose" = ask clarification
```

---

# 6. Master Setup Area Matrix

## 6.1 Tires / pressure / temperature / wear

### Tire pressure general logic

| Setup area | Increase / raise | Decrease / lower | Helps | Counter-effect | Evidence | Strength/Risk |
|---|---|---|---|---|---|---|
| Tire pressure | Stiffer sidewall, more response, can support higher load and reduce deflection/drag | More compliance/grip at lower load, less response | Response, platform support, heat control depending tire | Too high can reduce grip or overwork tire; too low can heat/drag/sluggish feel | cold/hot pressure, pressure gain, O/M/I temps, wear, run length | 3–4 / Medium |
| LF pressure | Often used to calm or tune front response | Can add LF compliance | Entry/center feel | May slow response or increase heat | LF temps, steering, entry response | 3 / Medium |
| RF pressure | Supports most-loaded front on oval; can calm/shape RF work | Can add RF grip if over-supported | Center, long-run RF management | Too much can push/heat; too little can overwork or collapse support | RF temp/wear/pressure gain, steering | 3–4 / Medium |
| LR pressure | Can calm rear rotation / add support depending package | Can add rear bite/compliance | Entry/drive-off package | May hurt drive-off or change long-run rear bite | LR temp/pressure, exit yaw, drive-off | 3 / Medium |
| RR pressure | Supports loaded rear, affects exit/security | Can add rear compliance | Exit/drive-off | Too low can overheat/drag; too high can loosen or reduce bite | RR temp/wear/pressure, throttle yaw | 3 / Medium |

### Oval matrix-derived tire swings

| Condition | Candidate tire swings | Effect | Counter-effect |
|---|---|---|---|
| Loose entry | Add LR pressure, reduce LF pressure, add rear stability pressure split | Calms rear rotation / softens front response | May hurt drive-off or make center lazy |
| Tight entry | Lower LR/RR support or free front response depending tire evidence | Helps rotation/turn-in | Can destabilize entry |
| Loose center | Add rear support or reduce front aggression | Adds security | May tighten center or reduce rotation |
| Tight center | Reduce RF overwork / free front / manage cross-pressure split | Helps rotation | Can give up entry/exit stability |
| Loose exit | Add rear tire support, stabilize pressure split | Calms throttle yaw | May reduce rear bite later |
| Tight exit | Free rear or reduce bind pressure trend | Helps drive-off rotation | Can loosen exit |

---

## 6.2 Alignment: Toe, camber, caster

### Toe

| Setup area | Direction | Effect | Counter-effect | Evidence | Strength/Risk |
|---|---|---|---|---|---|
| Front toe-in | More stability, slower initial response | Stable braking/straight | Adds scrub and slows straight; can feel lazy | straight speed, steering, tire heat | 3 / Medium |
| Front toe-out | Faster turn-in | Helps lazy entry / turn-in | Less straight stability, more scrub, can over-slip front | turn-in yaw, RF temp, straight speed | 3 / Medium |
| Rear toe-in | Rear stability | Helps loose entry/exit, straight stability | Can bind center or add drag | rear yaw, straight stability, tire heat | 3 / Medium |
| Rear toe-out | More rear rotation | Helps tight entry/center in some cars | Can quickly transition to loose/unstable | yaw/countersteer, entry stability | 3 / Medium |

### Matrix-derived toe patterns

| Symptom | Candidate | Effect | Counter-effect |
|---|---|---|---|
| Tight entry / lazy turn-in | Add front response via toe-out | Quicker turn-in | Straight speed/stability loss |
| Loose entry | Add rear toe stability or reduce aggressive front response | Calms rear | May tighten center |
| Low straight speed / draggy | Reduce toe scrub | Better speed | May reduce response/stability |
| Loose exit | Add rear toe stability where available | Calms throttle rear | May bind center/drag |

### Camber

| Setup area | Direction | Effect | Counter-effect | Evidence |
|---|---|---|---|---|
| More loaded-corner camber | More contact in loaded corner | Helps center grip | Can hurt braking/traction and tire life | O/M/I temps, wear, center speed |
| Less aggressive camber | Better braking/long-run/straight contact if overdone | Helps tire life and longitudinal grip | May reduce center grip | tire temps/wear, braking/exit |

Oval notes:

```text
Left side often positive, right side often negative on ovals.
Too much camber can help center but punish braking, exit, and tire life.
```

### Caster

| Setup area | Direction | Effect | Counter-effect |
|---|---|---|---|
| More caster / more split | Heavier centering, can influence turn-in/driver feel | More steering effort; can create exit/high-speed instability if overdone |
| Less caster | Lighter steering, can help shorter tracks/turning radius | Less centering/stability |

Caster is mostly driver feel / polish unless evidence directly points to steering response.

---

## 6.3 Springs, collars, ride height, and platform

### Springs

| Area | Stiffer | Softer | Helps | Counter-effect | Strength/Risk |
|---|---|---|---|---|---|
| Front springs | More front support/stability/platform control | More front compliance/grip | Entry/high-speed support, aero attitude | Stiffer can tighten center; softer can loosen or lose platform | 4–5 / High |
| Rear springs | More rear platform support/rotation depending package | More rear grip/compliance | Exit/platform/center package | Stiffer can loosen/lose rear grip; softer can tighten/lazy or scrape | 4–5 / High |
| RF spring | Adds RF support and can calm/hold platform | More compliance if reduced | Entry support, RF platform | May tighten center / reduce compliance | 4 / High |
| LR spring | Can affect drive, cross, and rotation package | More compliance/drive if reduced | Exit/center depending package | Can bind or loosen depending package | 4 / High |
| RR spring | Rear support / exit platform | Rear grip/compliance | Exit/high-speed | Can loosen exit if too stiff | 4 / High |

Matrix-derived common patterns:

| Symptom | Candidate spring idea | Effect | Counter-effect |
|---|---|---|---|
| Loose entry | Add front/RF support or add cross-supporting spring package | Calms entry | May tighten center |
| Tight center | Soften front / reduce bind / free center support | Helps rotation | May loosen entry/exit |
| Loose exit | Add rear support or stabilize spring/cross package | Calms throttle | May reduce drive if overdone |
| Tight exit | Free rear / reduce rear bind / adjust rear spring package | Helps drive-off rotation | Can make loose off |

### Shock collar / spring perch / ride-height support

| Setup area | Effect | Counter-effect | Evidence |
|---|---|---|---|
| Shock collar / perch | Changes preload, ride height, corner weight, cross depending corner and pairs | Can unintentionally change cross and platform while chasing height | setup snapshot, corner weights, ride-height trace |
| Ride height | Changes static attitude and dynamic platform/aero/mechanical window | Lower is not automatically faster; can contact/choke/destabilize | dynamic ride heights, scrape/contact, speed, yaw |
| Front ride-height platform | Defines CFS/front splitter/rub-block height, LF/RF, front center, feed/contact/dive | Too much support may tighten center; too little may contact/dive | CFS/front RH, entry, speed, scrape/contact |
| Rear ride-height platform | Defines rear outlet/expansion/scrape context | Too low may scrape/choke; too high may destabilize/drag depending package | rear center/RR/LR, scrape, speed, yaw |

---

# 7. Next Gen Diffuser / Front Feed Logic

## 7.1 Mandatory wording

Use:

```text
Front ride-height platform helps define diffuser feed.
Rear ride-height platform helps define diffuser outlet/expansion and scrape/choke context.
Diffuser metrics are derived geometry proxies, not measured downforce.
```

Do not use:

```text
Rear lower always means more rear downforce.
Front higher is automatically wrong.
Lower is always faster.
Rake sign alone decides aero.
Diffuser proxy equals measured downforce.
```

## 7.2 Definitions

### Front ride-height platform

Includes:

```text
CFS / center front splitter / front rub-block height
LF ride height
RF ride height
front center ride height
dynamic front pitch behavior
front splitter/rub-block clearance
front underbody inlet/feed behavior
front seal behavior
front attitude stability at speed
```

### Rear ride-height platform

Includes:

```text
LR/RR/rear center reference
rear diffuser outlet/expansion context
rear scrape/contact/choke risk
rear platform stability at speed
```

### Diffuser/platform system

Includes:

```text
front underbody feed
rear outlet/expansion
center rake
diffuser volume / wedge / base proxy
scrape/contact
speed loss
platform stability
```

## 7.3 CFS 0.5 inch opening / clearance note

Create this as `needs_review`, not accepted fact:

```text
User reports the CFS/front platform may include an approximately 0.5 inch opening/clearance feature that helps feed airflow toward the diffuser. Needs verification before being encoded as fact.
```

Do not encode as a confirmed source-backed fact until verified.

## 7.4 Diffuser/platform effects

| Effect ID | Effect | Counter-effect | Evidence | Validate |
|---|---|---|---|---|
| improve_front_feed_window | Helps keep the underbody feed usable instead of starving/choking the rear diffuser window | Can shift aero balance, tighten center, or change drag if overdone | CFS/front RH, diffuser proxy, speed, scrape | speed, yaw, front/rear RH |
| add_front_platform_support | Calms dive/contact and stabilizes front feed | May tighten center or reduce compliance | CFS min, front RH, entry instability | entry yaw, center speed |
| reduce_front_platform_support | Adds compliance/front grip if over-supported | May increase contact/dive or aero instability | shock/ride trace, tire grip, contact | contact, center speed |
| add_rear_platform_support | Controls rear squat/scrape/outlet instability | Can reduce rear mechanical grip or make exit loose | rear RH, scrape, shock, throttle yaw | rear scrape, exit yaw |
| reduce_rear_platform_support | Adds rear compliance/grip | Can allow scrape/choke/lazy platform | rear RH, speed, shock, scrape | rear contact/speed |
| inspect_diffuser_choke_or_scrape | Identifies if low platform is fast or hitting/choking | Not a setup change by itself | diffuser proxy, scrape, speed loss | compare same zone |
| reduce_platform_contact_small | Reduces repeated contact/scrape | May add drag or shift balance | contact proxy, RH min, speed | contact frequency, speed |

---

# 8. ARB / Sway Bar Knowledge

## 8.1 General ARB meaning

ARB changes roll stiffness and balance response. A stiffer bar at one end increases load transfer at that end and can shift balance. Front and rear effects differ by car and phase.

## 8.2 Next Gen front ARB

| Area | Options | Effect | Counter-effect |
|---|---|---|---|
| Front ARB diameter | 1.375 soft / 2.000 stiff | Bigger swing; stiff bar reduces roll and sharpens platform/response | Can add understeer and reduce compliance |
| Front ARB arm | P1 softest → P5 stiffest | Tuning swing within chosen bar | Softer frees front/compliance; stiffer sharpens but may push |
| Front ARB preload | Static/dynamic bar load detail | Can tune corner load behavior | Can mask ride-height/corner-weight problems |
| Front ARB attach | Procedure state | Used for adjustment/diagnostics | Not a normal recommendation |

## 8.3 Next Gen rear ARB

| Area | Options | Effect | Counter-effect |
|---|---|---|---|
| Rear ARB diameter | 1.375 soft / 2.000 stiff | Bigger rear roll-stiffness package | Can induce oversteer if too stiff or reduce rotation if too soft depending package |
| Rear ARB arm | P1 softest → P5 stiffest | Tuning swing | Stiffer can help rotation; softer can add rear security |
| Rear ARB preload | Static/dynamic bar load detail | Alters load on straights/corners | Can mask setup/corner-weight issues |
| Rear ARB attach | Procedure state | Not default race advice | Use with caution |

## 8.4 ARB effects

| Symptom | Candidate | Effect | Counter-effect |
|---|---|---|---|
| Tight center | Soften front ARB arm/bar | Adds front compliance/free center | May slow response or hurt platform |
| Loose center | Soften rear ARB or stiffen front depending evidence | Adds rear security / shifts balance tighter | May reduce rotation |
| Tight exit | Rear ARB/diff/cross package review | Helps drive-off rotation if bound | May loosen exit |
| Loose exit | Soften rear ARB or add rear security | Calms throttle rear | May make center tight/lazy |
| High-speed/bumpy instability | Softer ARB or compliance package | More tire contact | May reduce platform control |

---

# 9. Shocks / Dampers

## 9.1 Terms

| Term | Meaning |
|---|---|
| Bump / compression | Shock shortening. |
| Rebound | Shock extending. |
| Low-speed damping | Damper movement mostly from driver input/body motion: braking, throttle, steering. |
| High-speed damping | Damper movement mostly from bumps, curbs, dips, sharp track impacts. |
| Load variation | Cyclical tire load change; too much hurts grip. |
| Overdamped | Too much control; suspension cannot move enough. |
| Underdamped | Too little control; suspension moves uncontrolled. |
| Digressive | Builds force quickly at low shaft speed and flattens at high speed. |
| Linear | Force rises steadily with velocity. |
| Progressive | Force builds more aggressively as velocity rises. |
| Slope | Shape control in high-speed region where available. |

## 9.2 Shock histogram interpretation

Rules:

```text
Histogram bars = percent of valid time/samples in velocity bins.
Left side = rebound.
Right side = bump/compression.
Center/low-speed = near zero shaft velocity.
Outer/high-speed = bumps/curbs/impacts/large events.
Use same bins, same selected zone, same lap window, same scale for comparison.
Whole-lap histogram should not overrule selected-zone evidence.
```

Do not say:

```text
The shock histogram proves the shock is wrong.
Add rebound because the bar is tall.
This shows downforce loss.
Shock fixes this setup.
```

Say:

```text
The histogram shows unusual damper activity. Inspect matching ride-height, input, and track-zone evidence before changing shocks.
```

## 9.3 Shock effect matrix

| Swing | Effect | Counter-effect | Helps | Can hurt | Evidence |
|---|---|---|---|---|---|
| Add LS compression | Loads/supports that corner faster during driver-input compression | Can reduce compliance/grip if overdone | entry/exit transition, platform control | bumps, tire contact | low-speed bump histogram, ride-height, input trace |
| Reduce LS compression | More compliance and slower load transfer | Can let platform move too much | bumps/traction | platform stability | shock hist, RH, driver feel |
| Add LS rebound | Slows extension/holds platform attitude | Can hold tire unloaded or create oscillation | brake release, throttle transition | bumps/recovery | rebound hist, RH recovery, yaw |
| Reduce LS rebound | Faster recovery/compliance | Can feel floaty or uncontrolled | bumps/recovery | transient control | rebound hist, oscillation |
| Add HS compression | Resists sharp compression; prevents bottoming | Can be harsh and lose contact | bumps/curbs/platform strike | rough grip | high-speed bump hist, contact |
| Reduce HS compression | Absorbs impacts better | Can blow through travel/contact | bumps/curbs | bottoming | shock travel/contact |
| Add HS rebound | Controls fast extension after impact | Can pack suspension down/delay recovery | curbs/crests/banking exit | repeated bumps | high-speed rebound, RH recovery |
| Reduce HS rebound | Faster extension/recovery | Can bounce/oscillate | repeated bumps | platform control | oscillation/tire contact |
| More linear slope | Better for bumpy tracks needing stronger high-speed force | Can be harsh on smooth tracks | bumpy surfaces | smooth surfaces | high-speed hist, contact |
| More digressive slope | Better for smoother tracks to absorb small bumps without moving chassis | Can blow through travel on bumpy tracks | smooth tracks | bumpy tracks | track surface, shock hist |

## 9.4 Shock guide implementation rule

Shocks are often **fine tuning** unless the evidence points clearly to:

```text
driver-input transitions
bumps/curbs
platform instability
contact/scrape
shock overactivity
load variation
```

Do not rank shock changes high unless shock histogram and platform/phase evidence agree.

---

# 10. Brake, Differential, and Gearing

## 10.1 Brake bias

| Direction | Effect | Counter-effect | Evidence |
|---|---|---|---|
| More front bias | Calms rear under braking, stabilizes entry | Adds entry push, may underuse rear brake | brake trace, entry yaw, lock/correction |
| Less front bias / more rear | Helps rotation under brake | Can make rear unstable or lock | brake yaw, correction, decel |

## 10.2 Diff preload

| Direction | Effect | Counter-effect | Evidence |
|---|---|---|---|
| Increase preload | More locking; can stabilize throttle/decel but increase understeer | Can bind center/off-throttle and hurt rotation | throttle/brake transition, wheelspin, yaw |
| Reduce preload | Frees rotation | Can create lift/off instability or hurt drive | yaw, throttle pickup, wheelspin |

## 10.3 Final drive

| Direction | Effect | Counter-effect | Evidence |
|---|---|---|---|
| Shorter final drive | Better acceleration | May hit limiter or make throttle touchy | RPM, limiter, exit speed |
| Taller final drive | More top speed / less limiter | May bog off corner | RPM, terminal speed, exit acceleration |

---

# 11. Legacy Oval Knowledge

These are preserved for cars that support them.

## 11.1 Track bar

| Swing | Effect | Counter-effect |
|---|---|---|
| Raise/lower track bar depending side/car | Changes rear roll center/lateral behavior and rotation | Can loosen/tighten one phase while hurting another |

Use only if car capability allows it.

## 11.2 Truck arms

| Swing | Effect | Counter-effect |
|---|---|---|
| Truck arm mount changes | Rear steer/bite/weight transfer dynamics | Can create wheel hop or phase tradeoffs |

Use only if car capability allows it.

## 11.3 Bump stops / packers

| Swing | Effect | Counter-effect |
|---|---|---|
| Add earlier support | Prevents bottoming/platform collapse | Can bounce or reduce mechanical grip |
| Delay support | Adds compliance | Can allow contact |

Use only if car capability allows it.

---

# 12. Master Condition Matrix

This is RacerZLab-owned interpretation of the user-fed V4/V5 matrices and flowcharts. It should become guide mappings, not a copied UI table.

## 12.1 Loose / Tight overall

| Condition | First candidate systems | Effect | Counter-effect | Evidence |
|---|---|---|---|---|
| Loose overall | Add cross/security, rear tire support, rear toe stability, rear platform control, brake bias if entry-driven | Calms rear | Can bind center or slow rotation | yaw, tire temps, driver phase, setup diff |
| Tight overall | Free center/balance, reduce cross, front ARB/front tire work, toe/scrub, platform contact check | Helps rotation | Can reduce entry/exit security | steering, center speed, tire work, yaw |

## 12.2 Entry

| Condition | Candidate systems | Effect | Counter-effect |
|---|---|---|---|
| Loose entry | brake bias forward, rear rebound/recovery control, add cross, front platform support, rear toe stability, diff/preload where available | Calms rear getting in | May tighten center or slow turn-in |
| Tight entry | reduce front bias, free front response, front toe/caster/ARB tuning, reduce over-support, reduce bind | Helps turn-in/rotation | May destabilize braking or loosen entry |

## 12.3 Center / Middle

| Condition | Candidate systems | Effect | Counter-effect |
|---|---|---|---|
| Loose center | add rear grip/security, soften rear ARB, add stability/cross if package supports, tire/camber check, rear platform consistency | Calms middle | May tighten exit or reduce rotation |
| Tight center | reduce cross/bind, soften front ARB/arm, free center rotation, inspect RF pressure/camber, reduce toe scrub, platform bind check | Helps rotation/min speed | May loosen entry or exit |

## 12.4 Exit / Off

| Condition | Candidate systems | Effect | Counter-effect |
|---|---|---|---|
| Loose exit | add cross/stability, rear shock control, rear tire support, rear toe stability, rear platform support, diff/preload | Calms throttle rear | May bind center or reduce drive-off bite |
| Tight exit | free rear/center-off, inspect rear ARB/cross/rear platform/diff/throttle pickup/tire pressure | Helps drive-off rotation | May loosen throttle application |

## 12.5 Straight / Low top speed

| Condition | Candidate systems | Effect | Counter-effect |
|---|---|---|---|
| Low straight speed / draggy | normalize exit speed, check toe/scrub, steering/yaw, platform contact, diffuser proxy, gearing/RPM | Finds whether speed loss is drag, scrub, contact, or gearing | Wrong diagnosis can make car worse in corner | exit speed, throttle, RPM, steering, yaw, RH |

## 12.6 Long run

| Condition | Candidate systems | Effect | Counter-effect |
|---|---|---|---|
| Falls off / burns RF | pressure/camber/cross/ARB/platform/tire-protection package | Protects long-run pace | May lose fire-off speed | lap trend, tire temps/wear/pressure gain |
| Falls off / rear tires | rear tire pressure, rear shock/platform, diff, throttle pickup | Protects drive | May tighten center or reduce short-run speed | exit yaw, RR/LR temps, throttle |

---

# 13. Setup Flowchart Logic

The flowchart logic becomes ranking order:

## 13.1 Priority order

```text
1. Corner exit grip / drive-off
2. Corner entry balance
3. Driver preference / fine tuning
```

## 13.2 Rules

| Flow rule | RacerZLab behavior |
|---|---|
| Exit grip first | If poor drive/loose off/tight off exists, prioritize exit validation before entry polish. |
| Entry balance second | Once exit is usable, tune brake/entry balance. |
| Driver preference last | Caster, toe feel, steering offset, and small low-speed damper polish come later. |
| One side effect matters | If a change helps entry but hurts exit, save that tradeoff. |
| Do not chase comfort while car lacks drive | Driver feel levers should rank lower if exit grip is failing. |

---

# 14. Package Archetypes

| Archetype | Looks like | Why fast | Common risk | Stabilizers | Failure symptoms |
|---|---|---|---|---|---|
| Low-platform speed package | Low dynamic heights, controlled platform | Speed/efficiency | scrape, choke, harshness, tire abuse | springs, collars, shocks, pressure | rear scrape, snap, speed loss |
| Front-feed diffuser package | Front platform not blindly slammed; stable front feed | Maintains underbody feed | may push if front over-supported | front/rear support balance | aero balance shift, tight center |
| High-front low-rear diffuser-feed package | Front height feeds, rear outlet low/controlled | Can be fast if dynamic window works | counterintuitive static rake; scrape/choke risk | cross, rear support, front feed | rear scrape, unstable aero |
| High-cross stability package | Higher diagonal stability | Secure entry/exit | bind center, burn RF/LR | ARB, pressure, spring/damper | bound up, tight center |
| Free-center rotation package | Lower bind / more rotation | Center speed | loose entry/off | brake bias, rear support | loose in/off |
| Long-run tire-protection package | Smoother tire loading | Stint pace | lacks raw speed | pressures, camber, cross | slow fire-off |
| Qualifying speed package | Aggressive platform/tire | peak lap | falloff/heat/instability | driver precision | fast one lap, then gone |
| Pack-stability package | more yaw/platform margin | traffic confidence | slower alone/tighter | rear security, cross | pack unstable |
| Bumpy-track compliance package | more compliance/HS tuning | grip over bumps | aero motion | HS damping, springs | bottoming/skating |
| Shock-controlled platform | dampers shape transient | entry/exit polish | masks bad platform | LS/HS damping | busy histograms |
| Spring-controlled platform | springs/collars lead support | repeatable platform | harsh/grip-limited | ARB/pressure/shocks | tight/curb weakness |
| ARB-led package | ARB leads response | sharp platform/roll | tire heat/bump sensitivity | spring/shock/pressure | skate/push |
| Tire-pressure support package | pressures support/shape load | quick response/tire management | heat/drag/grip tradeoff | camber/cross/platform | pressure falloff |
| Toe-scrub speed package | toe minimized for speed | top speed | less stability/response | driver comfort, ARB | draggy or nervous |
| Legacy track-bar rotation package | rear geometry lever | center/entry tuning | phase tradeoff | spring/ARB/cross | only supported cars |

---

# 15. Evidence Requirements

## 15.1 Evidence groups

| Evidence group | Examples | Used for |
|---|---|---|
| Driver complaint | loose off, tight center, draggy | parse symptom |
| Setup snapshot | springs, collars, cross, ARB, shocks | static levers |
| Platform trace | CFS, LF/RF, rear heights, rake | dynamic platform |
| Diffuser proxy | base/wedge/volume, smooth rake | derived underbody geometry |
| Scrape/scrub | rear scrape, speed loss, yaw/scrub | contact/drag |
| Tire evidence | pressures, temps, wear, gains | tire work |
| Shock evidence | hist, RMS, velocity, delta | damper activity |
| Driver input | throttle, brake, steering | phase and trigger |
| Compare | baseline/test delta | validation |
| Track map zone | entry/center/exit/bumps | phase-local evidence |
| Memory/survey later | helped/hurt | personal learning |

## 15.2 Readiness labels

| Readiness | Meaning |
|---|---|
| ready | Required evidence is present. |
| partially_ready | Some evidence exists but key validation is missing. |
| missing_key_evidence | Do not rank high; explain what is missing. |

## 15.3 Human missing-evidence wording

```text
Need a clean center-zone window before calling this a setup swing.
Need live shock histogram before ranking shock changes high.
Need setup snapshot before comparing static garage levers.
Need Compare baseline before saying it worked.
Need front/rear ride-height traces before making platform/diffuser calls.
```

---

# 16. Review Queue Items

These must be stored as `needs_review` unless verified.

| Item | Status | Safe wording |
|---|---|---|
| CFS 0.5 inch opening/clearance feature | needs_review | User reports the CFS/front platform may include an approximately 0.5 inch opening/clearance feature that helps feed airflow toward the diffuser. Needs verification before being encoded as fact. |
| Exact numeric deltas from examples | review / driver-style example only | Numeric setup deltas can be shown only as small test swings or user-chosen examples, not universal values. |
| Legacy oval adjustments on Next Gen | blocked by capability | Track bar, truck arms, bump stops, and packers are kept for supported legacy cars but disabled for Next Gen. |
| Diffuser proxy overclaim | accepted guardrail | Derived geometry proxy, not measured downforce. |
| Shock histogram overclaim | accepted guardrail | Histogram is evidence, not a command. |

---

# 17. Implementation Targets

## 17.1 JSON records

This markdown should be converted into:

```text
guide_sources.json
guide_principles.json
guide_term_definitions.json
guide_setup_mappings.json
guide_review_queue.json
guide_digest_manifest.json
setup_areas.json
setup_effects.json
package_archetypes.json
evidence_requirements.json
nextgen_platform_rules.json
shock_interpretation.json
symptom_vocabulary.json
phase_model.json
car_capabilities.json
```

## 17.2 Validation rules

Validator should fail if:

```text
Any Next Gen effect returns track_bar, truck_arm_mount, bump_stop, or packer.
Any diffuser record claims measured downforce.
Any effect lacks counter-effect.
Any effect lacks validation target.
Any effect lacks evidence requirement.
Any effect says guaranteed.
Any effect says always except safe phrases like “not always”.
Any shock rule claims histogram alone proves a setup change.
CFS 0.5 opening is accepted without verified source.
Next Gen ARB diameter is not exactly 1.375 / 2.000.
Next Gen ARB arm is not exactly P1–P5.
```

## 17.3 Query examples

```bash
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off" --evidence setup_snapshot,platform_trace,shock_histogram

python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "tight center" --track-family intermediate_oval

python -B scripts/query_guide_knowledge.py --setup-area ls_rebound --car-family next_gen

python -B scripts/query_guide_knowledge.py --topic diffuser --car-family next_gen
```

---

# 18. Crew-Chief Response Style Seeds

## Loose entry

```text
You said loose on entry. I’m reading that as rear instability while you’re getting in.

First swings I’d consider:
1. Add a little entry stability with the best-supported lever.
2. Check brake bias and rear rebound before touching a package-level setup.
3. If the platform trace agrees, inspect front support or rear recovery.

Effect: should calm rear yaw getting in.
Counter-effect: may make the car lazier or tighter in the center.
Validate: entry yaw, steering correction, brake trace, and center speed.
```

## Tight center

```text
You said tight center. I’m reading that as the car not rotating at minimum speed.

First swings I’d consider:
1. Free the center with a small cross or ARB/pressure-supported swing.
2. Check RF tire work and steering demand.
3. Make sure this is not platform bind or toe/scrub.

Effect: should reduce steering demand and help center speed.
Counter-effect: may give up entry or exit security.
Validate: min speed, steering angle, exit throttle pickup, and RF tire trend.
```

## Loose off

```text
You said loose off. I’m reading that as rear security loss on throttle.

First swings I’d consider:
1. Add a little cross.
2. Add rear platform/security support if the trace agrees.
3. Use rear shock/tire support only if evidence points there.

Effect: should calm throttle-on rear yaw.
Counter-effect: may bind center or reduce drive-off bite if overdone.
Validate: throttle pickup, exit yaw, exit speed, and center speed.
```

## Draggy / slow straight

```text
You said it feels draggy. I won’t call that gearing until exit speed is normalized.

First checks:
1. Same exit speed?
2. Full throttle?
3. Same gear/RPM?
4. Steering/yaw scrub?
5. Platform contact or diffuser proxy warning?

Effect of reducing scrub/contact: better straight speed.
Counter-effect: may reduce response or stability.
Validate: terminal speed, RPM/limiter, steering/yaw, and ride-height contact.
```

## Platform/diffuser issue

```text
This looks like a platform-window problem, not measured downforce.

I’d inspect CFS/front feed, rear platform outlet/scrape, smooth rake, diffuser proxy, and speed loss together.

Effect: a small platform support swing may reduce contact or stabilize the diffuser window.
Counter-effect: it may tighten center, add drag, or reduce mechanical grip.
Validate: ride-height mins, scrape, speed, steering/yaw, and tire trend.
```

---

# 19. Commit Message Suggestion

```text
Add master setup matrix source for RacerZLab knowledge digestion
```
