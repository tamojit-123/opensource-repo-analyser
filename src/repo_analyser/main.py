from __future__ import annotations

import uvicorn

from repo_analyser.config import get_settings
from repo_analyser.logging_utils import configure_logging, get_logger
from repo_analyser.web.app import create_app


def main() -> int:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__, "main")
    logger.info("Starting application server on %s:%s", settings.host, settings.port)
    uvicorn.run(create_app(), host=settings.host, port=settings.port)
    return 0
