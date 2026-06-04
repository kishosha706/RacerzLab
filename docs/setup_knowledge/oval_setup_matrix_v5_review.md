# Oval Setup Matrix V5 Review

Source audited from the user-provided Oval Setup Matrix V5 image in conversation.

This review captures RacerZLab-owned setup concepts derived from the matrix. Runtime setup logic should use reviewed JSON records, not a copied screenshot table.

## Reviewed Concepts

- The matrix organizes driver complaints into loose/tight, entry, middle/center, and exit phases.
- Tire pressure rows map to tire-pressure support and tire-temperature validation. Pressure swings should stay small and be validated against tire trend and run length.
- Spring, spring perch/wedge, shock collar, ride height, and corner weight rows are coupled package levers. Changing one can move ride height, platform, and corner load context.
- Bump/rebound rows map to shock compression/rebound setup effects. Shock changes should be one-setting-at-a-time fine tuning unless shock/platform evidence agrees.
- Camber and caster rows map to alignment/contact/driver-feel effects. They need tire temperature, steering, and phase evidence before ranking high.
- Front sway bar size is a bigger package swing. Front sway bar arm is a smaller tuning swing.
- Next Gen ARB diameter has only two choices: 1.375 soft and 2.000 stiff. Diameter changes are bigger package swings.
- Next Gen ARB arm position is P1 through P5. P1 is softest/lowest/looser, P5 is stiffest/tighter, and one P-position is the smaller tuning swing inside the chosen diameter.
- Ballast, front stagger, front toe in/out, and steering ratio rows are matrix context for setup digestion; recommend only when the selected car exposes the adjustment and evidence supports it.
- Legacy rows such as truck arm mount and track bar stay behind car capability gates and must not be recommended for Next Gen.

## Guardrails

- Do not copy the screenshot table into normal UI.
- Do not treat one matrix cell as a guaranteed fix.
- Do not stack several matrix cells as one recommendation.
- Do not weaken Next Gen disabled-area gates.
- Do not invent exact values beyond the confirmed Next Gen ARB discrete options.
