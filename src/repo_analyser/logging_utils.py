from __future__ import annotations

import contextvars
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from repo_analyser.config import Settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        record.component = getattr(record, "component", record.name)
        record.agent = getattr(record, "agent", "-")
        return True


def configure_logging(settings: Settings) -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_repo_analyser_configured", False):
        return

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(component)s | request=%(request_id)s | agent=%(agent)s | %(message)s"
    )
    context_filter = RequestContextFilter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)

    handlers: list[logging.Handler] = [console_handler]

    if settings.log_to_file:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.log_dir / "app.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        handlers.append(file_handler)

    root_logger.setLevel(log_level)
    for handler in handlers:
        root_logger.addHandler(handler)
    root_logger._repo_analyser_configured = True  # type: ignore[attr-defined]


def get_logger(name: str, component: str) -> logging.LoggerAdapter[logging.Logger]:
    logger = logging.getLogger(name)
    return logging.LoggerAdapter(logger, {"component": component})


def set_request_id(request_id: str) -> contextvars.Token[str]:
    return request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token[str]) -> None:
    request_id_var.reset(token)
