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
import time
from dataclasses import dataclass
from typing import Any

from promptry.storage.base import BaseStorage

log = logging.getLogger(__name__)


@dataclass
class WriteOp:
    """A queued write operation."""
    method: str
    args: tuple
    kwargs: dict[str, Any]


class AsyncWriter(BaseStorage):
    """Wraps a storage backend with a background write queue.

    All read methods go straight to the underlying storage.
    Write methods (save_eval_run, save_eval_result, tag_prompt) get queued
    and processed by a single background thread.

    save_prompt is synchronous even in async mode because callers need the
    returned PromptRecord (version number, id). The dedup check makes it
    fast anyway (no write on duplicate content).
    """

    def __init__(self, storage: BaseStorage, max_queue: int = 10000):
        self._storage = storage
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(
            target=self._drain,
            name="promptry-writer",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.flush)

    def _drain(self):
        """Process writes until stopped."""
        while self._running or not self._queue.empty():
            try:
                op = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                method = getattr(self._storage, op.method)
                method(*op.args, **op.kwargs)
            except Exception:
                log.exception("async write failed: %s", op.method)
            finally:
                self._queue.task_done()

    def _enqueue(self, method: str, *args, **kwargs):
        try:
            self._queue.put(WriteOp(method, args, kwargs), timeout=1.0)
        except queue.Full:
            log.warning(
                "write queue full, dropping %s — increase max_queue or check for slowdowns",
                method,
            )

    def flush(self, timeout: float = 5.0):
        """Wait for all pending writes to finish, with timeout."""
        deadline = time.monotonic() + timeout
        while not self._queue.empty():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                log.warning("flush timed out with %d writes pending", self._queue.qsize())
                return
            time.sleep(min(0.05, remaining))

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    # ---- write methods ----

    def save_prompt(self, name, content, content_hash, metadata=None):
        # synchronous -- callers need the returned PromptRecord
        return self._storage.save_prompt(name, content, content_hash, metadata)

    def save_eval_run(self, **kwargs):
        # synchronous -- callers need the returned run_id
        return self._storage.save_eval_run(**kwargs)

    def save_eval_result(self, **kwargs):
        self._enqueue("save_eval_result", **kwargs)

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
        self._running = False
        self.flush()
        self._thread.join(timeout=2.0)
        self._storage.close()
