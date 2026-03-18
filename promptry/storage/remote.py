"""Remote telemetry storage backend.

Dual-write: all data goes to local SQLite (for reads/evals) AND gets
batched and shipped to a remote endpoint (for centralized collection).

Configure in promptry.toml:
    [storage]
    mode = "remote"
    endpoint = "https://your-server.com/ingest"
    api_key = "pk_..."

The JS client (promptry on npm) uses the same event format and endpoint,
so both Python and JS telemetry land in the same place.
"""
from __future__ import annotations

import atexit
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

from promptry.storage.base import BaseStorage
from promptry.storage.sqlite import SQLiteStorage
from promptry.models import PromptRecord

log = logging.getLogger(__name__)


@dataclass
class TelemetryEvent:
    """A single event to ship to the remote endpoint."""
    event_type: str
    data: dict[str, Any]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class RemoteStorage(BaseStorage):
    """Dual-write storage: local SQLite + remote HTTP endpoint.

    All reads go to local SQLite. All writes go to both local SQLite
    and a batched queue that ships events to the remote endpoint.

    If the remote endpoint is unreachable, events are retried with
    backoff. Local storage always works regardless of network state.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str = "",
        batch_size: int = 10,
        flush_interval: float = 5.0,
        max_queue: int = 10000,
        max_retries: int = 3,
    ):
        self._local = SQLiteStorage()
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_retries = max_retries
        self._queue: queue.Queue[TelemetryEvent] = queue.Queue(maxsize=max_queue)
        self._running = True
        self._thread = threading.Thread(
            target=self._flush_loop,
            name="promptry-remote",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.flush)

    def _flush_loop(self):
        """Batch events and ship them periodically."""
        while self._running:
            batch: list[TelemetryEvent] = []
            deadline = time.monotonic() + self._flush_interval

            while len(batch) < self._batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    event = self._queue.get(timeout=min(remaining, 0.5))
                    batch.append(event)
                    self._queue.task_done()
                except queue.Empty:
                    continue

            if batch:
                self._ship_batch(batch)

        # drain remaining on shutdown
        batch = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
                self._queue.task_done()
            except queue.Empty:
                break
        if batch:
            self._ship_batch(batch)

    def _ship_batch(self, batch: list[TelemetryEvent]):
        """POST a batch of events to the remote endpoint."""
        payload = json.dumps({
            "events": [
                {"type": e.event_type, "data": e.data, "timestamp": e.timestamp}
                for e in batch
            ]
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        for attempt in range(self._max_retries):
            try:
                req = Request(
                    self._endpoint,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                with urlopen(req, timeout=10) as resp:
                    if resp.status < 300:
                        return
                    log.warning("remote ingest returned %d", resp.status)
            except (URLError, OSError) as exc:
                if attempt < self._max_retries - 1:
                    time.sleep(min(2 ** attempt, 10))
                else:
                    log.warning(
                        "failed to ship %d events after %d retries: %s",
                        len(batch), self._max_retries, exc,
                    )

    def _emit(self, event_type: str, data: dict):
        """Queue a telemetry event for remote shipping."""
        try:
            self._queue.put_nowait(TelemetryEvent(event_type=event_type, data=data))
        except queue.Full:
            log.warning("telemetry queue full, dropping %s event", event_type)

    def flush(self, timeout: float = 10.0):
        """Wait for all queued events to be shipped."""
        deadline = time.monotonic() + timeout
        while not self._queue.empty():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                log.warning("flush timed out with %d events pending", self._queue.qsize())
                return
            time.sleep(min(0.05, remaining))

    @property
    def pending(self) -> int:
        """Number of events waiting to be shipped."""
        return self._queue.qsize()

    # ---- write methods (dual-write: local + remote) ----

    def save_prompt(self, name, content, content_hash, metadata=None) -> PromptRecord:
        record = self._local.save_prompt(name, content, content_hash, metadata)
        self._emit("prompt_save", {
            "name": record.name,
            "version": record.version,
            "content": record.content,
            "hash": record.hash,
            "metadata": record.metadata,
            "created_at": record.created_at,
        })
        return record

    def save_eval_run(
        self, suite_name, prompt_name=None, prompt_version=None,
        model_version=None, overall_pass=True, overall_score=None,
    ) -> int:
        run_id = self._local.save_eval_run(
            suite_name, prompt_name, prompt_version,
            model_version, overall_pass, overall_score,
        )
        self._emit("eval_run", {
            "run_id": run_id,
            "suite_name": suite_name,
            "prompt_name": prompt_name,
            "prompt_version": prompt_version,
            "model_version": model_version,
            "overall_pass": overall_pass,
            "overall_score": overall_score,
        })
        return run_id

    def save_eval_result(
        self, run_id, test_name, assertion_type, passed,
        score=None, details=None, latency_ms=None,
    ) -> int:
        result_id = self._local.save_eval_result(
            run_id, test_name, assertion_type, passed,
            score, details, latency_ms,
        )
        self._emit("eval_result", {
            "run_id": run_id,
            "test_name": test_name,
            "assertion_type": assertion_type,
            "passed": passed,
            "score": score,
            "details": details,
            "latency_ms": latency_ms,
        })
        return result_id

    def tag_prompt(self, prompt_id, tag):
        self._local.tag_prompt(prompt_id, tag)
        self._emit("prompt_tag", {"prompt_id": prompt_id, "tag": tag})

    # ---- read methods (local SQLite passthrough) ----

    def get_prompt(self, name, version=None):
        return self._local.get_prompt(name, version)

    def get_prompt_by_tag(self, name, tag):
        return self._local.get_prompt_by_tag(name, tag)

    def list_prompts(self, name=None):
        return self._local.list_prompts(name)

    def get_tags(self, prompt_id):
        return self._local.get_tags(prompt_id)

    def get_eval_runs(self, suite_name, limit=50):
        return self._local.get_eval_runs(suite_name, limit)

    def get_eval_results(self, run_id):
        return self._local.get_eval_results(run_id)

    def get_score_history(self, suite_name, limit=30):
        return self._local.get_score_history(suite_name, limit)

    def close(self):
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=self._flush_interval + 2)
        self._local.close()
