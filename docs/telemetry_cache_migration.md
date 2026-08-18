# Telemetry cache migration and re-import policy

RacerZLab does not silently upgrade a legacy telemetry cache into a universal
archive. A cache created before the universal manifest may already have omitted
file-declared channels, and those missing samples cannot be reconstructed from
the reduced cache.

The telemetry-capabilities response exposes `cache_compatibility.status`:

- `current`: the manifest and lossless archive invariant match this release.
- `reimport_required`: re-import the original `.ibt`; the old cache is not used
  to make universal-channel or evidence-completeness claims.
- `app_upgrade_required`: the cache was written by a newer archive schema.
- `missing_cache`: the run has metadata but no readable telemetry cache.

Re-import is transactional. RacerZLab writes a staged cache, channel metadata,
and manifest, verifies that every declared channel has the expected physical
column and row/array shape, and only then replaces the prior cache. A failed
re-import leaves the previously promoted artifacts in place.

There is intentionally no lossy in-place migration. If the original `.ibt` is
unavailable, the run remains visible as historical metadata, but analyses that
need universal telemetry must report the missing evidence and stay blocked.

## Manifest schema v6

Schema v6 cannot reuse v5 calculated evidence because two upstream truth
contracts changed:

- canonical elapsed time is now qualified from `SessionTick` plus the declared
  base rate, with raw `SessionTime` retained as corroboration;
- nominal 110-inch wheelbase, 79-inch track width, and 0.5-inch rub-block
  substitutions were removed from diffuser geometry.

Re-import therefore rebuilds lap timing, integrity, calculated columns, typed
engineering blockers, and engineering-role metadata from the original source.
Legacy filename-derived run rows remain available for audit, but session
membership converges on one content-addressed recording owner. Same-source
aliases can never be compared or counted as independent evidence.
