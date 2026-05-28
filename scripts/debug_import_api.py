#!/usr/bin/env python
"""
Local API import debug script.

Tests the backend import endpoints directly without the frontend.
Useful for distinguishing backend route bugs from frontend header bugs.

Usage:
    python scripts/debug_import_api.py --ibt "C:\\path\\to\\file.ibt"
    python scripts/debug_import_api.py --health
    python scripts/debug_import_api.py --sessions
    python scripts/debug_import_api.py --folder "C:\\path\\to\\telemetry"
"""

import argparse
import json
import sys
import urllib.request
import urllib.error


BASE_URL = "http://127.0.0.1:8010"


def request(method: str, path: str, body: dict | None = None, content_type: str | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if body is not None:
        headers["X-RacerZLab-Request-Id"] = "debug_script"
        data = json.dumps(body).encode("utf-8")
    else:
        data = None

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return {
                "status": resp.status,
                "body": json.loads(raw) if raw else None,
            }
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return {
            "status": e.code,
            "error": raw,
        }
    except urllib.error.URLError as e:
        return {
            "status": 0,
            "error": f"Connection failed: {e.reason}. Is the backend running at {BASE_URL}?",
        }
    except Exception as e:
        return {
            "status": 0,
            "error": str(e),
        }


def cmd_health() -> None:
    print(f"\n=== Health Check: GET {BASE_URL}/api/health ===")
    result = request("GET", "/api/health")
    print(f"  Status: {result['status']}")
    if result.get("body"):
        print(f"  Body: {json.dumps(result['body'], indent=2)}")
    if result.get("error"):
        print(f"  Error: {result['error']}")


def cmd_sessions() -> None:
    print(f"\n=== List Sessions: GET {BASE_URL}/api/sessions ===")
    result = request("GET", "/api/sessions")
    print(f"  Status: {result['status']}")
    if result.get("body"):
        sessions = result["body"]
        print(f"  Sessions: {len(sessions)}")
        for s in sessions[:5]:
            print(f"    - {s.get('name', '?')} ({s.get('session_id', '?')})")
    if result.get("error"):
        print(f"  Error: {result['error']}")


def cmd_import_ibt(ibt_path: str) -> None:
    print(f"\n=== Import .ibt: POST {BASE_URL}/api/imports/ibt ===")
    print(f"  File: {ibt_path}")
    print(f"  Content-Type: application/json")
    result = request("POST", "/api/imports/ibt", body={"path": ibt_path}, content_type="application/json")
    print(f"  Status: {result['status']}")
    if result.get("body"):
        body = result["body"]
        print(f"  run_id: {body.get('run_id', 'N/A')}")
        print(f"  status: {body.get('status', {}).get('status', 'N/A')}")
        print(f"  message: {body.get('status', {}).get('message', 'N/A')[:200]}")
        track_map = body.get("track_map")
        if track_map:
            print(f"  track_map.status: {track_map.get('status', 'N/A')}")
            print(f"  track_map.map_name: {track_map.get('map_name', 'N/A')}")
            print(f"  track_map.message: {track_map.get('message', 'N/A')}")
        cache = body.get("cache")
        if cache:
            print(f"  cache.format: {cache.get('format', 'N/A')}")
            print(f"  cache.used_fallback: {cache.get('used_fallback', 'N/A')}")
    if result.get("error"):
        print(f"  Error: {result['error']}")


def cmd_import_wrong_content_type() -> None:
    """Test that wrong Content-Type is rejected properly."""
    print(f"\n=== Test Wrong Content-Type: POST {BASE_URL}/api/imports/ibt ===")
    print(f"  Content-Type: text/plain (should be rejected)")
    result = request("POST", "/api/imports/ibt", body={"path": "test.ibt"}, content_type="text/plain")
    print(f"  Status: {result['status']}")
    if result.get("error"):
        print(f"  Error (expected): {result['error'][:200]}")
    else:
        print(f"  Body: {json.dumps(result.get('body'), indent=2)}")


def cmd_scan_folder(folder_path: str) -> None:
    print(f"\n=== Scan Telemetry Folder: POST {BASE_URL}/api/imports/scan-telemetry-folder ===")
    print(f"  Folder: {folder_path}")
    result = request("POST", "/api/imports/scan-telemetry-folder", body={"folder_path": folder_path})
    print(f"  Status: {result['status']}")
    if result.get("body"):
        body = result["body"]
        print(f"  Files found: {body.get('count', 0)}")
        for f in body.get("files", [])[:5]:
            print(f"    - {f.get('name', '?')} ({f.get('size_bytes', 0)} bytes, {f.get('modified_at', '?')})")
    if result.get("error"):
        print(f"  Error: {result['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug RacerZLab import API")
    parser.add_argument("--ibt", type=str, help="Path to .ibt file for import test")
    parser.add_argument("--folder", type=str, help="Path to telemetry folder for scan test")
    parser.add_argument("--health", action="store_true", help="Check backend health")
    parser.add_argument("--sessions", action="store_true", help="List sessions")
    parser.add_argument("--all", action="store_true", help="Run all available tests")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        print("\nNo arguments provided. Running default health check.")
        args.health = True

    if args.health or args.all:
        cmd_health()
    if args.sessions or args.all:
        cmd_sessions()
    if args.all:
        cmd_import_wrong_content_type()
    if args.ibt or args.all:
        if args.ibt:
            cmd_import_ibt(args.ibt)
        elif args.all:
            print("\n  (skipping actual .ibt import — use --ibt to specify a file)")
    if args.folder or args.all:
        if args.folder:
            cmd_scan_folder(args.folder)
        elif args.all:
            print("\n  (skipping folder scan — use --folder to specify a path)")

    print("\nDone.")


if __name__ == "__main__":
    main()
