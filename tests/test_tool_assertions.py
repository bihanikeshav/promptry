"""Tests for tool-use assertions (assert_tool_called, assert_tool_sequence,
assert_no_tool_called).
"""
import pytest

from promptry.evaluator import run_context
from promptry.assertions import (
    assert_tool_called,
    assert_tool_sequence,
    assert_no_tool_called,
    _normalize_tool_call,
)


# ---- sample traces ---------------------------------------------------------

NATIVE_TRACE = [
    {"name": "search", "args": ["python tutorials"], "kwargs": {"limit": 10}},
    {"name": "summarize", "args": ["some text"], "kwargs": {}},
    {"name": "rank", "args": [], "kwargs": {"top_k": 3}},
]


# ---------------------------------------------------------------------------
# assert_tool_called
# ---------------------------------------------------------------------------

class TestAssertToolCalled:

    def test_happy_path_by_name(self):
        with run_context() as results:
            score = assert_tool_called(NATIVE_TRACE, "search")
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].assertion_type == "tool_called"

    def test_failure_tool_not_called(self):
        with run_context():
            with pytest.raises(AssertionError, match="was never called"):
                assert_tool_called(NATIVE_TRACE, "delete_all")

    def test_empty_trace_fails(self):
        with run_context() as results:
            with pytest.raises(AssertionError):
                assert_tool_called([], "search")
        assert results[0].passed is False

    def test_kwargs_partial_match(self):
        # expected kwargs are a subset of the actual call's kwargs
        with run_context():
            assert_tool_called(NATIVE_TRACE, "search", kwargs={"limit": 10})

    def test_kwargs_mismatch_fails(self):
        with run_context():
            with pytest.raises(AssertionError, match="none matched"):
                assert_tool_called(NATIVE_TRACE, "search", kwargs={"limit": 99})

    def test_args_prefix_match(self):
        with run_context():
            assert_tool_called(NATIVE_TRACE, "search", args=["python tutorials"])

    def test_args_mismatch_fails(self):
        with run_context():
            with pytest.raises(AssertionError):
                assert_tool_called(NATIVE_TRACE, "search", args=["something else"])


# ---------------------------------------------------------------------------
# assert_tool_sequence
# ---------------------------------------------------------------------------

class TestAssertToolSequence:

    def test_happy_path_in_order(self):
        with run_context() as results:
            score = assert_tool_sequence(NATIVE_TRACE, ["search", "summarize"])
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].assertion_type == "tool_sequence"

    def test_wrong_order_fails(self):
        with run_context():
            with pytest.raises(AssertionError, match="subsequence"):
                assert_tool_sequence(NATIVE_TRACE, ["summarize", "search"])

    def test_missing_tool_fails(self):
        with run_context():
            with pytest.raises(AssertionError):
                assert_tool_sequence(
                    NATIVE_TRACE, ["search", "validate", "summarize"]
                )

    def test_subsequence_not_adjacency(self):
        # "search" then "rank" with "summarize" in between -- still passes
        # because it's subsequence matching, not strict adjacency
        with run_context():
            assert_tool_sequence(NATIVE_TRACE, ["search", "rank"])

    def test_empty_trace_fails(self):
        with run_context():
            with pytest.raises(AssertionError):
                assert_tool_sequence([], ["search"])


# ---------------------------------------------------------------------------
# assert_no_tool_called
# ---------------------------------------------------------------------------

class TestAssertNoToolCalled:

    def test_happy_path(self):
        with run_context() as results:
            score = assert_no_tool_called(NATIVE_TRACE, "delete_all")
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].assertion_type == "no_tool_called"

    def test_failure_tool_was_called(self):
        with run_context():
            with pytest.raises(AssertionError, match="should not have been called"):
                assert_no_tool_called(NATIVE_TRACE, "search")

    def test_empty_trace_passes(self):
        with run_context() as results:
            assert_no_tool_called([], "anything")
        assert results[0].passed is True


# ---------------------------------------------------------------------------
# trace normalization (OpenAI / Anthropic / native)
# ---------------------------------------------------------------------------

class TestNormalizeToolCall:

    def test_native_format(self):
        result = _normalize_tool_call(
            {"name": "search", "args": ["q"], "kwargs": {"limit": 5}}
        )
        assert result == {"name": "search", "args": ["q"], "kwargs": {"limit": 5}}

    def test_openai_format_with_json_string_arguments(self):
        item = {
            "function": {
                "name": "get_weather",
                "arguments": '{"city": "Paris", "units": "celsius"}',
            }
        }
        result = _normalize_tool_call(item)
        assert result["name"] == "get_weather"
        assert result["kwargs"] == {"city": "Paris", "units": "celsius"}

    def test_openai_format_with_dict_arguments(self):
        item = {"function": {"name": "lookup", "arguments": {"id": 42}}}
        result = _normalize_tool_call(item)
        assert result["name"] == "lookup"
        assert result["kwargs"] == {"id": 42}

    def test_anthropic_format(self):
        item = {
            "type": "tool_use",
            "name": "fetch_url",
            "input": {"url": "https://example.com"},
        }
        result = _normalize_tool_call(item)
        assert result["name"] == "fetch_url"
        assert result["kwargs"] == {"url": "https://example.com"}

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="Could not extract tool name"):
            _normalize_tool_call({"foo": "bar"})

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            _normalize_tool_call("not a dict")

    def test_openai_trace_works_with_assertions(self):
        openai_trace = [
            {"function": {"name": "search", "arguments": '{"q": "hello"}'}},
            {"function": {"name": "summarize", "arguments": "{}"}},
        ]
        with run_context():
            assert_tool_called(openai_trace, "search", kwargs={"q": "hello"})
            assert_tool_sequence(openai_trace, ["search", "summarize"])
            assert_no_tool_called(openai_trace, "delete_all")

    def test_anthropic_trace_works_with_assertions(self):
        anthropic_trace = [
            {"type": "tool_use", "name": "search", "input": {"q": "hi"}},
            {"type": "tool_use", "name": "rank", "input": {"top_k": 3}},
        ]
        with run_context():
            assert_tool_called(anthropic_trace, "rank", kwargs={"top_k": 3})
            assert_tool_sequence(anthropic_trace, ["search", "rank"])
