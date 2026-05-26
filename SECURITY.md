# Security

RaceLab Garage is local desktop software for iRacing telemetry and setup analysis.

- It does not upload telemetry, setup files, reports, or user data.
- It does not use external APIs, analytics, remote crash reporting, login, cloud sync, or telemetry upload by default.
- Production desktop UI loads bundled local files from `ui/dist`, not a remote website.
- During development only, Tauri may use the local Vite server at `http://127.0.0.1:5173`.
- The RaceLab Engine backend binds to `127.0.0.1` only.
- Imported `.ibt`, `.sto`, `.mt2`, generated reports, cache files, and SQLite data stay on the user's machine.
- Notebook findings, notes, tags, and test plans are stored in local SQLite only. No cloud sync exists.
- `.mt2` decoding is partial/centerline only — no GPS, boundaries, banking, or track width data.
- `.sto` decoding is not implemented yet, and no claim is made that it is decoded.

If you discover a local data exposure issue, preserve the local files involved and document the exact steps to reproduce it.
