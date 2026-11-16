"""Synthetic failures retain private evidence without publishing tool payloads."""

import logging
import os
import stat

import pytest

from debug import capture_tool_protocol_failure
from test_stream_tool_protocol import _events, _stream


@pytest.mark.parametrize(("frame", "failure"), [
    ('<tool_call>{"function":</tool_call>', "invalid_json"),
    ('<tool_call>[]</tool_call>', "non_object_call"),
    ('<tool_call>{"function":"write_file"}</tool_call>', "missing_function_object"),
    ('<tool_call>{"function":{"name":" "}}</tool_call>', "missing_function_name"),
    ('<tool_call>{"function":', "incomplete_frame"),
])
def test_failure_metadata_is_useful_without_raw_dump(monkeypatch, caplog, frame, failure):
    monkeypatch.delenv("ANTIGRAVITY_DEBUG_PROMPT_DIR", raising=False)
    with caplog.at_level(logging.WARNING):
        capture_tool_protocol_failure(frame, "invalid", "fixture-only")
    assert failure in caplog.text
    assert frame not in caplog.text
    assert "private_dump=None" in caplog.text
    if failure == "invalid_json":
        assert '"position":' in caplog.text


def test_private_dump_keeps_exact_failed_frame_but_normal_log_does_not(monkeypatch, tmp_path, caplog):
    target = tmp_path / "private"
    monkeypatch.setenv("ANTIGRAVITY_DEBUG_PROMPT_DIR", str(target))
    secret = "fixture-private-content-47"
    frame = '<tool_call>{"private":"' + secret + '","function":}</tool_call>'
    with caplog.at_level(logging.WARNING):
        capture_tool_protocol_failure(frame, "invalid", "fixture-only")
    files = list(target.glob("*_protocol-invalid.txt"))
    assert len(files) == 1
    assert files[0].read_text().endswith(frame)
    assert secret not in caplog.text
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o700
        assert stat.S_IMODE(files[0].stat().st_mode) == 0o600


def test_stream_keeps_rejecting_invalid_calls_after_capturing_them(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIGRAVITY_DEBUG_PROMPT_DIR", str(tmp_path))
    frame = '<tool_call>{"function":"write_file","arguments":{"content":"fixture"}}</tool_call>'
    stream, _proc, _client = _stream(_events(frame))
    with pytest.raises(RuntimeError, match="invalid tool call block"):
        list(stream)
    assert any(p.read_text().endswith(frame) for p in tmp_path.glob("*_protocol-invalid.txt"))


def test_unwritable_diagnostics_do_not_mask_original_protocol_error(monkeypatch, tmp_path):
    blocked = tmp_path / "regular-file"
    blocked.write_text("fixture")
    monkeypatch.setenv("ANTIGRAVITY_DEBUG_PROMPT_DIR", str(blocked))
    frame = '<tool_call>{"function":</tool_call>'
    stream, _proc, _client = _stream(_events(frame))
    with pytest.raises(RuntimeError, match="invalid tool call block"):
        list(stream)


def test_stream_captures_incomplete_frame_without_emitting_a_call(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIGRAVITY_DEBUG_PROMPT_DIR", str(tmp_path))
    frame = '<tool_call>{"function":{"name":"write_file"'
    stream, _proc, _client = _stream(_events(frame))
    with pytest.raises(RuntimeError, match="incomplete tool call block"):
        list(stream)
    files = list(tmp_path.glob("*_protocol-incomplete.txt"))
    assert len(files) == 1
    assert files[0].read_text().endswith(frame)
