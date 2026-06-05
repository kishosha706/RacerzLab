# Stint Intelligence TODO

## Next Milestone

- True pit-to-pit stint detection from imported lap/session data.

Future definition:

- Stint starts when the car leaves pit road.
- Stint ends when the car pits, resets, or starts a new pit-road cycle.
- Full-run and best-window summaries remain useful, but pit-to-pit rows should become the primary long-run stint rows once the imported data can support it reliably.

Constraints:

- No live iRSDK bridge is required for the imported-data milestone.
- Do not infer pit-to-pit boundaries from missing data.
- Keep invalid/caution laps flagged rather than converting them to zero-time or fake values.
