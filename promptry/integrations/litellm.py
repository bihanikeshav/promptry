"""Auto-instrumentation for LiteLLM. Wraps litellm.completion to track prompts and cost."""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any

logger = logging.getLogger("promptry.integrations.litellm")


def _extract_system_prompt(kwargs: dict[str, Any]) -> str | None:
    """Pull the system message text from the messages list, if present."""
    messages = kwargs.get("messages") or []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
    return None


def _extract_usage_metadata(response: Any) -> dict[str, Any]:
    """Build a metadata dict from the response's token usage."""
    meta: dict[str, Any] = {}
    # LiteLLM responses follow the OpenAI response shape
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return meta

    if isinstance(usage, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if key in usage:
                meta[key] = usage[key]
    else:
        for attr in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = getattr(usage, attr, None)
            if val is not None:
                meta[attr] = val

    # model
    model = (
        getattr(response, "model", None)
        if not isinstance(response, dict)
        else response.get("model")
    )
    if model is not None:
        meta["model"] = model
    return meta


def patch_litellm(prompt_name: str = "litellm") -> None:
    """Wrap ``litellm.completion`` to automatically track prompts and cost.

    Usage::

        import litellm
        from promptry.integrations.litellm import patch_litellm

        patch_litellm(prompt_name="my-service")

        # Now all litellm.completion calls are tracked
        response = litellm.completion(model="gpt-4o", messages=[...])

    The wrapper monkey-patches ``litellm.completion`` (and
    ``litellm.acompletion`` if it exists and is a coroutine) so that
    every call records the system prompt and token usage via
    :func:`promptry.track`.  The original response is always returned
    unchanged, even if tracking raises an exception.
    """
    try:
        import litellm  # noqa: F811 — lazy import
    except ImportError as exc:
        raise ImportError(
            "litellm is required for this integration. "
            "Install it with: pip install promptry[litellm]"
        ) from exc

    # --- sync wrapper ---
    original_completion = litellm.completion

    @functools.wraps(original_completion)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            from promptry import track

            system_prompt = _extract_system_prompt(kwargs)
            if system_prompt is not None:
                track(system_prompt, prompt_name)
        except Exception:
            logger.debug("pre-call tracking failed", exc_info=True)

        response = original_completion(*args, **kwargs)

        try:
            from promptry import track

            meta = _extract_usage_metadata(response)
            if meta:
                system_prompt = _extract_system_prompt(kwargs)
                content = system_prompt or ""
                track(content, prompt_name, metadata=meta)
        except Exception:
            logger.debug("post-call tracking failed", exc_info=True)

        return response

    litellm.completion = sync_wrapper

    # --- async wrapper ---
    original_acompletion = getattr(litellm, "acompletion", None)
    if original_acompletion is not None and inspect.iscoroutinefunction(
        original_acompletion
    ):

        @functools.wraps(original_acompletion)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                from promptry import track

                system_prompt = _extract_system_prompt(kwargs)
                if system_prompt is not None:
                    track(system_prompt, prompt_name)
            except Exception:
                logger.debug("pre-call tracking failed", exc_info=True)

            response = await original_acompletion(*args, **kwargs)

            try:
                from promptry import track

                meta = _extract_usage_metadata(response)
                if meta:
                    system_prompt = _extract_system_prompt(kwargs)
                    content = system_prompt or ""
                    track(content, prompt_name, metadata=meta)
            except Exception:
                logger.debug("post-call tracking failed", exc_info=True)

            return response

        litellm.acompletion = async_wrapper
