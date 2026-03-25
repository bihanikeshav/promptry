"""Tests for the dashboard FastAPI server."""
import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from promptry.storage.sqlite import SQLiteStorage


def _seed_suite(storage, suite_name, scores, model="gpt-4o", prompt_version=1):
    """Seed eval runs and results for a suite."""
    for score in scores:
        run_id = storage.save_eval_run(
            suite_name=suite_name,
            model_version=model,
            prompt_name="test-prompt",
            prompt_version=prompt_version,
            overall_pass=score >= 0.7,
            overall_score=score,
        )
        storage.save_eval_result(
            run_id=run_id,
            test_name="test_main",
            assertion_type="semantic",
            passed=score >= 0.7,
            score=score,
        )
    return run_id  # return last run_id


def _seed_prompt(storage, name, contents):
    """Seed prompt versions."""
    import hashlib

    records = []
    for content in contents:
        h = hashlib.sha256(content.encode()).hexdigest()[:16]
        record = storage.save_prompt(name=name, content=content, content_hash=h)
        records.append(record)
    return records


@pytest.fixture
def storage(tmp_path):
    db = SQLiteStorage(db_path=tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def client(storage):
    import promptry.dashboard.server as srv

    original = srv.get_storage
    srv.get_storage = lambda: storage
    from promptry.dashboard.server import app

    with TestClient(app) as c:
        yield c
    srv.get_storage = original


# ---- Health ----

class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "db_path" in data


# ---- Suites ----

class TestSuites:
    def test_suites_empty(self, client):
        resp = client.get("/api/suites")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_suites_with_data(self, client, storage):
        _seed_suite(storage, "qa-suite", [0.8, 0.85, 0.9])
        resp = client.get("/api/suites")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        s = data[0]
        assert s["name"] == "qa-suite"
        assert s["latest_score"] == pytest.approx(0.9)
        assert s["passed"] is True
        assert "drift_status" in s
        assert "drift_slope" in s
        assert s["model_version"] == "gpt-4o"
        assert s["prompt_version"] == 1
        assert "timestamp" in s
        assert "sparkline_scores" in s
        # sparkline should be oldest-first
        assert len(s["sparkline_scores"]) == 3


# ---- Suite Runs ----

class TestSuiteRuns:
    def test_suite_runs(self, client, storage):
        _seed_suite(storage, "qa-suite", [0.8, 0.85])
        resp = client.get("/api/suite/qa-suite/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # newest first
        assert data[0]["overall_score"] == pytest.approx(0.85)

    def test_suite_runs_with_limit(self, client, storage):
        _seed_suite(storage, "qa-suite", [0.7, 0.75, 0.8, 0.85])
        resp = client.get("/api/suite/qa-suite/runs?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


# ---- Run Detail ----

class TestRunDetail:
    def test_run_detail(self, client, storage):
        run_id = _seed_suite(storage, "qa-suite", [0.9])
        resp = client.get(f"/api/suite/qa-suite/run/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["suite_name"] == "qa-suite"
        assert len(data["assertions"]) == 1
        assert data["assertions"][0]["test_name"] == "test_main"

    def test_run_detail_wrong_suite(self, client, storage):
        run_id = _seed_suite(storage, "qa-suite", [0.9])
        resp = client.get(f"/api/suite/other-suite/run/{run_id}")
        assert resp.status_code == 404

    def test_run_detail_nonexistent(self, client, storage):
        resp = client.get("/api/suite/qa-suite/run/9999")
        assert resp.status_code == 404


# ---- Prompts ----

class TestPromptsList:
    def test_prompts_empty(self, client):
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_prompts_with_data(self, client, storage):
        _seed_prompt(storage, "summarizer", ["v1 content", "v2 content"])
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "summarizer"
        assert data[0]["latest_version"] == 2


class TestPromptVersions:
    def test_prompt_versions(self, client, storage):
        records = _seed_prompt(storage, "summarizer", ["v1", "v2", "v3"])
        resp = client.get("/api/prompts/summarizer")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) == 3

    def test_prompt_versions_not_found(self, client):
        resp = client.get("/api/prompts/nonexistent")
        assert resp.status_code == 404


class TestPromptContent:
    def test_prompt_content(self, client, storage):
        _seed_prompt(storage, "summarizer", ["v1 content", "v2 content"])
        resp = client.get("/api/prompts/summarizer/content?v=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "v1 content"
        assert data["version"] == 1

    def test_prompt_content_latest(self, client, storage):
        _seed_prompt(storage, "summarizer", ["v1 content", "v2 content"])
        resp = client.get("/api/prompts/summarizer/content")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "v2 content"

    def test_prompt_content_not_found(self, client):
        resp = client.get("/api/prompts/nonexistent/content")
        assert resp.status_code == 404


class TestPromptDiff:
    def test_prompt_diff(self, client, storage):
        _seed_prompt(storage, "summarizer", [
            "line1\nline2\nline3",
            "line1\nmodified\nline3\nline4",
        ])
        resp = client.get("/api/prompts/summarizer/diff?v1=1&v2=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "additions" in data
        assert "deletions" in data
        assert "lines" in data
        assert data["additions"] >= 1
        assert data["deletions"] >= 1
        # Check line types
        types = {line["type"] for line in data["lines"]}
        assert "unchanged" in types or "added" in types or "deleted" in types


# ---- Models ----

class TestModelVersions:
    def test_model_versions(self, client, storage):
        _seed_suite(storage, "qa-suite", [0.8, 0.85], model="gpt-4o")
        _seed_suite(storage, "qa-suite", [0.9], model="claude-sonnet")
        resp = client.get("/api/models/qa-suite")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) == 2
        models = {v["model_version"] for v in data["versions"]}
        assert "gpt-4o" in models
        assert "claude-sonnet" in models


class TestModelCompare:
    def test_model_compare(self, client, storage):
        _seed_suite(storage, "qa-suite", [0.8, 0.82, 0.85, 0.83, 0.84], model="gpt-4o")
        _seed_suite(storage, "qa-suite", [0.9], model="claude-sonnet")
        resp = client.get(
            "/api/models/qa-suite/compare?baseline=gpt-4o&candidate=claude-sonnet"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["suite_name"] == "qa-suite"
        assert data["baseline"]["model_version"] == "gpt-4o"
        assert data["candidate"]["model_version"] == "claude-sonnet"
        assert "verdict" in data
        assert "overall_delta" in data


# ---- Cost ----

class TestCost:
    def test_cost_empty(self, client):
        resp = client.get("/api/cost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_calls"] == 0

    def test_cost_with_data(self, client, storage):
        # Save prompts with cost metadata
        import json
        import hashlib

        for i in range(3):
            content = f"prompt content {i}"
            h = hashlib.sha256(content.encode()).hexdigest()[:16]
            storage.save_prompt(
                name="cost-prompt",
                content=content,
                content_hash=h,
                metadata={"model": "gpt-4o", "cost": 0.05, "tokens_in": 100, "tokens_out": 50},
            )

        resp = client.get("/api/cost?days=7&name=cost-prompt&model=gpt-4o")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_calls"] == 3
        assert data["summary"]["total_cost"] == pytest.approx(0.15)
