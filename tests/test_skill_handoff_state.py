"""A proven reload supersedes stale pruning instructions, without hiding loss."""
import json

from prompt import _format_delta_prompt, _format_messages_as_prompt, _skill_state_section


def view(ident, body, *, name="rubric", file_path=None):
    args = {"name": name}
    if file_path:
        args["file_path"] = file_path
    return [
        {"role": "assistant", "tool_calls": [{"id": ident, "function": {
            "name": "skill_view", "arguments": json.dumps(args)}}]},
        {"role": "tool", "tool_call_id": ident,
         "content": body if isinstance(body, str) else json.dumps(body)},
    ]


FULL = {"success": True, "content": "Use the complete fair rubric instructions."}
PRUNED = "[SKILL_PRUNED: content lost in compression; reload with skill_view(name='rubric')]"


def test_reload_supersedes_old_marker_and_names_the_proving_result():
    messages = view("old", PRUNED) + view("fresh", FULL)
    state = _skill_state_section(messages)
    assert '"name": "rubric"' in state and '"tool_call_id": "fresh"' in state
    prompt = _format_messages_as_prompt([{"role": "user", "content": "Write it."}, *messages])
    assert state in prompt and PRUNED in prompt and FULL["content"] in prompt
    assert prompt.index(state) < prompt.index("Conversation transcript:")


def test_later_pruning_revokes_proven_availability():
    assert _skill_state_section(view("loaded", FULL) + view("lost", PRUNED)) == ""


def test_unchanged_stub_is_never_mistaken_for_a_full_body():
    stub = {"success": True, "unchanged": True, "message": "Already loaded."}
    assert _skill_state_section(view("stub", stub)) == ""
    assert '"tool_call_id": "loaded"' in _skill_state_section(view("loaded", FULL) + view("stub", stub))


def test_failure_does_not_claim_the_skill_was_loaded():
    assert _skill_state_section(view("failed", {"success": False, "error": "Missing skill"})) == ""


def test_linked_file_state_does_not_cover_the_main_skill():
    messages = view("main", PRUNED) + view("ref", FULL, file_path="references/check.md")
    state = _skill_state_section(messages)
    assert '"file_path": "references/check.md"' in state
    assert '"file_path": null' not in state


def test_delta_carries_only_state_proven_by_the_current_canonical_history():
    messages = view("loaded", FULL)
    delta = _format_delta_prompt([{"role": "tool", "content": "CALCULATED"}],
                                pending_user_text="Finish.", skill_state=_skill_state_section(messages))
    assert '"tool_call_id": "loaded"' in delta and "CALCULATED" in delta
    assert FULL["content"] not in delta  # body already delivered, not a second copy


def test_host_notice_after_json_does_not_hide_a_complete_loaded_body():
    body = json.dumps(FULL) + "\n\n[Hermes note: this read has been recorded for the current task.]"
    messages = view("loaded", body)
    assert '"tool_call_id": "loaded"' in _skill_state_section(messages)
    assert body in _format_messages_as_prompt([{"role": "user", "content": "Continue"}, *messages])
