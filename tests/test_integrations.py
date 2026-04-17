"""Tests for auto-instrumentation wrappers (OpenAI and LiteLLM)."""

from __future__ import annotations

import asyncio
import types
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes that mimic OpenAI / LiteLLM response shapes
# ---------------------------------------------------------------------------

class _FakePromptTokensDetails:
    def __init__(self, cached_tokens=0):
        self.cached_tokens = cached_tokens


class _FakeUsage:
    def __init__(
        self,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cached_tokens=0,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.prompt_tokens_details = _FakePromptTokensDetails(cached_tokens)


class _FakeResponse:
    def __init__(self, model="gpt-4o", cached_tokens=0):
        self.model = model
        self.usage = _FakeUsage(cached_tokens=cached_tokens)


class _FakeCompletions:
    """Mimics ``client.chat.completions`` with a sync ``create``."""

    def create(self, **kwargs):
        return _FakeResponse()


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeOpenAIClient:
    """Minimal stand-in for ``openai.OpenAI()``."""

    def __init__(self):
        self.chat = _FakeChat()


# ---------------------------------------------------------------------------
# OpenAI wrapper tests
# ---------------------------------------------------------------------------


class TestPatchOpenAI:
    """Tests for promptry.integrations.openai.patch_openai."""

    def test_response_returned_unchanged(self):
        from promptry.integrations.openai import patch_openai

        client = _FakeOpenAIClient()
        patch_openai(client, prompt_name="test")

        resp = client.chat.completions.create(
            messages=[{"role": "system", "content": "Be helpful"}],
        )
        assert isinstance(resp, _FakeResponse)
        assert resp.model == "gpt-4o"

    @patch("promptry.track")
    def test_track_called_with_system_prompt(self, mock_track):
        from promptry.integrations.openai import patch_openai

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeOpenAIClient()
        patch_openai(client, prompt_name="my-bot")

        client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a pirate"},
                {"role": "user", "content": "Hello"},
            ],
        )

        # Single post-call tracking with metadata
        assert mock_track.call_count == 1

        call = mock_track.call_args_list[0]
        assert call[0][0] == "You are a pirate"
        assert call[0][1] == "my-bot"

    @patch("promptry.track")
    def test_metadata_includes_token_usage(self, mock_track):
        from promptry.integrations.openai import patch_openai

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeOpenAIClient()
        patch_openai(client, prompt_name="cost-test")

        client.chat.completions.create(
            messages=[{"role": "system", "content": "sys"}],
        )

        # The post-call track should carry metadata
        post_call = mock_track.call_args_list[-1]
        meta = post_call[1].get("metadata") or (
            post_call[0][3] if len(post_call[0]) > 3 else None
        )
        assert meta is not None
        assert meta["prompt_tokens"] == 10
        assert meta["completion_tokens"] == 20
        assert meta["total_tokens"] == 30
        assert meta["model"] == "gpt-4o"

    @patch("promptry.track", side_effect=RuntimeError("boom"))
    def test_tracking_failure_does_not_break_call(self, mock_track):
        from promptry.integrations.openai import patch_openai

        client = _FakeOpenAIClient()
        patch_openai(client, prompt_name="resilient")

        # Should NOT raise even though track() explodes
        resp = client.chat.completions.create(
            messages=[{"role": "system", "content": "hello"}],
        )
        assert isinstance(resp, _FakeResponse)

    def test_no_system_message_still_works(self):
        from promptry.integrations.openai import patch_openai

        client = _FakeOpenAIClient()
        patch_openai(client, prompt_name="no-sys")

        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
        )
        assert isinstance(resp, _FakeResponse)

    @patch("promptry.track")
    def test_async_client(self, mock_track):
        """Verify the wrapper handles an async create method."""
        from promptry.integrations.openai import patch_openai

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeOpenAIClient()

        # Replace create with an async version
        async def async_create(**kwargs):
            return _FakeResponse()

        client.chat.completions.create = async_create
        patch_openai(client, prompt_name="async-test")

        async def _run():
            return await client.chat.completions.create(
                messages=[{"role": "system", "content": "async sys"}],
            )

        resp = asyncio.run(_run())
        assert isinstance(resp, _FakeResponse)
        assert mock_track.call_count == 1

    @patch("promptry.track")
    def test_metadata_includes_cached_tokens(self, mock_track):
        from promptry.integrations.openai import patch_openai

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeOpenAIClient()

        class _CachedCompletions:
            def create(self, **kwargs):
                return _FakeResponse(cached_tokens=8)

        client.chat.completions = _CachedCompletions()
        patch_openai(client, prompt_name="cached")

        client.chat.completions.create(
            messages=[{"role": "system", "content": "sys"}],
        )

        meta = mock_track.call_args_list[-1][1].get("metadata")
        assert meta is not None
        assert meta["cached_tokens"] == 8
        assert meta["cache_write_tokens"] == 0
        assert meta["tokens_in"] == 10
        assert meta["tokens_out"] == 20
        assert meta["provider"] == "openai"

    @patch("promptry.track")
    def test_metadata_no_cached_tokens_defaults_to_zero(self, mock_track):
        from promptry.integrations.openai import patch_openai

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeOpenAIClient()
        patch_openai(client, prompt_name="nocache")

        client.chat.completions.create(
            messages=[{"role": "system", "content": "sys"}],
        )

        meta = mock_track.call_args_list[-1][1].get("metadata")
        assert meta["cached_tokens"] == 0
        assert meta["cache_write_tokens"] == 0


