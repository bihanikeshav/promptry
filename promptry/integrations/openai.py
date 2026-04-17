"""Auto-instrumentation for OpenAI. Wraps the client to track prompts and cost."""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any

logger = logging.getLogger("promptry.integrations.openai")


def _extract_system_prompt(kwargs: dict[str, Any]) -> str | None:
    """Pull the system message text from the messages list, if present."""
    messages = kwargs.get("messages") or []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            # Handle list-of-parts format
            if isinstance(content, list):
                return " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
    return None


def _extract_usage_metadata(response: Any) -> dict[str, Any]:
    """Build a metadata dict from the response's token usage.

    Includes prompt-cache fields when the provider reports them
    (OpenAI exposes them via ``usage.prompt_tokens_details.cached_tokens``).
    """
    meta: dict[str, Any] = {}
    usage = getattr(response, "usage", None)
    if usage is None:
        return meta
    for attr in ("prompt_tokens", "completion_tokens", "total_tokens"):
        val = getattr(usage, attr, None)
        if val is not None:
            meta[attr] = val

    # Unified token fields
    if "prompt_tokens" in meta:
        meta["tokens_in"] = meta["prompt_tokens"]
    if "completion_tokens" in meta:
        meta["tokens_out"] = meta["completion_tokens"]

    # Cached tokens live under usage.prompt_tokens_details.cached_tokens
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
        if not cached and isinstance(details, dict):
            cached = details.get("cached_tokens", 0) or 0
    meta["cached_tokens"] = int(cached)
    meta["cache_write_tokens"] = 0  # OpenAI does not bill a separate cache-write

    model = getattr(response, "model", None)
    if model is not None:
        meta["model"] = model
    meta["provider"] = "openai"
    return meta


def patch_openai(client: Any, prompt_name: str = "openai") -> None:
    """Wrap an OpenAI client to automatically track prompts and cost.

    Usage::

        from openai import OpenAI
        from promptry.integrations.openai import patch_openai

        client = OpenAI()
        patch_openai(client, prompt_name="my-chatbot")

        # Now all calls are automatically tracked
        response = client.chat.completions.create(...)

    The wrapper monkey-patches ``client.chat.completions.create`` so that
    every call automatically records the system prompt and token usage via
    :func:`promptry.track`.  The original response is always returned
    unchanged, even if tracking raises an exception.
    """
    original_create = client.chat.completions.create

    if inspect.iscoroutinefunction(original_create):
        @functools.wraps(original_create)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            response = await original_create(*args, **kwargs)

            try:
                from promptry import track

                system_prompt = _extract_system_prompt(kwargs) or ""
                meta = _extract_usage_metadata(response)
                track(system_prompt, prompt_name, metadata=meta)
            except Exception:
                logger.debug("post-call tracking failed", exc_info=True)

            return response

        client.chat.completions.create = async_wrapper
    else:
        @functools.wraps(original_create)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            response = original_create(*args, **kwargs)

            try:
                from promptry import track

                system_prompt = _extract_system_prompt(kwargs) or ""
                meta = _extract_usage_metadata(response)
                track(system_prompt, prompt_name, metadata=meta)
            except Exception:
                logger.debug("post-call tracking failed", exc_info=True)

            return response

        client.chat.completions.create = sync_wrapper
