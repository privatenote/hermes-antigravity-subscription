"""Do not lose unread evidence or loaded skills when an agy worker respawns."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompt import _format_delta_prompt, _format_messages_as_prompt


def round_messages(count, *, start=0, tool="read_file", size=1200):
    calls = [
        {"id": f"c{i}", "type": "function", "function": {
            "name": tool, "arguments": json.dumps({"path": f"/tmp/doc-{i}.txt"}),
        }}
        for i in range(start, start + count)
    ]
    bodies = [f"BEGIN_{i}\n" + "x" * size + f"\nFACT_IN_MIDDLE_{i}\n"
              + "y" * size + f"\nEND_{i}" for i in range(start, start + count)]
    messages = [{"role": "assistant", "content": None, "tool_calls": calls}]
    messages += [{"role": "tool", "tool_call_id": call["id"], "content": body}
                 for call, body in zip(calls, bodies)]
    return messages, bodies


def test_pending_parallel_round_larger_than_history_window_keeps_every_fact():
    for count in (9, 13):
        batch, bodies = round_messages(count)
        prompt = _format_messages_as_prompt([{"role": "user", "content": "Use all facts."}, *batch])
        assert all(body in prompt for body in bodies)


def test_current_task_keeps_evidence_across_multiple_rounds_and_large_results():
    first, first_bodies = round_messages(6, size=14000)
    second, second_bodies = round_messages(6, start=6)
    prompt = _format_messages_as_prompt([
        {"role": "user", "content": "Use all facts."}, *first, *second,
    ])
    assert all(body in prompt for body in first_bodies + second_bodies)


def test_empty_response_recovery_does_not_reclassify_pending_results_as_old_history():
    batch, bodies = round_messages(9)
    prompt = _format_messages_as_prompt([
        {"role": "user", "content": "Use all facts."}, *batch,
        {"role": "user", "content": "You just executed tool calls but returned an empty response. "
         "Please process the tool results above and continue with the task."},
    ])
    assert all(body in prompt for body in bodies)


def test_retained_skill_is_not_evicted_by_unrelated_tools_or_a_new_user_turn():
    skill, bodies = round_messages(1, tool="skill_view", size=14000)
    other, _ = round_messages(10, start=1)
    prompt = _format_messages_as_prompt([
        {"role": "user", "content": "Learn this skill."}, *skill, *other,
        {"role": "assistant", "content": "Done."},
        {"role": "user", "content": "Use the loaded skill for the next task."},
    ])
    assert bodies[0] in prompt


def test_delta_keeps_large_new_result_and_its_middle_fact():
    batch, bodies = round_messages(1, size=14000)
    assert bodies[0] in _format_delta_prompt(batch)


def test_core_pruned_skill_is_not_resurrected_from_external_state():
    batch, _ = round_messages(1, tool="skill_view")
    batch[-1]["content"] = "[SKILL_PRUNED: reload explicitly if needed]"
    prompt = _format_messages_as_prompt([{"role": "user", "content": "Continue."}, *batch])
    assert batch[-1]["content"] in prompt
    assert "FACT_IN_MIDDLE_0" not in prompt
