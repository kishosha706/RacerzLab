#!/usr/bin/env python
"""Export the FastAPI OpenAPI schema to a local JSON file.

This script is a local-only contract audit aid. It does not require
a running server or network access. It imports the FastAPI app and
generates the OpenAPI JSON directly.

Usage:
    python scripts/export_api_contract.py

Output:
    docs/contracts/openapi.generated.json
"""

import json
import sys
from pathlib import Path


def main() -> None:
    # Ensure we can import the app
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / "racelab-garage"))

    try:
        from api.main import app
    except ImportError as e:
        print(f"Error: Cannot import FastAPI app. {e}")
        print("Make sure you're running from the repo root or have the API dependencies installed.")
        sys.exit(1)

    openapi_schema = app.openapi()

    output_dir = repo_root / "racelab-garage" / "docs" / "contracts"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "openapi.generated.json"

    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2, default=str)

    print(f"OpenAPI schema exported to {output_path}")
    print(f"  Paths: {len(openapi_schema.get('paths', {}))}")
    print(f"  Schemas: {len(openapi_schema.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    main()
