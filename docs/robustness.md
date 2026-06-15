# Robustness Notes

## Import Cache Safety

Telemetry imports stage parquet/channel metadata under a temporary run id before saving run metadata. After the database save succeeds, staged cache artifacts are promoted to the final run id paths with an atomic replace. If the database save fails, staged artifacts are cleaned where possible and the previous completed run/cache is left intact.

Safe cleanup boundaries:

- Temp cache/upload artifacts from failed imports may be removed.
- Raw user `.ibt` files must not be deleted.
- Imported run records, setup snapshots, notebook findings, and test plans must not be deleted by cache cleanup.

## Upload Handling

Multipart `.ibt` uploads are streamed to a unique local import copy instead of being read into memory all at once. Successful import copies are retained as local evidence. Failed import copies are removed when safe.

## Recovery UX

Import failures return user-safe recovery details:

- what happened: the telemetry file could not be processed
- why it matters: no completed run was created
- what to do next: try again or choose a different `.ibt`

Technical details stay in logs or secondary UI details. Normal driver-facing UI should not expose raw tracebacks.

Duplicate telemetry imports update the existing run record for the same generated run id and show that replacement honestly.

## Stale Frontend State

The Test Basket revalidates persisted baseline/test evidence against the active session run list. Unavailable items are marked stale and shown to the driver instead of being silently removed. Stale basket pairs are not valid for review.

Selection state also validates the selected run against the active run list so old lap/event/sample focus does not survive a session change.

When selection is cleared by an active-session change, the UI should present it as a calm state change and ask the driver to choose a run or stint from the current session.

## Platform Event Visibility

Backend Platform events remain in the payload for evidence and debug use. Driver-facing chart markers, rails, timelines, and inspectors use shared visibility filtering so internal/debug events are hidden by default in Actionable mode and can be shown through Proxy/Internal or All modes.

## Missing Data Policy

Missing telemetry/setup fields mean unavailable. They must not be converted to zero or used to create fake exact conclusions.
