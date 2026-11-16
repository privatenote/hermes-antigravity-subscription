"""Worker reuse must match the history and tool contract actually delivered."""
import io
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import client as client_module
from client import AntigravityClient
from prompt import _messages_match_prefix


def test_snapshot_does_not_follow_in_place_host_edits():
    client = AntigravityClient.__new__(AntigravityClient)
    client._lock = threading.RLock()
    client._arm_idle_timer_locked = lambda: None
    history = [{"role": "user", "content": [{"type": "text", "text": "OLD"}]}]
    client._update_worker_history(history)
    history[0]["content"][0]["text"] = "EDITED BY HOST"
    assert not _messages_match_prefix(client._conversation_history, history + [{"role": "tool"}])
    assert client._conversation_history[0]["content"][0]["text"] == "OLD"


@pytest.mark.parametrize("field", ["tool_call_id", "name"])
def test_result_identity_is_part_of_the_reuse_check(field):
    old = {"role": "tool", "content": "SAME", "tool_call_id": "a", "name": "read_file"}
    edited = {**old, field: "different"}
    assert not _messages_match_prefix([old], [edited, {"role": "user", "content": "Next"}])


@pytest.mark.parametrize("change", ["schema", "choice", "lost_conversation"])
def test_changed_tool_contract_starts_a_full_fresh_worker(tmp_path, monkeypatch, change):
    home = tmp_path / "home"
    gemini = home / ".gemini" / "antigravity-cli"
    gemini.mkdir(parents=True)
    monkeypatch.setattr(client_module, "setup_isolated_home", lambda _: (home, gemini))
    monkeypatch.setattr(client_module, "is_authenticated", lambda: True)
    monkeypatch.setattr(client_module, "reap_orphaned_plugin_workers", lambda: 0)
    monkeypatch.setattr(client_module, "sync_isolated_token", lambda _: False)
    monkeypatch.setattr(client_module, "start_stderr_drainer", lambda _: None)
    monkeypatch.setattr(client_module, "_worker_idle_seconds", lambda: 0)
    spawns, procs = [], []

    def spawn(argv, **kwargs):
        ident = "" if change == "lost_conversation" else f"conv-{len(spawns)}"
        proc = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(
            json.dumps({"event": "result", "conversation_id": ident,
                        "result": {"status": "SUCCESS", "response": "OK"}}) + "\n"),
            stderr=io.StringIO(), poll=lambda: None, terminate=MagicMock(), wait=MagicMock())
        # SimpleNamespace is unhashable; the process registry uses identity.
        class Proc:
            pass
        obj = Proc()
        obj.__dict__.update(vars(proc))
        spawns.append(argv)
        procs.append(obj)
        return obj

    monkeypatch.setattr(client_module.subprocess, "Popen", spawn)
    client = AntigravityClient(command="fake-agy", cwd=str(tmp_path))
    client._resolve_model_and_effort = lambda *_: ("test-model", None)
    tool = {"type": "function", "function": {"name": "inspect", "description": "v1", "parameters": {"type": "object", "properties": {}}}}
    messages = [{"role": "user", "content": "First"}]
    try:
        client.chat.completions.create(messages=messages, tools=[tool])
        if change == "lost_conversation":
            procs[0].poll = lambda: 0
        next_tool = json.loads(json.dumps(tool))
        if change == "schema":
            next_tool["function"]["description"] = "CURRENT_SCHEMA_V2"
        client.chat.completions.create(messages=messages + [{"role": "user", "content": "Next"}],
                                       tools=[next_tool], tool_choice="none" if change == "choice" else None)
        assert len(spawns) == 2
        assert "--conversation" not in spawns[1]
        payload = json.loads(procs[1].stdin.getvalue())["message"]["content"]
        assert "Conversation transcript:" in payload
        if change == "schema":
            assert "CURRENT_SCHEMA_V2" in payload
    finally:
        client.close()


def test_parallel_media_request_cannot_terminate_another_turns_worker(tmp_path, monkeypatch):
    client = AntigravityClient.__new__(AntigravityClient)
    client.is_closed = False
    client._lock = threading.RLock()
    client._worker_lock = threading.Lock()
    client._worker_lock.acquire()  # owned by a different in-flight turn
    client._worker_proc = SimpleNamespace(poll=lambda: None)
    client._worker_media_rules = frozenset()
    client._materialized_media = set()
    client._isolated_gemini_dir = tmp_path
    client._terminate_worker_locked = MagicMock()
    client._resolve_model_and_effort = lambda *_: ("test", None)
    client._run_oneshot_completion = MagicMock(return_value="ONESHOT")
    monkeypatch.setattr(client_module, "is_authenticated", lambda: True)
    monkeypatch.setattr(client_module, "media_reference_paths", lambda *_: {"/tmp/new-image.png"})
    try:
        assert client._create_chat_completion(messages=[{"role": "user", "content": "Image"}]) == "ONESHOT"
        client._terminate_worker_locked.assert_not_called()
        assert client._worker_media_rules == frozenset()
        assert client._worker_lock.locked()
        assert "/tmp/new-image.png" in (tmp_path / "settings.json").read_text()
    finally:
        client._worker_lock.release()


def test_existing_media_rules_do_not_respawn_the_worker(tmp_path):
    from process import write_media_read_permissions
    client = AntigravityClient.__new__(AntigravityClient)
    client._lock = threading.RLock()
    client._isolated_gemini_dir = tmp_path
    client._worker_proc = SimpleNamespace(poll=lambda: None)
    paths = {"/tmp/existing.png"}
    client._worker_media_rules = write_media_read_permissions(tmp_path, paths)
    client._terminate_worker_locked = MagicMock()
    client._ensure_worker_media_permissions(paths)
    client._terminate_worker_locked.assert_not_called()
