"""Async write queue for production use.

Wraps any BaseStorage with a background thread that drains writes.
The calling code (track(), track_context()) never blocks on I/O.

Three modes:
  - sync:  writes happen inline (default, good for dev/testing)
  - async: writes are queued and flushed by a daemon thread
  - off:   no writes at all, track() is pure passthrough
"""
from __future__ import annotations

import atexit
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any

from promptry.storage.base import BaseStorage

log = logging.getLogger(__name__)

# sentinel value to tell the writer thread to stop
_STOP = object()


@dataclass
class WriteOp:
    """A queued write operation."""
    method: str
    args: tuple
    kwargs: dict[str, Any]


class AsyncWriter:
    """Wraps a storage backend with a background write queue.

    All read methods go straight to the underlying storage.
    Write methods (save_prompt, save_eval_run, etc.) get queued
    and processed by a single background thread.
    """

    def __init__(self, storage: BaseStorage, max_queue: int = 10000):
        self._storage = storage
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._thread = threading.Thread(
            target=self._drain,
            name="promptry-writer",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.flush)

    def _drain(self):
        """Process writes until we get the stop sentinel."""
        while True:
            op = self._queue.get()
            if op is _STOP:
                self._queue.task_done()
                break
            try:
                method = getattr(self._storage, op.method)
                method(*op.args, **op.kwargs)
            except Exception:
                log.exception("async write failed: %s", op.method)
            finally:
                self._queue.task_done()

    def _enqueue(self, method: str, *args, **kwargs):
        try:
            self._queue.put_nowait(WriteOp(method, args, kwargs))
        except queue.Full:
            log.warning("write queue full, dropping %s", method)

    def flush(self, timeout: float = 5.0):
        """Wait for all pending writes to finish."""
        self._queue.put(_STOP)
        self._thread.join(timeout=timeout)
        # restart the thread for future writes
        if not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._drain,
                name="promptry-writer",
                daemon=True,
            )
            self._thread.start()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    # ---- write methods (queued) ----

    def save_prompt(self, name, content, content_hash, metadata=None):
        self._enqueue("save_prompt", name, content, content_hash, metadata)
        # can't return the PromptRecord from the queue, so callers that
        # need it should use sync mode. async mode is for fire-and-forget.
        return None

    def save_eval_run(self, **kwargs):
        self._enqueue("save_eval_run", **kwargs)
        return None

    def save_eval_result(self, **kwargs):
        self._enqueue("save_eval_result", **kwargs)
        return None

    def tag_prompt(self, prompt_id, tag):
        self._enqueue("tag_prompt", prompt_id, tag)

    # ---- read methods (direct passthrough) ----

    def get_prompt(self, name, version=None):
        return self._storage.get_prompt(name, version)

    def get_prompt_by_tag(self, name, tag):
        return self._storage.get_prompt_by_tag(name, tag)

    def list_prompts(self, name=None):
        return self._storage.list_prompts(name)

    def get_tags(self, prompt_id):
        return self._storage.get_tags(prompt_id)

    def get_eval_runs(self, suite_name, limit=50):
        return self._storage.get_eval_runs(suite_name, limit)

    def get_eval_results(self, run_id):
        return self._storage.get_eval_results(run_id)

    def get_score_history(self, suite_name, limit=30):
        return self._storage.get_score_history(suite_name, limit)

    def close(self):
        self.flush()
        self._storage.close()
