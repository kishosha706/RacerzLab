"""Permanent release trust gate for RacerZLab.

Every release must pass the synthetic adversarial suite and a lossless import of
an explicitly supplied real .ibt file.  The real-file requirement never skips.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.services.import_service import ImportService, read_telemetry_manifest


TRUST_TESTS = (
    "tests/test_evidence_contracts.py",
    "tests/test_universal_telemetry.py",
    "tests/test_insight_causality.py",
    "tests/test_setup_learning_service.py",
    "tests/test_test_director.py",
    "tests/test_crew_chief_packet.py",
    "tests/test_engineering_api.py",
    "tests/test_controlled_workflow_service.py",
    "tests/test_active_reset_lab.py",
    "tests/test_controlled_workflow_report.py",
    "tests/test_damper_psd_contract.py",
    "tests/test_professional_surface_frontend_contract.py",
    "tests/test_advanced_experimentation.py",
    "tests/test_setup_controls.py",
    "tests/test_dial_in_service.py",
)

TRUST_DESELECTS = (
    "tests/test_universal_telemetry.py::test_real_atlanta_archive_health_has_no_false_faults",
)


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False)  # noqa: S603
    if completed.returncode:
        raise SystemExit(completed.returncode)


def audit_real_ibt(
    path: Path,
    *,
    expected_sha256: str,
    expected_schema_fingerprint: str,
    expected_records: int,
    expected_declared_channels: int,
) -> None:
    if not path.is_file() or path.suffix.lower() != ".ibt":
        raise SystemExit(f"Release fixture is missing or is not an .ibt file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().casefold() != expected_sha256.casefold():
        raise SystemExit("Protected release fixture SHA-256 does not match the configured immutable fixture.")
    with tempfile.TemporaryDirectory(prefix="racerzlab-release-audit-") as temp:
        root = Path(temp)
        result, _cache = ImportService(
            db_path=root / "racelab.sqlite",
            data_dir=root / "data",
        ).import_ibt_file(path)
        if result.overview is None:
            raise SystemExit("Real .ibt import did not produce a run overview.")
        frame = result.get_normalized_frame()
        if frame is None or frame.height <= 0:
            raise SystemExit("Real .ibt import produced no normalized telemetry frame.")
        manifest = read_telemetry_manifest(result.overview.run_id, root / "data")
        declared = int(manifest.get("declared_channel_count") or 0)
        cached = int(manifest.get("cached_channel_count") or 0)
        complete = int(manifest.get("complete_channel_count") or 0)
        if not declared or declared != cached or declared != complete:
            raise SystemExit(
                f"Lossless archive invariant failed: declared={declared}, cached={cached}, complete={complete}."
            )
        if manifest.get("lossless_archive_complete") is not True:
            raise SystemExit("Manifest did not certify a complete lossless archive.")
        if frame.height != expected_records:
            raise SystemExit(f"Fixture record count changed: expected {expected_records}, observed {frame.height}.")
        if declared != expected_declared_channels:
            raise SystemExit(
                f"Fixture declaration count changed: expected {expected_declared_channels}, observed {declared}."
            )
        if manifest.get("schema_fingerprint") != expected_schema_fingerprint:
            raise SystemExit("Fixture schema fingerprint does not match the protected release identity.")
        if any(column.startswith("raw__") for column in frame.columns):
            raise SystemExit("Redundant raw namespace columns were materialized.")
        advertised_aliases = {
            channel.get("canonical_name")
            for channel in manifest.get("channels", ())
            if channel.get("canonical_name")
        }
        missing_aliases = advertised_aliases - set(frame.columns)
        if missing_aliases:
            raise SystemExit(f"Advertised aliases are missing from the archive: {sorted(missing_aliases)}")
        print(
            "Real .ibt trust audit passed: "
            f"{frame.height} records, {declared}/{declared} declared channels archived, "
            f"schema {manifest.get('schema_fingerprint') or 'unavailable'}."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ibt", type=Path, help="Required real .ibt fixture for a release audit.")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-schema-fingerprint")
    parser.add_argument("--expected-records", type=int)
    parser.add_argument("--expected-declared-channels", type=int)
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Run PR-safe synthetic checks; this mode is not sufficient for a release.",
    )
    parser.add_argument("--skip-tests", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.synthetic_only and args.ibt:
        parser.error("choose --synthetic-only or --ibt, not both")
    if not args.synthetic_only and args.ibt is None:
        parser.error("release audit requires --ibt; use --synthetic-only only for pull-request checks")
    if not args.synthetic_only and any(value is None for value in (
        args.expected_sha256,
        args.expected_schema_fingerprint,
        args.expected_records,
        args.expected_declared_channels,
    )):
        parser.error("release audit requires the protected fixture digest, schema, record count, and declaration count")
    if not args.skip_tests:
        _run([sys.executable, "-m", "ruff", "check", "."])
        _run([
            sys.executable, "-B", "-m", "pytest", "-q", "-m", "not slow",
            *(f"--deselect={node_id}" for node_id in TRUST_DESELECTS),
            *TRUST_TESTS,
        ])
    if args.ibt is not None:
        audit_real_ibt(
            args.ibt.resolve(),
            expected_sha256=args.expected_sha256,
            expected_schema_fingerprint=args.expected_schema_fingerprint,
            expected_records=args.expected_records,
            expected_declared_channels=args.expected_declared_channels,
        )
    else:
        print("Synthetic trust audit passed. A real .ibt audit is still required before release.")


if __name__ == "__main__":
    main()
