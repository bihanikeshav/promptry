"""Tests for the multi-turn Conversation data model and assertions."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from promptry.conversation import Conversation, Turn
from promptry.evaluator import run_context
from promptry.assertions import (
    assert_conversation_length,
    assert_all_assistant_turns,
    assert_any_assistant_turn,
    assert_conversation_coherent,
    assert_no_repetition,
    assert_contains,
)


# ---------------------------------------------------------------------------
# Conversation data model
# ---------------------------------------------------------------------------


class TestConversationBuilder:

    def test_empty(self):
        conv = Conversation()
        assert len(conv) == 0
        assert conv.last() is None
        assert conv.assistant_turns() == []
        assert conv.user_turns() == []

    def test_add_returns_self_for_chaining(self):
        conv = Conversation().add("user", "hi").add("assistant", "hello")
        assert len(conv) == 2
        assert conv.turns[0].role == "user"
        assert conv.turns[0].content == "hi"
        assert conv.turns[1].role == "assistant"
        assert conv.turns[1].content == "hello"

    def test_last_without_role(self):
        conv = Conversation().add("user", "q").add("assistant", "a")
        last = conv.last()
        assert last is not None
        assert last.role == "assistant"
        assert last.content == "a"

    def test_last_filtered_by_role(self):
        conv = (
            Conversation()
            .add("user", "q1")
            .add("assistant", "a1")
            .add("user", "q2")
            .add("assistant", "a2")
        )
        assert conv.last("user").content == "q2"
        assert conv.last("assistant").content == "a2"
        assert conv.last("system") is None

    def test_assistant_and_user_filters(self):
        conv = (
            Conversation()
            .add("system", "sys")
            .add("user", "u1")
            .add("assistant", "a1")
            .add("user", "u2")
            .add("assistant", "a2")
        )
        assert [t.content for t in conv.user_turns()] == ["u1", "u2"]
        assert [t.content for t in conv.assistant_turns()] == ["a1", "a2"]

    def test_add_accepts_metadata_and_tools(self):
        conv = Conversation().add(
            "assistant",
            "calling tool",
            tools=[{"name": "search", "input": {"q": "x"}}],
            metadata={"latency_ms": 42},
        )
        t = conv.turns[0]
        assert t.tools == [{"name": "search", "input": {"q": "x"}}]
        assert t.metadata == {"latency_ms": 42}


class TestConversationFromOpenAI:

    def test_basic_messages(self):
        msgs = [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        conv = Conversation.from_openai(msgs)
        assert len(conv) == 3
        assert conv.turns[0].role == "system"
        assert conv.turns[1].content == "hi"
        assert conv.turns[2].content == "hello"

    def test_tool_calls_captured(self):
        msgs = [
            {"role": "user", "content": "search for cats"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "search", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "results"},
        ]
        conv = Conversation.from_openai(msgs)
        assistant_turn = conv.turns[1]
        assert len(assistant_turn.tools) == 1
        assert assistant_turn.tools[0]["id"] == "c1"
        tool_turn = conv.turns[2]
        assert tool_turn.metadata.get("tool_call_id") == "c1"
        assert tool_turn.content == "results"

    def test_multimodal_content_flattened(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "look at this"},
                {"type": "image_url", "image_url": {"url": "..."}},
            ]},
        ]
        conv = Conversation.from_openai(msgs)
        assert "look at this" in conv.turns[0].content


class TestConversationFromAnthropic:

    def test_basic_messages(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        conv = Conversation.from_anthropic(msgs)
        assert len(conv) == 2
        assert conv.turns[0].content == "hi"
        assert conv.turns[1].content == "hello"

    def test_block_content(self):
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {"role": "assistant", "content": [
                {"type": "text", "text": "let me check"},
                {"type": "tool_use", "id": "t1", "name": "get_weather",
                 "input": {"city": "SF"}},
            ]},
        ]
        conv = Conversation.from_anthropic(msgs)
        assert conv.turns[0].content == "hi"
        assistant = conv.turns[1]
        assert "let me check" in assistant.content
        assert len(assistant.tools) == 1
        assert assistant.tools[0]["name"] == "get_weather"
        assert assistant.tools[0]["input"] == {"city": "SF"}

    def test_tool_result_block(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": "sunny, 70F"},
            ]},
        ]
        conv = Conversation.from_anthropic(msgs)
        assert "sunny, 70F" in conv.turns[0].content


# ---------------------------------------------------------------------------
# Non-semantic conversation assertions
# ---------------------------------------------------------------------------


class TestAssertConversationLength:

    def test_within_bounds(self):
        conv = Conversation().add("user", "hi").add("assistant", "hello")
        with run_context() as results:
            score = assert_conversation_length(conv, min_turns=1, max_turns=5)
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].assertion_type == "conversation_length"

    def test_too_short(self):
        conv = Conversation().add("user", "hi")
        with run_context():
            with pytest.raises(AssertionError, match="out of bounds"):
                assert_conversation_length(conv, min_turns=3)

    def test_too_long(self):
        conv = Conversation()
        for i in range(10):
            conv.add("user", f"q{i}")
        with run_context():
            with pytest.raises(AssertionError, match="out of bounds"):
                assert_conversation_length(conv, max_turns=5)


class TestAssertAllAssistantTurns:

    def test_all_pass(self):
        conv = (
            Conversation()
            .add("user", "weather?")
            .add("assistant", "The weather is sunny")
            .add("user", "tomorrow?")
            .add("assistant", "Tomorrow's weather will be rainy")
        )
        with run_context() as results:
            score = assert_all_assistant_turns(
                conv,
                lambda t: assert_contains(t, ["weather"]),
            )
        assert score == 1.0
        assert results[0].passed is True

    def test_one_fails(self):
        conv = (
            Conversation()
            .add("assistant", "weather is sunny")
            .add("assistant", "totally unrelated response")
        )
        with run_context() as results:
            with pytest.raises(AssertionError, match="failed predicate"):
                assert_all_assistant_turns(
                    conv,
                    lambda t: assert_contains(t, ["weather"]),
                )
        # the outer result should record 1/2 passed
        assert results[0].score == pytest.approx(0.5)
        assert results[0].details["failed_turns"] == 1

    def test_no_assistant_turns(self):
        conv = Conversation().add("user", "hi")
        with run_context():
            with pytest.raises(AssertionError, match="No assistant turns"):
                assert_all_assistant_turns(conv, lambda t: None)


class TestAssertAnyAssistantTurn:

    def test_second_turn_matches(self):
        conv = (
            Conversation()
            .add("assistant", "let me think")
            .add("assistant", "the answer is 42")
        )
        with run_context() as results:
            score = assert_any_assistant_turn(
                conv,
                lambda t: assert_contains(t, ["42"]),
            )
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].details["matched_turn_index"] == 1

    def test_no_match(self):
        conv = (
            Conversation()
            .add("assistant", "nope")
            .add("assistant", "still nope")
        )
        with run_context():
            with pytest.raises(AssertionError, match="No assistant turn"):
                assert_any_assistant_turn(
                    conv,
                    lambda t: assert_contains(t, ["42"]),
                )

    def test_no_assistant_turns(self):
        conv = Conversation().add("user", "hi")
        with run_context():
            with pytest.raises(AssertionError, match="No assistant turns"):
                assert_any_assistant_turn(conv, lambda t: None)


# ---------------------------------------------------------------------------
# Semantic conversation assertions (mocked embedding model)
# ---------------------------------------------------------------------------


class _FakeModel:
    """Stand-in for SentenceTransformer that maps each text to a fixed vector.

    We store a dict of text -> vector. Unknown texts get a deterministic
    vector derived from hash. This lets tests craft specific similarities.
    """

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def encode(self, texts):
        import numpy as np
        out = []
        for t in texts:
            if t in self.vectors:
                out.append(np.array(self.vectors[t], dtype=float))
            else:
                # deterministic but likely-different fallback
                h = abs(hash(t)) % 1000
                out.append(np.array([h / 1000.0, 1 - h / 1000.0], dtype=float))
        return np.array(out)


def _patch_model(vectors: dict[str, list[float]]):
    """Patch the lazy model loader in promptry.assertions."""
    import promptry.assertions as _a
    return patch.object(_a, "_get_model", lambda: _FakeModel(vectors))


# cos_sim is used inside the assertions; we need it to be available.
# If sentence-transformers isn't installed, we synthesize a minimal shim.
try:
    import sentence_transformers.util  # noqa: F401
    _HAS_ST_UTIL = True
except ImportError:
    _HAS_ST_UTIL = False


@pytest.fixture
def _ensure_cos_sim(monkeypatch):
    """Make sure sentence_transformers.util.cos_sim is importable.

    If the real package is missing, install a shim module so the
    ``from sentence_transformers.util import cos_sim`` inside the
    assertion body succeeds in tests.
    """
    if _HAS_ST_UTIL:
        yield
        return

    import sys
    import types
    import numpy as np

    def _cos_sim(a, b):
        a = np.asarray(a, dtype=float).reshape(-1)
        b = np.asarray(b, dtype=float).reshape(-1)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        v = float(np.dot(a, b) / denom)
        # mimic the torch-tensor-ish shape assertions use: [0][0]
        return [[v]]

    pkg = types.ModuleType("sentence_transformers")
    util = types.ModuleType("sentence_transformers.util")
    util.cos_sim = _cos_sim
    pkg.util = util
    monkeypatch.setitem(sys.modules, "sentence_transformers", pkg)
    monkeypatch.setitem(sys.modules, "sentence_transformers.util", util)
    yield


class TestAssertConversationCoherent:

    def test_coherent_turns(self, _ensure_cos_sim):
        conv = (
            Conversation()
            .add("assistant", "a")
            .add("assistant", "b")
            .add("assistant", "c")
        )
        vectors = {
            "a": [1.0, 0.0],
            "b": [0.9, 0.1],
            "c": [0.95, 0.05],
        }
        with _patch_model(vectors), run_context() as results:
            score = assert_conversation_coherent(conv, threshold=0.5)
        assert score >= 0.5
        assert results[0].passed is True

    def test_incoherent_turns(self, _ensure_cos_sim):
        conv = (
            Conversation()
            .add("assistant", "a")
            .add("assistant", "b")
        )
        vectors = {
            "a": [1.0, 0.0],
            "b": [0.0, 1.0],  # orthogonal -> similarity 0
        }
        with _patch_model(vectors), run_context():
            with pytest.raises(AssertionError, match="incoherent"):
                assert_conversation_coherent(conv, threshold=0.5)

    def test_single_turn_trivially_coherent(self, _ensure_cos_sim):
        conv = Conversation().add("assistant", "solo")
        with run_context() as results:
            score = assert_conversation_coherent(conv)
        assert score == 1.0
        assert results[0].passed is True


class TestAssertNoRepetition:

    def test_no_repetition(self, _ensure_cos_sim):
        conv = (
            Conversation()
            .add("assistant", "first")
            .add("assistant", "second")
            .add("assistant", "third")
        )
        vectors = {
            "first":  [1.0, 0.0, 0.0],
            "second": [0.0, 1.0, 0.0],
            "third":  [0.0, 0.0, 1.0],
        }
        with _patch_model(vectors), run_context() as results:
            score = assert_no_repetition(conv, similarity_threshold=0.95)
        assert score < 0.95
        assert results[0].passed is True

    def test_detects_loop(self, _ensure_cos_sim):
        conv = (
            Conversation()
            .add("assistant", "I can help")
            .add("assistant", "different answer")
            .add("assistant", "I can help")  # near-duplicate of first
        )
        vectors = {
            "I can help":        [1.0, 0.0],
            "different answer":  [0.0, 1.0],
        }
        with _patch_model(vectors), run_context() as results:
            with pytest.raises(AssertionError, match="Repetition detected"):
                assert_no_repetition(conv, similarity_threshold=0.95)
        # max similarity pair should be turns 0 and 2
        assert results[0].details["worst_pair_indices"] == [0, 2]

    def test_single_turn_no_repetition(self, _ensure_cos_sim):
        conv = Conversation().add("assistant", "solo")
        with run_context() as results:
            score = assert_no_repetition(conv)
        assert score == 0.0
        assert results[0].passed is True
