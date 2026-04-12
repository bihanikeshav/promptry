"""Tests for auto-instrumentation wrappers (OpenAI and LiteLLM)."""

from __future__ import annotations

import asyncio
import types
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes that mimic OpenAI / LiteLLM response shapes
# ---------------------------------------------------------------------------

class _FakeUsage:
    def __init__(self, prompt_tokens=10, completion_tokens=20, total_tokens=30):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _FakeResponse:
    def __init__(self, model="gpt-4o"):
        self.model = model
        self.usage = _FakeUsage()


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

        # At minimum 2 calls: pre-call (system prompt) + post-call (with metadata)
        assert mock_track.call_count >= 2

        # First call is the pre-call tracking of the system prompt
        first_call = mock_track.call_args_list[0]
        assert first_call[0][0] == "You are a pirate"
        assert first_call[0][1] == "my-bot"

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
        assert mock_track.call_count >= 2


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

        assert mock_track.call_count >= 2
        first_call = mock_track.call_args_list[0]
        assert first_call[0][0] == "You are a wizard"
        assert first_call[0][1] == "lit-bot"

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
        assert mock_track.call_count >= 2
