# RacerZLab release trust gate

The roadmap trust rules are executable release criteria, not review notes.

Every pull request runs the named `Permanent synthetic trust gate`. It lints the
whole repository and executes the hostile contract, eligibility, causality,
controlled-workflow, response-memory, uncertainty, setup-control, and wording
suites listed in `scripts/audit_release_trust.py`.

Every version tag and published release runs the `Release Trust Gate` on
a protected self-hosted Windows runner with an explicitly supplied real `.ibt`.
That job fails when the fixture is missing. It imports into a clean temporary
database/cache and verifies that every file-declared channel is archived, every
advertised canonical alias exists, the manifest certifies lossless promotion,
and the normalized frame contains real samples. The repository's protected
runner variables pin the fixture SHA-256, schema fingerprint, record count, and
declared-channel count. It never silently skips. Tag/release protection must
require this named job before packaging or publishing artifacts.

Local release command:

```powershell
python scripts/audit_release_trust.py `
  --ibt 'C:\path\to\protected-fixture.ibt' `
  --expected-sha256 '<protected digest>' `
  --expected-schema-fingerprint '<protected schema>' `
  --expected-records 26556 `
  --expected-declared-channels 277
```

`--synthetic-only` is suitable for pull-request validation but is explicitly
not sufficient to authorize a release.
