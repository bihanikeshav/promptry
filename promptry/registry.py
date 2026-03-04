"""Prompt registry -- versioning, hashing, and diffing.

The main thing users care about is track(). Stick it in your pipeline,
it handles the rest.
"""
from __future__ import annotations

import difflib
import hashlib
import random
from pathlib import Path

from promptry.models import PromptRecord
from promptry.storage import Storage


class PromptRegistry:

    def __init__(self, storage: Storage | None = None):
        self._storage = storage or Storage()
        self._hash_cache: dict[str, str] = {}

    @property
    def storage(self) -> Storage:
        return self._storage

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def save(self, name, content, tag=None, metadata=None) -> PromptRecord:
        """Save a new version. Skips if identical content already exists."""
        h = self.content_hash(content)
        record = self._storage.save_prompt(name, content, h, metadata)
        self._hash_cache[f"{name}:{h}"] = f"{name}@v{record.version}"

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

    def load_from_file(self, file_path: Path) -> str:
        return Path(file_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# track() -- the main integration point
#
# One line in your existing code. Returns the prompt string unchanged.
# Under the hood it versions the content by SHA-256 hash.
# Repeated calls with the same content are a no-op (in-memory cache).
# ---------------------------------------------------------------------------

_default_registry: PromptRegistry | None = None
_track_cache: set[str] = set()  # "name:hash" for the fast path


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

    if cache_key in _track_cache and tag is None:
        return content

    registry = _get_registry()
    registry.save(name=name, content=content, tag=tag, metadata=metadata)
    _track_cache.add(cache_key)

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

    if cache_key in _track_cache:
        return chunks

    registry = _get_registry()
    meta = metadata or {}
    meta["chunk_count"] = len(chunks)
    registry.save(name=context_name, content=joined, metadata=meta)
    _track_cache.add(cache_key)

    return chunks
