"""Process-wide logging setup (O-16) and per-request log correlation (SEC-17/18)."""

import logging
from contextvars import ContextVar

# "-" outside a request (Celery tasks, startup) so the format string never fails.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"

_factory_installed = False
_HANDLER_MARK = "_dosely_handler"


def _install_request_id_record_factory() -> None:
    """Stamp every LogRecord (any logger, any handler) with the current request id."""
    global _factory_installed
    if _factory_installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.request_id = request_id_var.get()
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_logging(level: str = "INFO") -> None:
    """Apply ``level`` to the root logger with one stream handler. Safe to call repeatedly.

    Only the handler installed here is replaced, so handlers added by others
    (pytest's caplog, uvicorn's own loggers) are left alone.
    """
    _install_request_id_record_factory()
    root = logging.getLogger()
    for handler in root.handlers[:]:
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level)