# ---------------------------------------------------------------------------
# Anthropic wrapper tests
# ---------------------------------------------------------------------------


class _FakeAnthropicUsage:
    def __init__(
        self,
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens


class _FakeAnthropicResponse:
    def __init__(
        self,
        model="claude-sonnet-4",
        cache_read=0,
        cache_create=0,
    ):
        self.model = model
        self.usage = _FakeAnthropicUsage(
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_create,
        )


class _FakeAnthropicMessages:
    def __init__(self, cache_read=0, cache_create=0):
        self._cache_read = cache_read
        self._cache_create = cache_create

    def create(self, **kwargs):
        return _FakeAnthropicResponse(
            cache_read=self._cache_read,
            cache_create=self._cache_create,
        )


class _FakeAnthropicClient:
    def __init__(self, cache_read=0, cache_create=0):
        self.messages = _FakeAnthropicMessages(cache_read, cache_create)


class TestPatchAnthropic:
    """Tests for promptry.integrations.anthropic.patch_anthropic."""

    def test_response_returned_unchanged(self):
        from promptry.integrations.anthropic import patch_anthropic

        client = _FakeAnthropicClient()
        patch_anthropic(client, prompt_name="test")

        resp = client.messages.create(
            system="You are helpful",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert isinstance(resp, _FakeAnthropicResponse)

    @patch("promptry.track")
    def test_track_called_with_system_prompt(self, mock_track):
        from promptry.integrations.anthropic import patch_anthropic

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeAnthropicClient()
        patch_anthropic(client, prompt_name="claude-bot")

        client.messages.create(
            system="You are a helpful assistant",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert mock_track.call_count == 1
        call = mock_track.call_args_list[0]
        assert call[0][0] == "You are a helpful assistant"
        assert call[0][1] == "claude-bot"

    @patch("promptry.track")
    def test_metadata_includes_cache_tokens(self, mock_track):
        from promptry.integrations.anthropic import patch_anthropic

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeAnthropicClient(cache_read=80, cache_create=10)
        patch_anthropic(client, prompt_name="cached-claude")

        client.messages.create(
            system="static system",
            messages=[{"role": "user", "content": "q"}],
        )

        meta = mock_track.call_args_list[-1][1].get("metadata")
        assert meta is not None
        assert meta["cached_tokens"] == 80
        assert meta["cache_write_tokens"] == 10
        # tokens_in should be all-inclusive: 100 input + 80 read + 10 create
        assert meta["tokens_in"] == 190
        assert meta["tokens_out"] == 50
        assert meta["provider"] == "anthropic"
        assert meta["model"] == "claude-sonnet-4"

    @patch("promptry.track", side_effect=RuntimeError("boom"))
    def test_tracking_failure_does_not_break_call(self, _mock_track):
        from promptry.integrations.anthropic import patch_anthropic

        client = _FakeAnthropicClient()
        patch_anthropic(client, prompt_name="resilient")

        resp = client.messages.create(
            system="hello",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert isinstance(resp, _FakeAnthropicResponse)

    @patch("promptry.track")
    def test_system_as_list_of_blocks(self, mock_track):
        from promptry.integrations.anthropic import patch_anthropic

        mock_track.side_effect = lambda content, name, **kw: content

        client = _FakeAnthropicClient()
        patch_anthropic(client, prompt_name="sysblocks")

        client.messages.create(
            system=[
                {"type": "text", "text": "Part one.", "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": "Part two."},
            ],
            messages=[{"role": "user", "content": "hi"}],
        )
        call = mock_track.call_args_list[-1]
        assert "Part one." in call[0][0]
        assert "Part two." in call[0][0]


# ---------------------------------------------------------------------------
# LiteLLM wrapper tests
# ---------------------------------------------------------------------------


class TestPatchLiteLLM:
    """Tests for promptry.integrations.litellm.patch_litellm."""

    def _make_fake_litellm(self):
        """Create a fake ``litellm`` module with a ``completion`` function."""
        fake = types.ModuleType("litellm")
        fake.completion = MagicMock(return_value=_FakeResponse())
        return fake

    @patch.dict("sys.modules", {})
    def test_response_returned_unchanged(self):
        import sys

        fake_litellm = self._make_fake_litellm()
        sys.modules["litellm"] = fake_litellm

        from promptry.integrations.litellm import patch_litellm

        patch_litellm(prompt_name="test-llm")

        resp = fake_litellm.completion(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Be helpful"}],
        )
        assert isinstance(resp, _FakeResponse)

    @patch("promptry.track")
    def test_track_called_with_system_prompt(self, mock_track):
        import sys

        mock_track.side_effect = lambda content, name, **kw: content

        fake_litellm = self._make_fake_litellm()
        sys.modules["litellm"] = fake_litellm

        from promptry.integrations.litellm import patch_litellm

        patch_litellm(prompt_name="lit-bot")

        fake_litellm.completion(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a wizard"},
                {"role": "user", "content": "Cast a spell"},
            ],
        )

        assert mock_track.call_count == 1
        call = mock_track.call_args_list[0]
        assert call[0][0] == "You are a wizard"
        assert call[0][1] == "lit-bot"

    @patch("promptry.track")
    def test_metadata_includes_token_usage(self, mock_track):
        import sys

        mock_track.side_effect = lambda content, name, **kw: content

        fake_litellm = self._make_fake_litellm()
        sys.modules["litellm"] = fake_litellm

        from promptry.integrations.litellm import patch_litellm

        patch_litellm(prompt_name="cost")

        fake_litellm.completion(
            model="gpt-4o",
            messages=[{"role": "system", "content": "sys"}],
        )

        post_call = mock_track.call_args_list[-1]
        meta = post_call[1].get("metadata") or (
            post_call[0][3] if len(post_call[0]) > 3 else None
        )
        assert meta is not None
        assert meta["prompt_tokens"] == 10
        assert meta["completion_tokens"] == 20
        assert meta["total_tokens"] == 30

    @patch("promptry.track", side_effect=RuntimeError("boom"))
    def test_tracking_failure_does_not_break_call(self, mock_track):
        import sys

        fake_litellm = self._make_fake_litellm()
        sys.modules["litellm"] = fake_litellm

        from promptry.integrations.litellm import patch_litellm

        patch_litellm(prompt_name="resilient")

        resp = fake_litellm.completion(
            model="gpt-4o",
            messages=[{"role": "system", "content": "hello"}],
        )
        assert isinstance(resp, _FakeResponse)

    @patch("promptry.track")
    def test_metadata_extracts_cached_tokens(self, mock_track):
        import sys

        mock_track.side_effect = lambda content, name, **kw: content

        # litellm normalizes to OpenAI shape: prompt_tokens_details.cached_tokens
        fake_litellm = self._make_fake_litellm()
        fake_litellm.completion = MagicMock(
            return_value=_FakeResponse(cached_tokens=25)
        )
        sys.modules["litellm"] = fake_litellm

        from promptry.integrations.litellm import patch_litellm

        patch_litellm(prompt_name="cached-lit")

        fake_litellm.completion(
            model="gpt-4o",
            messages=[{"role": "system", "content": "s"}],
        )

        meta = mock_track.call_args_list[-1][1].get("metadata")
        assert meta["cached_tokens"] == 25
        assert meta["tokens_in"] == 10
        assert meta["provider"] == "litellm"

    @patch("promptry.track")
    def test_async_acompletion(self, mock_track):
        import sys

        mock_track.side_effect = lambda content, name, **kw: content

        fake_litellm = self._make_fake_litellm()

        # Add an async acompletion
        async def fake_acompletion(*args, **kwargs):
            return _FakeResponse()

        fake_litellm.acompletion = fake_acompletion
        sys.modules["litellm"] = fake_litellm

        from promptry.integrations.litellm import patch_litellm

        patch_litellm(prompt_name="async-lit")

        async def _run():
            return await fake_litellm.acompletion(
                model="gpt-4o",
                messages=[{"role": "system", "content": "async sys"}],
            )

        resp = asyncio.run(_run())
        assert isinstance(resp, _FakeResponse)
        assert mock_track.call_count == 1
