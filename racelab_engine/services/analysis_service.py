from __future__ import annotations

from racelab_engine.io.ibt_types import IBTImportResult
from racelab_engine.models.session import RunOverview


def overview_from_import_result(result: IBTImportResult) -> RunOverview | None:
    """Return the parsed overview from an import result.

    The real analysis is currently performed by the `.ibt` reader so this service
    is intentionally thin. It gives later MVP tickets a stable place to move lap,
    platform, segment, and recommendation orchestration.
    """

    return result.overview
