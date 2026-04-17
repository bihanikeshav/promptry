"""Prompt registry -- versioning, hashing, and diffing.

The main thing users care about is track(). Stick it in your pipeline,
it handles the rest.
"""
from __future__ import annotations

import difflib
import hashlib
import random
import threading

from promptry.models import PromptRecord


class PromptRegistry:

    def __init__(self, storage=None):
        if storage is None:
            from promptry.storage import get_storage
            storage = get_storage()
        self._storage = storage

    @property
    def storage(self):
        return self._storage

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def save(self, name, content, tag=None, metadata=None) -> PromptRecord:
        """Save a new version. Skips if identical content already exists."""
        h = self.content_hash(content)
        record = self._storage.save_prompt(name, content, h, metadata)

        if tag:
            self._storage.tag_prompt(record.id, tag)
            record.tags = self._storage.get_tags(record.id)

        return record

    def get(self, name, version=None) -> PromptRecord | None:
        return self._storage.get_prompt(name, version)

    def get_by_tag(self, name, tag) -> PromptRecord | None:
        return self._storage.get_prompt_by_tag(name, tag)

    def list(self, name=None) -> list[PromptRecord]:
        return self._storage.list_prompts(name)

    def tag(self, name, version, tag):
        record = self._storage.get_prompt(name, version)
        if not record:
            raise ValueError(f"Prompt '{name}' version {version} not found")
        self._storage.tag_prompt(record.id, tag)

    def diff(self, name, v1, v2) -> str:
        """Unified diff between two versions."""
        p1 = self._storage.get_prompt(name, v1)
        p2 = self._storage.get_prompt(name, v2)
        if not p1:
            raise ValueError(f"Prompt '{name}' version {v1} not found")
        if not p2:
            raise ValueError(f"Prompt '{name}' version {v2} not found")

        return "".join(difflib.unified_diff(
            p1.content.splitlines(keepends=True),
            p2.content.splitlines(keepends=True),
            fromfile=f"{name}@v{v1}",
            tofile=f"{name}@v{v2}",
        ))


# ---------------------------------------------------------------------------
# track() -- the main integration point
#
# One line in your existing code. Returns the prompt string unchanged.
# Under the hood it versions the content by SHA-256 hash.
# Repeated calls with the same content are a no-op (in-memory cache).
# ---------------------------------------------------------------------------

_default_registry: PromptRegistry | None = None
_track_cache: dict[str, None] = {}  # bounded LRU-ish cache, max 10k entries
_TRACK_CACHE_MAX = 10_000
_track_lock = threading.Lock()


def _get_registry() -> PromptRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PromptRegistry()
    return _default_registry


def reset_registry():
    global _default_registry, _track_cache
    _default_registry = None
    _track_cache.clear()


