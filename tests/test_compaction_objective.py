"""Compaction handoffs are background; their post-boundary request stays active."""

from prompt import (
    _format_delta_prompt,
    _format_messages_as_prompt,
    _latest_user_text,
)

PREFIX = "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted."
END = "--- END OF CONTEXT SUMMARY — respond to the message below, not the summary above ---"
REPLAY = (
    "[STILL IN PROGRESS — this is the active request, restated after the "
    "compaction boundary because it was not finished yet. Continue it; do not "
    "start over.]"
)
REQUEST = "Write the fair rubric, then obtain an independent audit."
HISTORY = "OLD_HANDOFF_BODY: [SKILL_PRUNED: reload the earlier skill]"


def handoff(request=REQUEST):
    return {"role": "user", "content": f"{PREFIX}\n{HISTORY}\n{END}\n{REPLAY}\n{request}"}


def test_merged_inflight_request_survives_wire_metadata_stripping():
    assert _latest_user_text([handoff()]) == REQUEST


def test_standalone_reference_summary_is_never_the_active_request():
    summary = {"role": "user", "content": f"{PREFIX}\n{HISTORY}\n{END}"}
    assert _latest_user_text([summary]) == ""
    assert _latest_user_text([{"role": "user", "content": REQUEST}, summary]) == REQUEST


def test_last_boundary_wins_over_an_old_replay_quoted_in_the_summary():
    old = handoff("OLD_TASK")["content"]
    summary = {"role": "user", "content": f"{PREFIX}\n{old}\n{END}\n{REPLAY}\n{REQUEST}"}
    assert _latest_user_text([summary]) == REQUEST
    summary["content"] = f"{PREFIX}\n{old}\n{END}"
    assert _latest_user_text([summary]) == ""


def test_legacy_merged_layout_extracts_only_text_after_the_end_boundary():
    summary = {"role": "user", "content": (
        "[PRIOR CONTEXT — for reference only; not a new message]\nold context\n"
        "[END OF PRIOR CONTEXT — COMPACTION SUMMARY BELOW]\n"
        f"{PREFIX}\n{HISTORY}\n{END}\n{REQUEST}"
    )}
    assert _latest_user_text([summary]) == REQUEST


def test_plain_restated_request_and_multimodal_text_keep_the_live_task():
    assert _latest_user_text([{"role": "user", "content": f"{REPLAY}\n{REQUEST}"}]) == REQUEST
    msg = handoff()
    msg["content"] = [{"type": "text", "text": msg["content"]}]
    assert _latest_user_text([msg]) == REQUEST


def test_new_user_steering_wins_and_quoted_marker_text_is_not_reclassified():
    text = "Explain this marker: " + handoff()["content"]
    assert _latest_user_text([handoff(), {"role": "user", "content": text}]) == text


def test_full_tool_request_does_not_copy_handoff_into_objective_sections():
    messages = [handoff(), {"role": "tool", "tool_call_id": "c1", "content": "CURRENT_EVIDENCE"}]
    result = _format_messages_as_prompt(messages)
    head, transcript = result.split("Conversation transcript:", 1)
    tail = result.split("### USER REQUEST THIS TOOL LOOP IS SERVING:", 1)[1]
    assert REQUEST in head and REQUEST in tail
    assert HISTORY not in head and HISTORY not in tail
    assert result.count(HISTORY) == 1
    assert "Compaction handoff (reference only):" in transcript


def test_full_handoff_at_tail_is_continuation_not_a_new_request():
    result = _format_messages_as_prompt([handoff()])
    assert result.count(HISTORY) == 1
    assert "The user has submitted a new request" not in result
    assert REQUEST in result.split("### LATEST USER REQUEST TO ANSWER:", 1)[1]


def test_delta_handoff_keeps_background_once_and_names_the_current_request():
    result = _format_delta_prompt([handoff()], pending_user_text="OLDER_REQUEST")
    assert result.count(HISTORY) == 1
    tail = result.split("### LATEST USER REQUEST TO ANSWER:", 1)[1]
    assert REQUEST in tail and HISTORY not in tail and "OLDER_REQUEST" not in tail


def test_tool_delta_uses_extracted_request_without_summary_reload_markers():
    messages = [handoff(), {"role": "tool", "tool_call_id": "c1", "content": "CURRENT_EVIDENCE"}]
    result = _format_delta_prompt(messages[-1:], pending_user_text=_latest_user_text(messages))
    assert REQUEST in result and HISTORY not in result and "CURRENT_EVIDENCE" in result


def test_old_media_reference_does_not_remove_the_active_requests_attachment():
    image = "[Image attached at: /tmp/compaction-probe.png]"
    msg = handoff(f"{REQUEST}\n{image}")
    msg["content"] = msg["content"].replace(HISTORY, f"{HISTORY}\n{image}")
    text = _latest_user_text([msg])
    assert REQUEST in text and "[Image](/tmp/compaction-probe.png)" in text
    assert HISTORY not in text


def test_structured_image_after_the_replay_boundary_is_preserved():
    msg = handoff()
    msg["content"] = [
        {"type": "text", "text": msg["content"]},
        {"type": "image_url", "image_url": {"url": "/tmp/compaction-probe.png"}},
    ]
    text = _latest_user_text([msg])
    assert REQUEST in text and "[Image](/tmp/compaction-probe.png)" in text
    assert HISTORY not in text
