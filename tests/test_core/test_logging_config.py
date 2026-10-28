"""SEC-17 / O-16: log level applied, request id on records, no print(), no PHI."""

import ast
import logging
from pathlib import Path

import pytest

from src.core.logging_config import configure_logging, request_id_var

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    factory = logging.getLogRecordFactory()
    yield
    root.setLevel(level)
    root.handlers[:] = handlers
    logging.setLogRecordFactory(factory)


def test_configure_logging_applies_level(restore_logging):
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_is_idempotent(restore_logging):
    configure_logging("INFO")
    n = len(logging.getLogger().handlers)
    configure_logging("INFO")
    assert len(logging.getLogger().handlers) == n


def test_records_carry_request_id(restore_logging, caplog):
    configure_logging("INFO")
    token = request_id_var.set("req-123")
    try:
        with caplog.at_level(logging.INFO):
            logging.getLogger("dosely.test").info("hello")
    finally:
        request_id_var.reset(token)
    assert caplog.records[-1].request_id == "req-123"


def test_records_default_request_id_when_unset(restore_logging, caplog):
    configure_logging("INFO")
    with caplog.at_level(logging.INFO):
        logging.getLogger("dosely.test").info("hello")
    assert caplog.records[-1].request_id == "-"


def test_no_print_calls_in_src():
    offenders = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not offenders, offenders


def test_celery_uses_settings_log_level():
    from celery.signals import setup_logging

    import src.core.celery_app  # noqa: F401

    assert setup_logging.receivers, "celery_app must connect a setup_logging handler"


def test_describe_integrity_error_omits_statement_parameters():
    from sqlalchemy.exc import IntegrityError

    from src.common.exceptions import describe_integrity_error

    class FakeOrigError(Exception):
        constraint_name = "uq_users_phone"

    exc = IntegrityError("INSERT INTO users VALUES (%s)", {"phone": "+84912345678"}, FakeOrigError("dup"))
    text = describe_integrity_error(exc)
    assert "uq_users_phone" in text
    assert "84912345678" not in text
