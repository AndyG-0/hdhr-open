from __future__ import annotations

import logging

from app.logging_config import RequestIdFilter, request_id_ctx


def test_request_id_filter_defaults_to_placeholder_outside_a_request():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", (), None)

    assert RequestIdFilter().filter(record) is True
    assert record.request_id == "-"


def test_request_id_filter_tags_record_with_the_current_context_value():
    token = request_id_ctx.set("abc123")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", (), None)
        RequestIdFilter().filter(record)
        assert record.request_id == "abc123"
    finally:
        request_id_ctx.reset(token)
