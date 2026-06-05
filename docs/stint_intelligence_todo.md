# Stint Intelligence TODO

## Next Milestone

- True pit-to-pit stint detection from imported lap/session data.
- Add an explicit `ephemeral` or `temporary` RaceLab session flag before enabling automatic session cleanup.

Future definition:

- Stint starts when the car leaves pit road.
- Stint ends when the car pits, resets, or starts a new pit-road cycle.
- Full-run and best-window summaries remain useful, but pit-to-pit rows should become the primary long-run stint rows once the imported data can support it reliably.

Constraints:

- No live iRSDK bridge is required for the imported-data milestone.
- Do not infer pit-to-pit boundaries from missing data.
- Keep invalid/caution laps flagged rather than converting them to zero-time or fake values.
- Session cleanup may remove only clearly marked temporary session containers. It must never delete imported runs, raw `.ibt` files, cached telemetry, setup snapshots, notebooks, reports, or source guide data.
