"""App-wide logging setup, applied once at startup (see main.py).

Every module's `logging.getLogger(__name__)` inherits this root
configuration, so a single call here gives consistent formatting/level
across the whole backend instead of each module fending for itself.
"""

from __future__ import annotations

import logging.config
from contextvars import ContextVar

from app.config import LOG_DIR, settings

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
                # Console output doesn't survive a dev-server reload or a
                # crash - the retention/disk-space safeguard's decisions are
                # exactly the kind of thing you need to reconstruct after the
                # fact, so persist everything to disk too, rotated to bound
                # growth (10MB x 5 files ~= 50MB worst case).
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                    "filename": str(LOG_DIR / "backend.log"),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                },
            },
            "root": {
                "handlers": ["console", "file"],
                "level": settings.log_level,
            },
        }
    )