def track(content: str, name: str, tag=None, metadata=None) -> str:
    """Track a prompt version. Returns the content string unchanged.

    Usage::

        from promptry import track

        prompt = track("You are a helpful assistant...", "rag-qa")
        response = llm.chat(system=prompt, ...)

    First call writes to storage. Subsequent calls with the same content
    hit an in-memory cache and skip all I/O.
    """
    from promptry.config import get_config

    config = get_config()
    if config.storage.mode == "off":
        return content

    h = PromptRegistry.content_hash(content)
    cache_key = f"{name}:{h}"

    # auto-compute cost when caller provided tokens + model but no explicit cost
    if metadata is not None and isinstance(metadata, dict):
        if "cost" not in metadata and metadata.get("model"):
            try:
                from promptry.pricing import calculate_cost

                tokens_in = int(
                    metadata.get("tokens_in", metadata.get("prompt_tokens", 0)) or 0
                )
                tokens_out = int(
                    metadata.get("tokens_out", metadata.get("completion_tokens", 0)) or 0
                )
                cached_tokens = int(metadata.get("cached_tokens", 0) or 0)
                cache_write_tokens = int(metadata.get("cache_write_tokens", 0) or 0)
                if tokens_in or tokens_out:
                    auto_cost = calculate_cost(
                        metadata["model"],
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cached_tokens=cached_tokens,
                        cache_write_tokens=cache_write_tokens,
                    )
                    if auto_cost is not None:
                        metadata = {**metadata, "cost": auto_cost}
            except Exception:
                import logging
                logging.getLogger("promptry").debug(
                    "auto cost computation failed", exc_info=True
                )

    with _track_lock:
        if cache_key in _track_cache and tag is None:
            return content

    try:
        registry = _get_registry()
        registry.save(name=name, content=content, tag=tag, metadata=metadata)
    except Exception:
        import logging
        logging.getLogger("promptry").warning("track() storage write failed", exc_info=True)
        return content

    with _track_lock:
        # bounded cache: evict oldest entries when full
        if len(_track_cache) >= _TRACK_CACHE_MAX:
            # drop first half (cheap bulk eviction)
            keys = list(_track_cache.keys())
            for k in keys[:len(keys) // 2]:
                del _track_cache[k]
        _track_cache[cache_key] = None

    return content


def track_context(
    chunks: list[str],
    name: str,
    metadata=None,
    sample_rate: float | None = None,
) -> list[str]:
    """Track retrieval context alongside a prompt.

    Same idea as track() but for the chunks your RAG pipeline retrieved.
    Helps pinpoint whether a regression was caused by the prompt changing
    or the retrieval drifting.

    sample_rate controls what fraction of calls actually write to storage.
    Defaults to config value (1.0 = every call, 0.1 = 10%).
    """
    from promptry.config import get_config

    config = get_config()
    if config.storage.mode == "off":
        return chunks

    rate = sample_rate if sample_rate is not None else config.tracking.context_sample_rate
    if rate < 1.0 and random.random() > rate:
        return chunks

    joined = "\n---\n".join(chunks)
    context_name = f"{name}:context"

    h = PromptRegistry.content_hash(joined)
    cache_key = f"{context_name}:{h}"

    with _track_lock:
        if cache_key in _track_cache:
            return chunks

    try:
        registry = _get_registry()
        meta = dict(metadata) if metadata else {}
        meta["chunk_count"] = len(chunks)
        registry.save(name=context_name, content=joined, metadata=meta)
    except Exception:
        import logging
        logging.getLogger("promptry").warning("track_context() storage write failed", exc_info=True)
        return chunks

    with _track_lock:
        if len(_track_cache) >= _TRACK_CACHE_MAX:
            keys = list(_track_cache.keys())
            for k in keys[:len(keys) // 2]:
                del _track_cache[k]
        _track_cache[cache_key] = None

    return chunks


def save_dataset(name: str, items: list[dict], metadata: dict | None = None) -> int:
    """Save a dataset of input/output pairs. Returns version number."""
    registry = _get_registry()
    return registry.storage.save_dataset(name, items, metadata)


def load_dataset(name: str, version: int | None = None) -> list[dict]:
    """Load a dataset. Returns list of {input, expected, metadata} dicts."""
    registry = _get_registry()
    dataset = registry.storage.get_dataset(name, version)
    if dataset is None:
        raise ValueError(f"Dataset '{name}' not found")
    return dataset["items"]


def vote(
    name: str,
    response: str,
    score: int,
    message: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Record user feedback on an LLM response.

    Args:
        name: Prompt name (same as used in track()).
        response: The LLM response text the user is voting on.
        score: +1 for upvote, -1 for downvote.
        message: Optional user comment explaining the vote.
        metadata: Optional dict (user_id, query, etc.).

    Returns:
        The vote ID.
    """
    if score not in (1, -1):
        raise ValueError(f"score must be +1 or -1, got {score}")

    registry = _get_registry()
    storage = registry.storage

    # look up latest prompt version for this name
    prompt = storage.get_prompt(name)
    prompt_version = prompt.version if prompt else None

    return storage.save_vote(
        prompt_name=name,
        response=response,
        score=score,
        prompt_version=prompt_version,
        message=message,
        metadata=metadata,
    )
