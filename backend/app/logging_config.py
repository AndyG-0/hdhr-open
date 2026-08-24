"""App-wide logging setup, applied once at startup (see main.py).

Every module's `logging.getLogger(__name__)` inherits this root
configuration, so a single call here gives consistent formatting/level
across the whole backend instead of each module fending for itself.
"""

from __future__ import annotations

import logging.config
from contextvars import ContextVar

from app.config import settings

# Set by the request-id middleware (see main.py) before a request is
# dispatched. contextvars propagate correctly into the async task each
# request runs in, so every log line emitted while handling a request —
# including from plugin/integration code with no direct access to the
# request object — can be tagged with the same id, letting a whole request's
# log lines be grepped/correlated even under concurrent traffic.
request_id_ctx: ContextVar[str] = ContextVar("request_id_ctx", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {
                    "()": RequestIdFilter,
                },
            },
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                },
            },
            "root": {
                "handlers": ["console"],
                "level": settings.log_level,
            },
        }
    )
