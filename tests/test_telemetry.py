"""Tests for the structured-logging module added in review round 1.

Covers: `log_event` emits one JSON line carrying the bound request-id;
no request-id outside a request scope; `elapsed_ms` is a small non-negative
number.
"""

from __future__ import annotations

import json
import logging
import time

from digitalocean_mcp import telemetry


def test_log_event_has_no_request_id_outside_a_request_scope(caplog):
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    telemetry.log_event("unit_test_event", foo="bar")

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload == {"event": "unit_test_event", "request_id": None, "foo": "bar"}


def test_log_event_carries_the_bound_request_id(caplog):
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    token = telemetry.set_request_id("req-123")
    try:
        telemetry.log_event("unit_test_event")
    finally:
        telemetry.reset_request_id(token)

    payload = json.loads(caplog.records[0].message)
    assert payload["request_id"] == "req-123"
    # Outside the `try` block, the ContextVar must be back to its default.
    assert telemetry.get_request_id() is None


def test_log_event_respects_level(caplog):
    caplog.set_level(logging.INFO, logger="digitalocean_mcp")

    telemetry.log_event("unit_test_event", level=logging.WARNING)

    assert caplog.records[0].levelno == logging.WARNING


def test_elapsed_ms_is_small_and_non_negative():
    started = time.perf_counter()
    value = telemetry.elapsed_ms(started)
    assert 0 <= value < 1000
