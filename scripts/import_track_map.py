from __future__ import annotations

import argparse
from pathlib import Path

from racelab_engine.services.track_map_service import import_mt2_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a track map file into the local RacerZLab map cache.")
    parser.add_argument("path", help="Path to the source track map file")
    args = parser.parse_args()

    entry = import_mt2_file(Path(args.path))
    print(f"map_id: {entry['map_id']}")
    print(f"points_count: {entry['points_count']}")
    print(f"markers_count: {entry['markers_count']}")
    print(f"sections_count: {entry['sections_count']}")
    print(f"distance_miles: {entry['distance_ft'] / 5280.0:.3f}")
    print(f"import_status: {entry['import_status']}")


if __name__ == "__main__":
    main()
