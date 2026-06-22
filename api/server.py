from __future__ import annotations

import logging
import multiprocessing
import os
from pathlib import Path

import uvicorn

from api.main import app


HOST = "127.0.0.1"
PORT = 8010


def _configure_file_logging() -> None:
    log_path = os.environ.get("RACERZLAB_BACKEND_LOG")
    if not log_path:
        return
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    multiprocessing.freeze_support()
    _configure_file_logging()
    try:
        logging.info("Starting RacerZLab backend on %s:%s", HOST, PORT)
        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            reload=False,
            access_log=False,
            log_config=None,
        )
    except Exception:
        logging.exception("RacerZLab backend failed to start")
        raise


if __name__ == "__main__":
    main()
