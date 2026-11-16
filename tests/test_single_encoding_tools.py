"""Tool requests encode prose once while retaining legacy response support."""

import copy
import json

import pytest

from prompt import _format_delta_prompt, _format_messages_as_prompt, _parse_tool_block


CONTENT = '한국어 "quoted note"\n\\(x^2 + y^2\\)\nLiteral </tool_call> in a document.'
ARGUMENTS = {"path": "fixture.md", "content": CONTENT}
CALL = {"id": "fixture", "type": "function", "function": {
    "name": "write_file", "arguments": json.dumps(ARGUMENTS, ensure_ascii=False),
}}


@pytest.mark.parametrize("formatter", [_format_messages_as_prompt, _format_delta_prompt])
def test_historical_calls_show_object_arguments_without_mutating_host_history(formatter):
    messages = [{"role": "assistant", "tool_calls": [copy.deepcopy(CALL)]}]
    original = copy.deepcopy(messages)
    text = formatter(messages)
    start = text.index('<tool_call>{"id"')
    obj, _ = json.JSONDecoder().raw_decode(text[start + len("<tool_call>"):])
    assert obj["function"]["arguments"] == ARGUMENTS
    assert messages == original


def test_schema_contract_requests_single_encoding_everywhere():
    tools = [{"type": "function", "function": {"name": "write_file", "parameters": {
        "type": "object", "properties": {"content": {"type": "string"}},
    }}}]
    text = _format_messages_as_prompt([{"role": "user", "content": "Write fixture."}], tools=tools)
    assert "arguments must be a JSON object, not a JSON string" in text
    assert "arguments must be a JSON string" not in text
    assert "'arguments' must be a JSON-encoded string" not in text


@pytest.mark.parametrize("legacy", [False, True])
def test_object_and_legacy_string_arguments_preserve_quotes_math_and_newlines(legacy):
    call = copy.deepcopy(CALL)
    call["function"]["arguments"] = CALL["function"]["arguments"] if legacy else ARGUMENTS
    parsed, rest = _parse_tool_block("<tool_call>" + json.dumps(call, ensure_ascii=False) + "</tool_call>")
    assert len(parsed) == 1 and not rest
    assert json.loads(parsed[0].function.arguments) == ARGUMENTS
