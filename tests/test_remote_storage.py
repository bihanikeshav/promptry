"""Tests for the RemoteStorage dual-write backend.

Mocks the HTTP endpoint and verifies that:
- Local SQLite reads/writes work as normal
- Events are batched and shipped to the remote endpoint
- Failed POSTs are retried
- Queue overflow is handled gracefully
"""
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch, MagicMock

import pytest

from promptry.config import reset_config
from promptry.storage import reset_storage
from promptry.storage.remote import RemoteStorage, TelemetryEvent


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
    reset_config()
    reset_storage()
    yield
    reset_storage()
    reset_config()


class IngestHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that collects POSTed events."""
    received: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        IngestHandler.received.append(body)
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # silence request logs


@pytest.fixture
def ingest_server():
    """Start a local HTTP server that captures POSTed events."""
    IngestHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), IngestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", IngestHandler.received
    server.shutdown()


class TestRemoteStorageLocal:
    """Verify that local reads/writes still work."""

    def test_save_and_read_prompt(self, ingest_server):
        endpoint, _ = ingest_server
        storage = RemoteStorage(endpoint=endpoint, flush_interval=0.1)
        try:
            record = storage.save_prompt("test", "hello world", "abc123")
            assert record.name == "test"
            assert record.version == 1

            fetched = storage.get_prompt("test")
            assert fetched is not None
            assert fetched.content == "hello world"
        finally:
            storage.close()

    def test_list_prompts(self, ingest_server):
        endpoint, _ = ingest_server
        storage = RemoteStorage(endpoint=endpoint, flush_interval=0.1)
        try:
            storage.save_prompt("a", "content a", "hash_a")
            storage.save_prompt("b", "content b", "hash_b")
            prompts = storage.list_prompts()
            names = [p.name for p in prompts]
            assert "a" in names
            assert "b" in names
        finally:
            storage.close()

    def test_eval_run_and_results(self, ingest_server):
        endpoint, _ = ingest_server
        storage = RemoteStorage(endpoint=endpoint, flush_interval=0.1)
        try:
            run_id = storage.save_eval_run("suite1", overall_score=0.9)
            assert run_id >= 1

            storage.save_eval_result(
                run_id, "test1", "semantic", True, score=0.9
            )
            results = storage.get_eval_results(run_id)
            assert len(results) == 1
            assert results[0].test_name == "test1"
        finally:
            storage.close()

    def test_tag_prompt(self, ingest_server):
        endpoint, _ = ingest_server
        storage = RemoteStorage(endpoint=endpoint, flush_interval=0.1)
        try:
            record = storage.save_prompt("test", "content", "hash1")
            storage.tag_prompt(record.id, "prod")
            tags = storage.get_tags(record.id)
            assert "prod" in tags
        finally:
            storage.close()


class TestRemoteShipping:
    """Verify that events get shipped to the remote endpoint."""

    def test_prompt_save_ships_event(self, ingest_server):
        endpoint, received = ingest_server
        storage = RemoteStorage(
            endpoint=endpoint, flush_interval=0.2, batch_size=1,
        )
        try:
            storage.save_prompt("rag-qa", "You are helpful", "abc123")
            time.sleep(0.5)

            assert len(received) >= 1
            events = received[0]["events"]
            assert events[0]["type"] == "prompt_save"
            assert events[0]["data"]["name"] == "rag-qa"
        finally:
            storage.close()

    def test_batches_multiple_events(self, ingest_server):
        endpoint, received = ingest_server
        storage = RemoteStorage(
            endpoint=endpoint, flush_interval=0.2, batch_size=3,
        )
        try:
            storage.save_prompt("a", "content a", "hash_a")
            storage.save_prompt("b", "content b", "hash_b")
            storage.save_prompt("c", "content c", "hash_c")
            time.sleep(0.5)

            # all 3 should be in a single batch
            assert len(received) >= 1
            total_events = sum(len(r["events"]) for r in received)
            assert total_events == 3
        finally:
            storage.close()

    def test_ships_eval_events(self, ingest_server):
        endpoint, received = ingest_server
        storage = RemoteStorage(
            endpoint=endpoint, flush_interval=0.2, batch_size=5,
        )
        try:
            run_id = storage.save_eval_run("suite1", overall_score=0.9)
            storage.save_eval_result(
                run_id, "test1", "semantic", True, score=0.85,
            )
            time.sleep(0.5)

            all_events = []
            for r in received:
                all_events.extend(r["events"])
            types = [e["type"] for e in all_events]
            assert "eval_run" in types
            assert "eval_result" in types
        finally:
            storage.close()

    def test_ships_tag_event(self, ingest_server):
        endpoint, received = ingest_server
        storage = RemoteStorage(
            endpoint=endpoint, flush_interval=0.2, batch_size=5,
        )
        try:
            record = storage.save_prompt("test", "content", "hash1")
            storage.tag_prompt(record.id, "prod")
            time.sleep(0.5)

            all_events = []
            for r in received:
                all_events.extend(r["events"])
            types = [e["type"] for e in all_events]
            assert "prompt_tag" in types
        finally:
            storage.close()

    def test_includes_api_key_header(self, ingest_server):
        endpoint, _ = ingest_server

        # monkey-patch the handler to capture headers
        captured_headers = []
        original_do_post = IngestHandler.do_POST

        def capturing_do_post(self):
            captured_headers.append(dict(self.headers))
            original_do_post(self)

        IngestHandler.do_POST = capturing_do_post
        try:
            storage = RemoteStorage(
                endpoint=endpoint, api_key="pk_test123",
                flush_interval=0.2, batch_size=1,
            )
            try:
                storage.save_prompt("test", "content", "hash1")
                time.sleep(0.5)
                assert len(captured_headers) >= 1
                assert captured_headers[0].get("Authorization") == "Bearer pk_test123"
            finally:
                storage.close()
        finally:
            IngestHandler.do_POST = original_do_post

    def test_flush_on_close(self, ingest_server):
        endpoint, received = ingest_server
        storage = RemoteStorage(
            endpoint=endpoint, flush_interval=60.0, batch_size=100,
        )
        # large flush_interval so nothing ships automatically
        storage.save_prompt("test", "content", "hash1")
        assert len(received) == 0
        storage.close()
        # close should flush remaining events
        assert len(received) >= 1


class TestRemoteErrorHandling:

    def test_queue_full_does_not_crash(self, ingest_server):
        endpoint, _ = ingest_server
        storage = RemoteStorage(
            endpoint=endpoint, flush_interval=60.0,
            batch_size=100, max_queue=2,
        )
        try:
            # fill the queue — should not raise
            for i in range(10):
                storage.save_prompt(f"p{i}", f"content{i}", f"hash{i}")
        finally:
            storage.close()

    def test_unreachable_endpoint_does_not_block(self):
        storage = RemoteStorage(
            endpoint="http://127.0.0.1:1",  # nothing listens here
            flush_interval=0.1, batch_size=1, max_retries=1,
        )
        try:
            # should still work locally even if remote is down
            record = storage.save_prompt("test", "content", "hash1")
            assert record.name == "test"
            fetched = storage.get_prompt("test")
            assert fetched is not None
        finally:
            storage.close()


class TestTelemetryEvent:

    def test_auto_timestamp(self):
        event = TelemetryEvent(event_type="test", data={"key": "val"})
        assert event.timestamp != ""
        assert "T" in event.timestamp  # ISO format

    def test_explicit_timestamp(self):
        event = TelemetryEvent(
            event_type="test", data={}, timestamp="2026-01-01T00:00:00Z",
        )
        assert event.timestamp == "2026-01-01T00:00:00Z"
