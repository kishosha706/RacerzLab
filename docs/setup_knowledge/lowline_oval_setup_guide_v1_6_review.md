# Lowline Oval Setup Guide v1.6 Review

Source file audited locally:

```text
C:\Users\Soulj\Downloads\LoWLiNE-Racing-Oval-Setup-Guide-v-1.6(4).pdf
```

This review captures RacerZLab-owned setup concepts derived from the local PDF. Runtime setup logic should continue to use reviewed JSON records, not the raw PDF.

## Reviewed Concepts

- Tire pressure is a tire support and feel lever. Higher-loaded tires generally need more support, higher pressure tends to sharpen response, and lower pressure tends to feel slower or more compliant. Validate with tire temperature and wear, not pressure alone.
- Oval tire temperature review should look for inside temperature/wear being modestly hotter than outside, while avoiding exact-value claims as universal truth.
- Toe near zero can reduce straightaway scrub, while rear toe can stabilize the car through the corner. Too much toe or the wrong rear toe relationship can add scrub or make the car transition loose.
- Brake bias should usually be treated as an entry/braking support lever after chassis balance is understood, because brake bias can mask an entry chassis problem.
- ARB choice is a package lever. A stiffer bar can add outside-tire load and reduce roll; the front bar should be treated as a foundational preference/package choice when applicable.
- Caster and caster split are driver-feel and track-context levers. More split can loosen entry/center feel; smaller tracks may need less caster and faster, wider, higher-banked tracks may tolerate more split.
- Camber changes tire contact quality and trades cornering contact against straight-line drag/speed context. Tire temperature spread is required before making a strong camber call.
- Weight distribution should be read as corner/diagonal load transfer context, not as an isolated magic number. If one tire overheats first, check corner weight imbalance as context.
- Spring changes are major package moves. After changing springs, re-check ride height and camber before judging the test.
- Ride height interacts with ballast, pressures, camber, springs, and perches/collars. Rear ride height is a common oval dial-in area, but should be validated with platform, scrape, and speed evidence.
- Shock changes are fine-tuning once the setup is close. Change one shock setting at a time and validate by phase/zone.
- Bump stops, packer shims, truck arm mounts, and track bar are legacy oval concepts. Keep them behind car capability gates and never recommend them for Next Gen.

## Guardrails

- Do not expose raw PDF text in normal UI.
- Do not use exact setup values as universal truth.
- Do not recommend disabled legacy-only adjustments for Next Gen.
- Do not stack these concepts into a single recommendation. Pick one change, test, and compare.
