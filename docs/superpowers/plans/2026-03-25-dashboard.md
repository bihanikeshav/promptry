# promptry Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web dashboard for promptry that visualizes eval history, prompt diffs, model comparisons, and cost data — served by `promptry dashboard`.

**Architecture:** FastAPI backend reads from existing SQLite storage, serves a REST JSON API. React+Vite SPA hosted at promptry.meownikov.xyz (primary) with a bundled local fallback. GitHub Dark monospace theme, Sentry-style drill-down navigation.

**Tech Stack:** Python (FastAPI, uvicorn), React 18, Vite, TypeScript, recharts, react-router-dom v6.

**Spec:** `docs/superpowers/specs/2026-03-25-dashboard-design.md`

---

## File Structure

### Backend (Python)

| File | Action | Responsibility |
|------|--------|----------------|
| `promptry/storage/base.py` | Modify | Add 3 abstract methods |
| `promptry/storage/sqlite.py` | Modify | Implement 3 new query methods |
| `promptry/storage/remote.py` | Modify | Add 3 passthroughs to `_local` |
| `promptry/writer.py` | Modify | Add 3 passthroughs to `_storage` |
| `promptry/dashboard/__init__.py` | Create | Empty |
| `promptry/dashboard/server.py` | Create | FastAPI app, all API routes, CORS, static serving |
| `promptry/cli.py` | Modify | Add `dashboard` command |
| `pyproject.toml` | Modify | Add `[dashboard]` optional dependency, package-data |
| `tests/test_storage.py` | Modify | Tests for 3 new storage methods |
| `tests/test_dashboard_api.py` | Create | Tests for all API endpoints |

### Frontend (TypeScript/React)

| File | Action | Responsibility |
|------|--------|----------------|
| `dashboard-ui/package.json` | Create | Dependencies, scripts |
| `dashboard-ui/tsconfig.json` | Create | TypeScript config |
| `dashboard-ui/vite.config.ts` | Create | Build output → `../promptry/dashboard/static/` |
| `dashboard-ui/index.html` | Create | SPA entry point |
| `dashboard-ui/src/main.tsx` | Create | React root mount |
| `dashboard-ui/src/App.tsx` | Create | Router setup |
| `dashboard-ui/src/theme.ts` | Create | GitHub Dark color tokens |
| `dashboard-ui/src/api/client.ts` | Create | Fetch wrapper, port discovery |
| `dashboard-ui/src/api/types.ts` | Create | TypeScript interfaces for API responses |
| `dashboard-ui/src/components/Breadcrumb.tsx` | Create | Navigation breadcrumb |
| `dashboard-ui/src/components/Sparkline.tsx` | Create | Inline SVG sparkline |
| `dashboard-ui/src/components/ScoreChart.tsx` | Create | Recharts line chart |
| `dashboard-ui/src/components/AssertionBar.tsx` | Create | Horizontal score bar |
| `dashboard-ui/src/components/DiffView.tsx` | Create | Git-diff renderer |
| `dashboard-ui/src/components/ClaimBreakdown.tsx` | Create | Grounded assertion detail |
| `dashboard-ui/src/components/Layout.tsx` | Create | Top nav + breadcrumb shell |
| `dashboard-ui/src/pages/Overview.tsx` | Create | Suite list with sparklines |
| `dashboard-ui/src/pages/SuiteDetail.tsx` | Create | Score chart, assertions, runs table |
| `dashboard-ui/src/pages/RunDetail.tsx` | Create | Per-assertion breakdown, expandable details |
| `dashboard-ui/src/pages/Prompts.tsx` | Create | Prompt list |
| `dashboard-ui/src/pages/PromptDetail.tsx` | Create | Version sidebar + diff view |
| `dashboard-ui/src/pages/Models.tsx` | Create | Model comparison report |
| `dashboard-ui/src/pages/Cost.tsx` | Create | Cost charts and tables |

---

## Task 1: Storage Layer — New Query Methods

**Files:**
- Modify: `promptry/storage/base.py`
- Modify: `promptry/storage/sqlite.py`
- Modify: `promptry/storage/remote.py`
- Modify: `promptry/writer.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests for new storage methods**

Add to `tests/test_storage.py`:

```python
class TestSuiteNames:

    def test_list_suite_names_empty(self, storage):
        assert storage.list_suite_names() == []

    def test_list_suite_names(self, storage):
        storage.save_eval_run(suite_name="alpha", overall_pass=True, overall_score=0.9)
        storage.save_eval_run(suite_name="beta", overall_pass=True, overall_score=0.8)
        storage.save_eval_run(suite_name="alpha", overall_pass=True, overall_score=0.85)
        names = storage.list_suite_names()
        assert sorted(names) == ["alpha", "beta"]


class TestGetRunById:

    def test_get_existing_run(self, storage):
        run_id = storage.save_eval_run(suite_name="test", overall_pass=True, overall_score=0.9)
        run = storage.get_eval_run_by_id(run_id)
        assert run is not None
        assert run.id == run_id
        assert run.suite_name == "test"

    def test_get_nonexistent_run(self, storage):
        assert storage.get_eval_run_by_id(9999) is None


class TestGetCostData:

    def test_cost_data_empty(self, storage):
        result = storage.get_cost_data(days=7)
        assert result["summary"]["total_calls"] == 0
        assert result["by_name"] == []

    def test_cost_data_with_metadata(self, storage):
        storage.save_prompt(
            name="my-prompt", content="test", content_hash="h1",
            metadata={"tokens_in": 500, "tokens_out": 100, "model": "gpt-4o", "cost": 0.005},
        )
        storage.save_prompt(
            name="my-prompt", content="test2", content_hash="h2",
            metadata={"tokens_in": 300, "tokens_out": 50, "model": "gpt-4o", "cost": 0.003},
        )
        result = storage.get_cost_data(days=7)
        assert result["summary"]["total_calls"] == 2
        assert result["summary"]["total_cost"] == pytest.approx(0.008)
        assert len(result["by_name"]) == 1
        assert result["by_name"][0]["name"] == "my-prompt"
        assert result["by_name"][0]["tokens_in"] == 800

    def test_cost_data_filter_by_name(self, storage):
        storage.save_prompt(name="a", content="x", content_hash="h1", metadata={"cost": 0.01})
        storage.save_prompt(name="b", content="y", content_hash="h2", metadata={"cost": 0.02})
        result = storage.get_cost_data(days=7, name="a")
        assert len(result["by_name"]) == 1
        assert result["by_name"][0]["name"] == "a"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py::TestSuiteNames tests/test_storage.py::TestGetRunById tests/test_storage.py::TestGetCostData -v`
Expected: FAIL — methods not defined.

- [ ] **Step 3: Add abstract methods to BaseStorage**

In `promptry/storage/base.py`, add before `def close()`:

```python
@abstractmethod
def list_suite_names(self) -> list[str]:
    ...

@abstractmethod
def get_eval_run_by_id(self, run_id: int):
    ...

@abstractmethod
def get_cost_data(self, days: int = 7, name: str | None = None, model: str | None = None) -> dict:
    ...
```

- [ ] **Step 4: Implement in SQLiteStorage**

In `promptry/storage/sqlite.py`, add before `get_score_history`:

```python
def list_suite_names(self) -> list[str]:
    with self._lock:
        cur = self._conn.execute(
            "SELECT DISTINCT suite_name FROM eval_runs ORDER BY suite_name"
        )
        return [row[0] for row in cur.fetchall()]

def get_eval_run_by_id(self, run_id: int):
    with self._lock:
        cur = self._conn.execute(
            "SELECT * FROM eval_runs WHERE id = ?", (run_id,)
        )
        row = cur.fetchone()
        return self._row_to_eval_run(row) if row else None

def get_cost_data(self, days: int = 7, name: str | None = None, model: str | None = None) -> dict:
    import json as _json
    from collections import defaultdict

    with self._lock:
        query = """
            SELECT name, metadata, created_at FROM prompts
            WHERE metadata IS NOT NULL
              AND created_at >= datetime('now', ?)
        """
        params: list = [f"-{days} days"]
        if name:
            query += " AND name = ?"
            params.append(name)
        query += " ORDER BY created_at ASC"
        cur = self._conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()

    by_name: dict[str, dict] = defaultdict(lambda: {
        "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0, "models": set(),
    })
    by_date: dict[str, dict] = defaultdict(lambda: {
        "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0,
    })

    for row in rows:
        try:
            meta = _json.loads(row["metadata"])
        except (TypeError, _json.JSONDecodeError):
            continue
        if not isinstance(meta, dict):
            continue
        has_info = any(k in meta for k in ("tokens_in", "tokens_out", "cost", "input_tokens", "output_tokens"))
        if not has_info:
            continue

        tokens_in = meta.get("tokens_in", 0) or meta.get("input_tokens", 0) or 0
        tokens_out = meta.get("tokens_out", 0) or meta.get("output_tokens", 0) or 0
        cost = meta.get("cost", 0.0) or 0.0
        model_name = meta.get("model", "")

        if model and model_name and model.lower() not in model_name.lower():
            continue

        pname = row["name"]
        date_str = row["created_at"][:10]

        by_name[pname]["tokens_in"] += tokens_in
        by_name[pname]["tokens_out"] += tokens_out
        by_name[pname]["cost"] += cost
        by_name[pname]["calls"] += 1
        if model_name:
            by_name[pname]["models"].add(model_name)

        by_date[date_str]["tokens_in"] += tokens_in
        by_date[date_str]["tokens_out"] += tokens_out
        by_date[date_str]["cost"] += cost
        by_date[date_str]["calls"] += 1

    total_in = sum(v["tokens_in"] for v in by_name.values())
    total_out = sum(v["tokens_out"] for v in by_name.values())
    total_cost = sum(v["cost"] for v in by_name.values())
    total_calls = sum(v["calls"] for v in by_name.values())

    return {
        "summary": {
            "total_cost": total_cost,
            "total_calls": total_calls,
            "total_tokens_in": total_in,
            "total_tokens_out": total_out,
            "avg_cost": total_cost / total_calls if total_calls else 0.0,
        },
        "by_name": sorted([
            {"name": k, "calls": v["calls"], "tokens_in": v["tokens_in"],
             "tokens_out": v["tokens_out"], "cost": v["cost"],
             "models": sorted(v["models"])}
            for k, v in by_name.items()
        ], key=lambda x: x["cost"], reverse=True),
        "by_date": [
            {"date": k, **{dk: dv for dk, dv in v.items()}}
            for k, v in sorted(by_date.items())
        ],
    }
```

- [ ] **Step 5: Add passthroughs to RemoteStorage and AsyncWriter**

In `promptry/storage/remote.py`, add after `get_model_versions`:

```python
def list_suite_names(self):
    return self._local.list_suite_names()

def get_eval_run_by_id(self, run_id):
    return self._local.get_eval_run_by_id(run_id)

def get_cost_data(self, days=7, name=None, model=None):
    return self._local.get_cost_data(days, name, model)
```

In `promptry/writer.py`, add after `get_model_versions`:

```python
def list_suite_names(self):
    return self._storage.list_suite_names()

def get_eval_run_by_id(self, run_id):
    return self._storage.get_eval_run_by_id(run_id)

def get_cost_data(self, days=7, name=None, model=None):
    return self._storage.get_cost_data(days, name, model)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite for regressions**

Run: `pytest tests/ --ignore=tests/test_mcp_server.py -q`
Expected: ALL PASS (168+ tests)

- [ ] **Step 8: Commit**

```bash
git add promptry/storage/base.py promptry/storage/sqlite.py promptry/storage/remote.py promptry/writer.py tests/test_storage.py
git commit -m "feat(storage): add list_suite_names, get_eval_run_by_id, get_cost_data"
```

---

## Task 2: FastAPI Server — API Routes

**Files:**
- Create: `promptry/dashboard/__init__.py`
- Create: `promptry/dashboard/server.py`
- Create: `tests/test_dashboard_api.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dashboard optional dependency to pyproject.toml**

Add to `pyproject.toml` under `[project.optional-dependencies]`:

```toml
dashboard = [
    "fastapi>=0.100.0",
    "uvicorn>=0.20.0",
]
```

Add package-data for static files:

```toml
[tool.setuptools.package-data]
"promptry.dashboard" = ["static/**/*"]
```

- [ ] **Step 2: Create empty `promptry/dashboard/__init__.py`**

```python
```

- [ ] **Step 3: Write failing tests for API endpoints**

Create `tests/test_dashboard_api.py`:

```python
"""Tests for the dashboard API."""
import pytest
from unittest.mock import patch

# Skip all if fastapi not installed
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from promptry.storage.sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=tmp_path / "test.db")


@pytest.fixture
def client(storage):
    with patch("promptry.dashboard.server.get_storage", return_value=storage):
        from promptry.dashboard.server import app
        yield TestClient(app)


def _seed_suite(storage, suite_name, scores, model="gpt-4o", prompt_version=1):
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
            run_id=run_id, test_name="test_main",
            assertion_type="semantic", passed=score >= 0.7, score=score,
        )
    return run_id


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestSuites:
    def test_empty(self, client):
        resp = client.get("/api/suites")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_data(self, client, storage):
        _seed_suite(storage, "alpha", [0.85, 0.87, 0.89])
        _seed_suite(storage, "beta", [0.90])
        resp = client.get("/api/suites")
        data = resp.json()
        assert len(data) == 2
        names = [s["name"] for s in data]
        assert "alpha" in names
        assert "beta" in names
        alpha = next(s for s in data if s["name"] == "alpha")
        assert alpha["latest_score"] == pytest.approx(0.89)
        assert alpha["passed"] is True
        assert len(alpha["sparkline_scores"]) == 3


class TestSuiteRuns:
    def test_runs(self, client, storage):
        _seed_suite(storage, "test", [0.8, 0.9])
        resp = client.get("/api/suite/test/runs?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_not_found(self, client):
        resp = client.get("/api/suite/nonexistent/runs")
        assert resp.status_code == 200
        assert resp.json() == []


class TestRunDetail:
    def test_existing_run(self, client, storage):
        run_id = _seed_suite(storage, "test", [0.85])
        resp = client.get(f"/api/suite/test/run/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["overall_score"] == pytest.approx(0.85)
        assert len(data["assertions"]) == 1

    def test_wrong_suite(self, client, storage):
        run_id = _seed_suite(storage, "real-suite", [0.9])
        resp = client.get(f"/api/suite/wrong-suite/run/{run_id}")
        assert resp.status_code == 404

    def test_nonexistent(self, client):
        resp = client.get("/api/suite/test/run/9999")
        assert resp.status_code == 404


class TestPrompts:
    def test_list_empty(self, client):
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client, storage):
        storage.save_prompt(name="p1", content="hello", content_hash="h1")
        storage.save_prompt(name="p1", content="hello v2", content_hash="h2")
        resp = client.get("/api/prompts")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "p1"
        assert data[0]["latest_version"] == 2


class TestPromptContent:
    def test_get_content(self, client, storage):
        storage.save_prompt(name="p1", content="hello world", content_hash="h1")
        resp = client.get("/api/prompts/p1/content?v=1")
        assert resp.status_code == 200
        assert resp.json()["content"] == "hello world"

    def test_not_found(self, client):
        resp = client.get("/api/prompts/nonexistent/content?v=1")
        assert resp.status_code == 404


class TestPromptDiff:
    def test_diff(self, client, storage):
        storage.save_prompt(name="p1", content="line one\nline two", content_hash="h1")
        storage.save_prompt(name="p1", content="line one\nline changed", content_hash="h2")
        resp = client.get("/api/prompts/p1/diff?v1=1&v2=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["additions"] >= 1
        assert data["deletions"] >= 1
        types = [l["type"] for l in data["lines"]]
        assert "added" in types
        assert "deleted" in types


class TestModels:
    def test_versions(self, client, storage):
        _seed_suite(storage, "test", [0.8], model="gpt-4o")
        _seed_suite(storage, "test", [0.9], model="claude")
        resp = client.get("/api/models/test")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) == 2

    def test_compare(self, client, storage):
        _seed_suite(storage, "test", [0.8, 0.82, 0.84], model="gpt-4o")
        _seed_suite(storage, "test", [0.9], model="claude")
        resp = client.get("/api/models/test/compare?baseline=gpt-4o&candidate=claude")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] in ("switch", "comparable", "keep_baseline")


class TestCost:
    def test_empty(self, client):
        resp = client.get("/api/cost?days=7")
        assert resp.status_code == 200
        assert resp.json()["summary"]["total_calls"] == 0

    def test_with_data(self, client, storage):
        storage.save_prompt(
            name="p1", content="test", content_hash="h1",
            metadata={"tokens_in": 500, "tokens_out": 100, "cost": 0.005, "model": "gpt-4o"},
        )
        resp = client.get("/api/cost?days=7")
        data = resp.json()
        assert data["summary"]["total_calls"] == 1
        assert data["summary"]["total_cost"] == pytest.approx(0.005)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_api.py -v`
Expected: FAIL — `promptry.dashboard.server` does not exist.

- [ ] **Step 5: Implement the FastAPI server**

Create `promptry/dashboard/server.py`:

```python
"""FastAPI server for the promptry dashboard."""
from __future__ import annotations

import dataclasses
import difflib
import importlib.metadata
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from promptry.storage import get_storage

app = FastAPI(title="promptry dashboard", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://promptry.meownikov.xyz",
        "http://promptry.meownikov.xyz",
        "http://localhost",
    ],
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _dc_to_dict(obj):
    """Recursively convert dataclasses to dicts, handling sets."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dc_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, list):
        return [_dc_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _dc_to_dict(v) for k, v in obj.items()}
    return obj


# ---- Health ----

@app.get("/api/health")
def health():
    try:
        version = importlib.metadata.version("promptry")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    storage = get_storage()
    db_path = str(getattr(storage, "_db_path", "unknown"))
    return {"status": "ok", "version": version, "db_path": db_path}


# ---- Suites ----

@app.get("/api/suites")
def list_suites():
    storage = get_storage()
    suite_names = storage.list_suite_names()

    results = []
    for name in suite_names:
        runs = storage.get_eval_runs(name, limit=1)
        if not runs:
            continue
        latest = runs[0]

        history = storage.get_score_history(name, limit=10)
        sparkline = [score for _, score in reversed(history)]

        # drift
        from promptry.drift import DriftMonitor
        monitor = DriftMonitor(storage=storage)
        drift = monitor.check(name)

        results.append({
            "name": name,
            "latest_score": latest.overall_score,
            "passed": latest.overall_pass,
            "model_version": latest.model_version,
            "prompt_version": latest.prompt_version,
            "timestamp": latest.timestamp,
            "drift_status": "drifting" if drift.is_drifting else "stable",
            "drift_slope": drift.slope,
            "sparkline_scores": sparkline,
        })

    return results


# ---- Suite Runs ----

@app.get("/api/suite/{name}/runs")
def suite_runs(name: str, limit: int = Query(20, le=200)):
    storage = get_storage()
    runs = storage.get_eval_runs(name, limit=limit)
    return [_dc_to_dict(r) for r in runs]


# ---- Run Detail ----

@app.get("/api/suite/{name}/run/{run_id}")
def run_detail(name: str, run_id: int):
    storage = get_storage()
    run = storage.get_eval_run_by_id(run_id)
    if run is None or run.suite_name != name:
        raise HTTPException(404, detail=f"Run {run_id} not found in suite {name}")
    assertions = storage.get_eval_results(run_id)
    return {
        "run": _dc_to_dict(run),
        "assertions": [_dc_to_dict(a) for a in assertions],
    }


# ---- Prompts ----

@app.get("/api/prompts")
def list_prompts():
    storage = get_storage()
    all_prompts = storage.list_prompts()
    # group by name, take latest version
    by_name: dict[str, dict] = {}
    for p in all_prompts:
        if p.name not in by_name or p.version > by_name[p.name]["latest_version"]:
            by_name[p.name] = {
                "name": p.name,
                "latest_version": p.version,
                "tags": p.tags,
            }
    return sorted(by_name.values(), key=lambda x: x["name"])


@app.get("/api/prompts/{name}")
def prompt_versions(name: str):
    storage = get_storage()
    prompts = storage.list_prompts(name=name)
    if not prompts:
        raise HTTPException(404, detail=f"Prompt '{name}' not found")
    return {
        "versions": [
            {"version": p.version, "hash": p.hash, "created_at": p.created_at, "tags": p.tags}
            for p in sorted(prompts, key=lambda p: p.version, reverse=True)
        ]
    }


@app.get("/api/prompts/{name}/content")
def prompt_content(name: str, v: int = Query(...)):
    storage = get_storage()
    prompt = storage.get_prompt(name, version=v)
    if prompt is None:
        raise HTTPException(404, detail=f"Prompt '{name}' v{v} not found")
    return _dc_to_dict(prompt)


@app.get("/api/prompts/{name}/diff")
def prompt_diff(name: str, v1: int = Query(...), v2: int = Query(...)):
    storage = get_storage()
    p1 = storage.get_prompt(name, version=v1)
    p2 = storage.get_prompt(name, version=v2)
    if p1 is None:
        raise HTTPException(404, detail=f"Prompt '{name}' v{v1} not found")
    if p2 is None:
        raise HTTPException(404, detail=f"Prompt '{name}' v{v2} not found")

    old_lines = p1.content.splitlines()
    new_lines = p2.content.splitlines()

    diff_lines = []
    additions = 0
    deletions = 0
    old_num = 0
    new_num = 0

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                old_num += 1
                new_num += 1
                diff_lines.append({
                    "type": "unchanged", "old_num": old_num, "new_num": new_num,
                    "content": old_lines[i1 + k],
                })
        elif tag == "delete":
            for k in range(i2 - i1):
                old_num += 1
                deletions += 1
                diff_lines.append({
                    "type": "deleted", "old_num": old_num, "new_num": None,
                    "content": old_lines[i1 + k],
                })
        elif tag == "insert":
            for k in range(j2 - j1):
                new_num += 1
                additions += 1
                diff_lines.append({
                    "type": "added", "old_num": None, "new_num": new_num,
                    "content": new_lines[j1 + k],
                })
        elif tag == "replace":
            for k in range(i2 - i1):
                old_num += 1
                deletions += 1
                diff_lines.append({
                    "type": "deleted", "old_num": old_num, "new_num": None,
                    "content": old_lines[i1 + k],
                })
            for k in range(j2 - j1):
                new_num += 1
                additions += 1
                diff_lines.append({
                    "type": "added", "old_num": None, "new_num": new_num,
                    "content": new_lines[j1 + k],
                })

    return {"additions": additions, "deletions": deletions, "lines": diff_lines}


# ---- Models ----

@app.get("/api/models/{suite}")
def model_versions(suite: str):
    storage = get_storage()
    versions = storage.get_model_versions(suite)
    return {"versions": [{"model_version": v, "run_count": c} for v, c in versions]}


@app.get("/api/models/{suite}/compare")
def model_compare(suite: str, baseline: str = Query(...), candidate: str = Query(...)):
    from promptry.model_compare import compare_models
    try:
        report = compare_models(suite_name=suite, candidate=candidate, baseline=baseline)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return _dc_to_dict(report)


# ---- Cost ----

@app.get("/api/cost")
def cost_report(
    days: int = Query(7, ge=1, le=365),
    name: Optional[str] = None,
    model: Optional[str] = None,
):
    storage = get_storage()
    return storage.get_cost_data(days=days, name=name, model=model)


# ---- Static files (fallback SPA) ----

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_api.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite for regressions**

Run: `pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add promptry/dashboard/ tests/test_dashboard_api.py pyproject.toml
git commit -m "feat(dashboard): add FastAPI server with all API routes"
```

---

## Task 3: CLI Dashboard Command

**Files:**
- Modify: `promptry/cli.py`

- [ ] **Step 1: Add the dashboard command to cli.py**

Add before the `@app.command("init")` block:

```python
@app.command("dashboard")
def dashboard_cmd(
    port: int = typer.Option(8420, "--port", "-p", help="Port to serve on."),
    no_open: bool = typer.Option(False, "--no-open", help="Don't auto-open browser."),
    local: bool = typer.Option(False, "--local", help="Open localhost instead of hosted URL."),
):
    """Start the promptry dashboard web UI."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error:[/red] Dashboard dependencies not installed.")
        console.print("  Install with: pip install promptry[dashboard]")
        raise typer.Exit(1)

    hosted_url = f"https://promptry.meownikov.xyz/dashboard?port={port}"
    local_url = f"http://localhost:{port}"
    open_url = local_url if local else hosted_url

    console.print(f"\n[bold]promptry dashboard[/bold] starting on port {port}\n")
    console.print(f"  Local API:  {local_url}/api/health")
    console.print(f"  Dashboard:  {hosted_url}")
    console.print(f"  Local UI:   {local_url}/")
    console.print()

    if not no_open:
        import webbrowser
        webbrowser.open(open_url)

    from promptry.dashboard.server import app as dashboard_app
    uvicorn.run(dashboard_app, host="127.0.0.1", port=port, log_level="info")
```

- [ ] **Step 2: Verify the command registers**

Run: `python -m promptry.cli dashboard --help`
Expected: Shows help text with --port, --no-open, --local options.

- [ ] **Step 3: Commit**

```bash
git add promptry/cli.py
git commit -m "feat(cli): add 'promptry dashboard' command"
```

---

## Task 4: Frontend — Scaffolding and Theme

**Files:**
- Create: `dashboard-ui/package.json`
- Create: `dashboard-ui/tsconfig.json`
- Create: `dashboard-ui/vite.config.ts`
- Create: `dashboard-ui/index.html`
- Create: `dashboard-ui/src/main.tsx`
- Create: `dashboard-ui/src/App.tsx`
- Create: `dashboard-ui/src/theme.ts`
- Create: `dashboard-ui/src/api/client.ts`
- Create: `dashboard-ui/src/api/types.ts`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "promptry-dashboard",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "recharts": "^2.12.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../promptry/dashboard/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8420",
    },
  },
});
```

- [ ] **Step 4: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>promptry</title>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      body { background: #0d1117; color: #e6edf3; font-family: 'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create theme.ts**

```typescript
export const theme = {
  bg: "#0d1117",
  surface: "#161b22",
  border: "#21262d",
  text: "#e6edf3",
  textSecondary: "#7d8590",
  textMuted: "#484f58",
  accent: "#58a6ff",
  success: "#3fb950",
  warning: "#d29922",
  error: "#f85149",
  font: "'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace",
} as const;
```

- [ ] **Step 6: Create api/types.ts**

```typescript
export interface SuiteSummary {
  name: string;
  latest_score: number | null;
  passed: boolean;
  model_version: string | null;
  prompt_version: number | null;
  timestamp: string;
  drift_status: "stable" | "drifting";
  drift_slope: number;
  sparkline_scores: number[];
}

export interface EvalRun {
  id: number;
  suite_name: string;
  prompt_name: string | null;
  prompt_version: number | null;
  model_version: string | null;
  timestamp: string;
  overall_pass: boolean;
  overall_score: number | null;
}

export interface AssertionResult {
  id: number;
  run_id: number;
  test_name: string;
  assertion_type: string;
  passed: boolean;
  score: number | null;
  details: Record<string, unknown> | null;
  latency_ms: number | null;
}

export interface RunDetailResponse {
  run: EvalRun;
  assertions: AssertionResult[];
}

export interface PromptSummary {
  name: string;
  latest_version: number;
  tags: string[];
}

export interface PromptVersion {
  version: number;
  hash: string;
  created_at: string;
  tags: string[];
}

export interface DiffLine {
  type: "unchanged" | "added" | "deleted";
  old_num: number | null;
  new_num: number | null;
  content: string;
}

export interface DiffResponse {
  additions: number;
  deletions: number;
  lines: DiffLine[];
}

export interface ModelVersion {
  model_version: string;
  run_count: number;
}

export interface AssertionComparison {
  assertion_type: string;
  baseline_mean: number;
  baseline_std: number;
  candidate_score: number;
  delta: number;
  verdict: "better" | "worse" | "comparable";
}

export interface ModelCompareReport {
  suite_name: string;
  baseline: { model_version: string; run_count: number; overall_mean: number; overall_std: number; };
  candidate: { model_version: string; run_count: number; overall_mean: number; overall_std: number; };
  overall_delta: number;
  percentile: number;
  assertion_comparisons: AssertionComparison[];
  cost_ratio: number | null;
  score_per_dollar_baseline: number | null;
  score_per_dollar_candidate: number | null;
  verdict: "switch" | "comparable" | "keep_baseline";
  verdict_reason: string;
}

export interface CostSummary {
  total_cost: number;
  total_calls: number;
  total_tokens_in: number;
  total_tokens_out: number;
  avg_cost: number;
}

export interface CostByName {
  name: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  cost: number;
  models: string[];
}

export interface CostByDate {
  date: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  cost: number;
}

export interface CostResponse {
  summary: CostSummary;
  by_name: CostByName[];
  by_date: CostByDate[];
}
```

- [ ] **Step 7: Create api/client.ts**

```typescript
const getBaseUrl = (): string => {
  const params = new URLSearchParams(window.location.search);
  const port = params.get("port") || "8420";
  // If running on localhost, use relative URLs (same origin)
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return "";
  }
  // Hosted version: connect to localhost API
  return `http://localhost:${port}`;
};

const BASE = getBaseUrl();

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => fetchJson<{ status: string; version: string }>("/api/health"),
  suites: () => fetchJson<import("./types").SuiteSummary[]>("/api/suites"),
  suiteRuns: (name: string, limit = 20) => fetchJson<import("./types").EvalRun[]>(`/api/suite/${name}/runs?limit=${limit}`),
  runDetail: (name: string, id: number) => fetchJson<import("./types").RunDetailResponse>(`/api/suite/${name}/run/${id}`),
  prompts: () => fetchJson<import("./types").PromptSummary[]>("/api/prompts"),
  promptVersions: (name: string) => fetchJson<{ versions: import("./types").PromptVersion[] }>(`/api/prompts/${name}`),
  promptContent: (name: string, v: number) => fetchJson<Record<string, unknown>>(`/api/prompts/${name}/content?v=${v}`),
  promptDiff: (name: string, v1: number, v2: number) => fetchJson<import("./types").DiffResponse>(`/api/prompts/${name}/diff?v1=${v1}&v2=${v2}`),
  modelVersions: (suite: string) => fetchJson<{ versions: import("./types").ModelVersion[] }>(`/api/models/${suite}`),
  modelCompare: (suite: string, baseline: string, candidate: string) => fetchJson<import("./types").ModelCompareReport>(`/api/models/${suite}/compare?baseline=${baseline}&candidate=${candidate}`),
  cost: (days = 7, name?: string, model?: string) => {
    const params = new URLSearchParams({ days: String(days) });
    if (name) params.set("name", name);
    if (model) params.set("model", model);
    return fetchJson<import("./types").CostResponse>(`/api/cost?${params}`);
  },
};
```

- [ ] **Step 8: Create main.tsx and App.tsx with router**

`src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
```

`src/App.tsx`:
```tsx
import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Overview } from "./pages/Overview";
import { SuiteDetail } from "./pages/SuiteDetail";
import { RunDetail } from "./pages/RunDetail";
import { Prompts } from "./pages/Prompts";
import { PromptDetail } from "./pages/PromptDetail";
import { Models } from "./pages/Models";
import { Cost } from "./pages/Cost";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/suite/:name" element={<SuiteDetail />} />
        <Route path="/suite/:name/run/:runId" element={<RunDetail />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/prompts/:name" element={<PromptDetail />} />
        <Route path="/models" element={<Models />} />
        <Route path="/cost" element={<Cost />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 9: Install dependencies and verify build scaffolding**

```bash
cd dashboard-ui && npm install && npx tsc --noEmit
```
Expected: No errors (pages don't exist yet so some import errors expected — create stubs first).

- [ ] **Step 10: Commit**

```bash
git add dashboard-ui/
git commit -m "feat(dashboard-ui): scaffold React app with router, theme, API client, types"
```

---

## Task 5: Frontend — Shared Components

**Files:**
- Create: `dashboard-ui/src/components/Layout.tsx`
- Create: `dashboard-ui/src/components/Breadcrumb.tsx`
- Create: `dashboard-ui/src/components/Sparkline.tsx`
- Create: `dashboard-ui/src/components/ScoreChart.tsx`
- Create: `dashboard-ui/src/components/AssertionBar.tsx`
- Create: `dashboard-ui/src/components/DiffView.tsx`
- Create: `dashboard-ui/src/components/ClaimBreakdown.tsx`

- [ ] **Step 1: Create Layout.tsx**

Top nav bar with page links and breadcrumb area. Uses `<Outlet />` for nested routes.

```tsx
import { NavLink, Outlet } from "react-router-dom";
import { theme } from "../theme";

const navStyle = (isActive: boolean) => ({
  color: isActive ? theme.text : theme.textSecondary,
  background: isActive ? theme.border : "transparent",
  padding: "4px 10px",
  borderRadius: 4,
  textDecoration: "none",
  fontSize: 12,
});

export function Layout() {
  return (
    <div style={{ minHeight: "100vh", background: theme.bg }}>
      <nav style={{
        display: "flex", alignItems: "center", gap: 16,
        padding: "8px 16px", borderBottom: `1px solid ${theme.border}`,
      }}>
        <NavLink to="/" style={{ fontWeight: 700, color: theme.text, textDecoration: "none", fontSize: 14 }}>
          promptry
        </NavLink>
        <div style={{ display: "flex", gap: 2 }}>
          <NavLink to="/" end style={({ isActive }) => navStyle(isActive)}>Overview</NavLink>
          <NavLink to="/prompts" style={({ isActive }) => navStyle(isActive)}>Prompts</NavLink>
          <NavLink to="/models" style={({ isActive }) => navStyle(isActive)}>Models</NavLink>
          <NavLink to="/cost" style={({ isActive }) => navStyle(isActive)}>Cost</NavLink>
        </div>
        <span style={{ marginLeft: "auto", fontSize: 10, color: theme.textMuted }}>
          localhost:{new URLSearchParams(window.location.search).get("port") || "8420"}
        </span>
      </nav>
      <main style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Create Sparkline.tsx**

```tsx
import { theme } from "../theme";

export function Sparkline({ scores, width = 80, height = 24 }: { scores: number[]; width?: number; height?: number }) {
  if (scores.length < 2) return null;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const range = max - min || 1;
  const points = scores
    .map((s, i) => `${(i / (scores.length - 1)) * width},${height - ((s - min) / range) * (height - 4) - 2}`)
    .join(" ");
  const color = scores[scores.length - 1] >= 0.7 ? theme.success : theme.error;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} opacity={0.7} />
    </svg>
  );
}
```

- [ ] **Step 3: Create ScoreChart.tsx**

Uses recharts `LineChart`. Accepts `data: {timestamp: string, score: number}[]`.

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { theme } from "../theme";

interface Props {
  data: { timestamp: string; score: number }[];
}

export function ScoreChart({ data }: Props) {
  return (
    <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 12 }}>
      <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 8 }}>
        Score history ({data.length} runs)
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data}>
          <XAxis dataKey="timestamp" tick={false} stroke={theme.border} />
          <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: theme.textMuted }} stroke={theme.border} />
          <Tooltip
            contentStyle={{ background: theme.surface, border: `1px solid ${theme.border}`, fontSize: 11, fontFamily: theme.font }}
            labelStyle={{ color: theme.textSecondary }}
          />
          <Line type="monotone" dataKey="score" stroke={theme.accent} strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 4: Create AssertionBar.tsx**

```tsx
import { theme } from "../theme";

interface Props {
  type: string;
  score: number | null;
  passed: boolean;
}

const scoreColor = (score: number) =>
  score >= 0.8 ? theme.success : score >= 0.6 ? theme.warning : theme.error;

export function AssertionBar({ type, score, passed }: Props) {
  const s = score ?? 0;
  const color = scoreColor(s);
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: "6px 12px",
      borderBottom: `1px solid ${theme.border}`, fontSize: 11,
    }}>
      <span style={{ color: passed ? theme.success : theme.error, width: 14 }}>
        {passed ? "✓" : "✗"}
      </span>
      <span style={{ color: theme.text, width: 100 }}>{type}</span>
      <div style={{ flex: 1, background: theme.border, height: 4, borderRadius: 2 }}>
        <div style={{ width: `${s * 100}%`, height: 4, background: color, borderRadius: 2 }} />
      </div>
      <span style={{ color, width: 44, textAlign: "right" }}>{s.toFixed(3)}</span>
    </div>
  );
}
```

- [ ] **Step 5: Create DiffView.tsx**

```tsx
import { theme } from "../theme";
import type { DiffLine } from "../api/types";

interface Props {
  lines: DiffLine[];
  additions: number;
  deletions: number;
  v1: number;
  v2: number;
}

const lineStyles: Record<string, React.CSSProperties> = {
  unchanged: { color: theme.textSecondary },
  added: { color: theme.success, background: `${theme.success}15` },
  deleted: { color: theme.error, background: `${theme.error}15` },
};

const prefix = { unchanged: " ", added: "+", deleted: "-" };

export function DiffView({ lines, additions, deletions, v1, v2 }: Props) {
  return (
    <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, overflow: "hidden" }}>
      <div style={{
        padding: "6px 10px", borderBottom: `1px solid ${theme.border}`,
        display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: theme.textSecondary,
      }}>
        <span>Comparing</span>
        <span style={{ background: theme.border, color: theme.text, padding: "1px 6px", borderRadius: 3 }}>v{v1}</span>
        <span style={{ color: theme.textMuted }}>→</span>
        <span style={{ background: theme.border, color: theme.text, padding: "1px 6px", borderRadius: 3 }}>v{v2}</span>
        <span style={{ marginLeft: "auto", fontSize: 9 }}>
          <span style={{ color: theme.success }}>+{additions}</span>{" "}
          <span style={{ color: theme.error }}>-{deletions}</span>
        </span>
      </div>
      <div style={{ fontSize: 11, lineHeight: 1.7 }}>
        {lines.map((line, i) => (
          <div key={i} style={{ display: "flex", padding: "1px 10px", ...lineStyles[line.type] }}>
            <span style={{ width: 28, textAlign: "right", color: theme.textMuted, marginRight: 4, userSelect: "none" }}>
              {line.old_num ?? ""}
            </span>
            <span style={{ width: 28, textAlign: "right", color: theme.textMuted, marginRight: 8, userSelect: "none" }}>
              {line.new_num ?? ""}
            </span>
            <span style={{ color: lineStyles[line.type].color, marginRight: 8, userSelect: "none" }}>
              {prefix[line.type]}
            </span>
            <span>{line.content}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create ClaimBreakdown.tsx**

```tsx
import { theme } from "../theme";

interface Claim {
  claim: string;
  verdict: string;
  reason: string;
}

export function ClaimBreakdown({ claims }: { claims: Claim[] }) {
  return (
    <div style={{ fontSize: 11 }}>
      {claims.map((c, i) => {
        const fabricated = c.verdict === "fabricated";
        return (
          <div key={i} style={{
            display: "flex", gap: 8, padding: "4px 0",
            borderBottom: `1px solid ${theme.border}`,
            background: fabricated ? `${theme.error}08` : "transparent",
          }}>
            <span style={{ color: fabricated ? theme.error : theme.success, width: 14 }}>
              {fabricated ? "✗" : "✓"}
            </span>
            <span style={{ color: theme.text, flex: 1 }}>"{c.claim}"</span>
            <span style={{ color: fabricated ? theme.error : theme.success, fontSize: 9 }}>
              {c.verdict} — {c.reason}
            </span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd dashboard-ui && npx tsc --noEmit
```
Expected: No errors (assuming page stubs exist).

- [ ] **Step 8: Commit**

```bash
git add dashboard-ui/src/components/
git commit -m "feat(dashboard-ui): add shared components — Layout, Sparkline, ScoreChart, AssertionBar, DiffView, ClaimBreakdown"
```

---

## Task 6: Frontend — Pages (Overview, SuiteDetail, RunDetail)

**Files:**
- Create: `dashboard-ui/src/pages/Overview.tsx`
- Create: `dashboard-ui/src/pages/SuiteDetail.tsx`
- Create: `dashboard-ui/src/pages/RunDetail.tsx`

- [ ] **Step 1: Create Overview.tsx**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { theme } from "../theme";
import { Sparkline } from "../components/Sparkline";
import type { SuiteSummary } from "../api/types";

export function Overview() {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.suites().then(setSuites).finally(() => setLoading(false));
  };
  useEffect(load, []);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: theme.textSecondary }}>Eval Suites</span>
        <button onClick={load} style={{
          marginLeft: "auto", background: theme.surface, border: `1px solid ${theme.border}`,
          color: theme.textSecondary, padding: "3px 10px", borderRadius: 4, fontSize: 10, cursor: "pointer",
        }}>↻ Refresh</button>
      </div>
      {loading && <div style={{ color: theme.textMuted, fontSize: 11 }}>Loading...</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {suites.map((s) => (
          <Link to={`/suite/${s.name}`} key={s.name} style={{ textDecoration: "none" }}>
            <div style={{
              background: theme.surface,
              border: `1px solid ${!s.passed ? theme.error + "33" : theme.border}`,
              borderRadius: 6, padding: "10px 14px",
              display: "flex", alignItems: "center", gap: 12,
            }}>
              <div style={{
                width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                background: s.passed ? theme.success : theme.error,
              }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, color: theme.text, fontWeight: 600 }}>
                  {s.name}
                  {!s.passed && (
                    <span style={{
                      fontSize: 9, background: `${theme.error}22`, color: theme.error,
                      padding: "1px 6px", borderRadius: 3, marginLeft: 6,
                    }}>REGRESSION</span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: theme.textSecondary }}>
                  {s.model_version || "—"} · v{s.prompt_version ?? "?"} · {s.timestamp}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{
                  fontSize: 14, fontWeight: 600,
                  color: (s.latest_score ?? 0) >= 0.8 ? theme.text : (s.latest_score ?? 0) >= 0.6 ? theme.warning : theme.error,
                }}>{(s.latest_score ?? 0).toFixed(3)}</div>
                <div style={{
                  fontSize: 9,
                  color: s.drift_status === "drifting" ? theme.error : theme.success,
                }}>{s.drift_status}</div>
              </div>
              <Sparkline scores={s.sparkline_scores} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create SuiteDetail.tsx**

```tsx
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { theme } from "../theme";
import { ScoreChart } from "../components/ScoreChart";
import type { EvalRun, AssertionResult } from "../api/types";

export function SuiteDetail() {
  const { name } = useParams<{ name: string }>();
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [assertions, setAssertions] = useState<AssertionResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!name) return;
    setLoading(true);
    api.suiteRuns(name, 30).then(async (r) => {
      setRuns(r);
      if (r.length > 0) {
        const detail = await api.runDetail(name, r[0].id);
        setAssertions(detail.assertions);
      }
      setLoading(false);
    });
  }, [name]);

  if (!name) return null;
  const latest = runs[0];
  const chartData = [...runs].reverse().map((r) => ({
    timestamp: r.timestamp,
    score: r.overall_score ?? 0,
  }));

  // root cause: compare latest two runs
  let rootCause = "";
  if (runs.length >= 2) {
    const [a, b] = [runs[0], runs[1]];
    if (a.prompt_version !== b.prompt_version) rootCause = `prompt v${b.prompt_version}→v${a.prompt_version}`;
    else if (a.model_version !== b.model_version) rootCause = `model ${b.model_version}→${a.model_version}`;
  }

  return (
    <div>
      <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 12 }}>
        <Link to="/" style={{ color: theme.accent, textDecoration: "none" }}>Overview</Link>
        <span style={{ color: theme.textMuted, margin: "0 4px" }}>/</span>
        <span style={{ color: theme.text }}>{name}</span>
      </div>

      {loading ? <div style={{ color: theme.textMuted, fontSize: 11 }}>Loading...</div> : (
        <>
          {/* Status bar */}
          <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
            {latest && (
              <>
                <div style={{
                  background: latest.overall_pass ? `${theme.success}12` : `${theme.error}12`,
                  border: `1px solid ${latest.overall_pass ? theme.success : theme.error}33`,
                  padding: "8px 14px", borderRadius: 6,
                }}>
                  <div style={{ fontSize: 9, color: theme.textSecondary }}>status</div>
                  <div style={{ fontSize: 16, color: latest.overall_pass ? theme.success : theme.error, fontWeight: 700 }}>
                    {latest.overall_pass ? "PASS" : "FAIL"}
                  </div>
                </div>
                <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, padding: "8px 14px", borderRadius: 6 }}>
                  <div style={{ fontSize: 9, color: theme.textSecondary }}>score</div>
                  <div style={{ fontSize: 16, color: theme.text, fontWeight: 700 }}>{(latest.overall_score ?? 0).toFixed(3)}</div>
                </div>
                <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, padding: "8px 14px", borderRadius: 6 }}>
                  <div style={{ fontSize: 9, color: theme.textSecondary }}>model</div>
                  <div style={{ fontSize: 12, color: theme.text, fontWeight: 600, marginTop: 2 }}>{latest.model_version || "—"}</div>
                </div>
                {rootCause && (
                  <div style={{ background: `${theme.warning}12`, border: `1px solid ${theme.warning}33`, padding: "8px 14px", borderRadius: 6 }}>
                    <div style={{ fontSize: 9, color: theme.textSecondary }}>cause</div>
                    <div style={{ fontSize: 11, color: theme.warning, fontWeight: 600, marginTop: 2 }}>{rootCause}</div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Chart */}
          {chartData.length > 1 && <div style={{ marginBottom: 14 }}><ScoreChart data={chartData} /></div>}

          {/* Assertion breakdown */}
          {assertions.length > 0 && (
            <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 10, marginBottom: 14 }}>
              <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 6 }}>Latest run — assertions</div>
              {assertions.map((a) => (
                <div key={a.id} style={{
                  display: "flex", justifyContent: "space-between", padding: "3px 0",
                  borderBottom: `1px solid ${theme.border}`, fontSize: 11,
                }}>
                  <span style={{ color: theme.text }}>{a.assertion_type}</span>
                  <span style={{ color: (a.score ?? 0) >= 0.8 ? theme.success : (a.score ?? 0) >= 0.6 ? theme.warning : theme.error }}>
                    {(a.score ?? 0).toFixed(3)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Runs table */}
          <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 6 }}>Recent runs</div>
            <div style={{ fontSize: 10 }}>
              <div style={{ display: "grid", gridTemplateColumns: "20px 1fr 70px 60px 60px", gap: 8, padding: "3px 0", borderBottom: `1px solid ${theme.border}`, color: theme.textMuted }}>
                <span /><span>timestamp</span><span>model</span><span>prompt</span><span>score</span>
              </div>
              {runs.slice(0, 20).map((r) => (
                <Link to={`/suite/${name}/run/${r.id}`} key={r.id} style={{ textDecoration: "none" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "20px 1fr 70px 60px 60px", gap: 8, padding: "4px 0", borderBottom: `1px solid ${theme.surface}` }}>
                    <span style={{ color: r.overall_pass ? theme.success : theme.error }}>●</span>
                    <span style={{ color: theme.text }}>{r.timestamp}</span>
                    <span style={{ color: theme.textSecondary }}>{r.model_version || "—"}</span>
                    <span style={{ color: theme.textSecondary }}>v{r.prompt_version ?? "?"}</span>
                    <span style={{ color: r.overall_pass ? theme.success : theme.error }}>{(r.overall_score ?? 0).toFixed(3)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create RunDetail.tsx**

```tsx
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { theme } from "../theme";
import { AssertionBar } from "../components/AssertionBar";
import { ClaimBreakdown } from "../components/ClaimBreakdown";
import type { RunDetailResponse } from "../api/types";

export function RunDetail() {
  const { name, runId } = useParams<{ name: string; runId: string }>();
  const [data, setData] = useState<RunDetailResponse | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    if (!name || !runId) return;
    api.runDetail(name, Number(runId)).then(setData);
  }, [name, runId]);

  if (!data) return <div style={{ color: theme.textMuted, fontSize: 11 }}>Loading...</div>;
  const { run, assertions } = data;

  // group by test_name
  const byTest: Record<string, typeof assertions> = {};
  for (const a of assertions) {
    (byTest[a.test_name] ??= []).push(a);
  }

  return (
    <div>
      <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 12 }}>
        <Link to="/" style={{ color: theme.accent, textDecoration: "none" }}>Overview</Link>
        <span style={{ color: theme.textMuted, margin: "0 4px" }}>/</span>
        <Link to={`/suite/${name}`} style={{ color: theme.accent, textDecoration: "none" }}>{name}</Link>
        <span style={{ color: theme.textMuted, margin: "0 4px" }}>/</span>
        <span style={{ color: theme.text }}>Run #{run.id}</span>
      </div>

      {/* Meta */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, fontSize: 10, flexWrap: "wrap" }}>
        <span style={{
          background: run.overall_pass ? `${theme.success}22` : `${theme.error}22`,
          color: run.overall_pass ? theme.success : theme.error,
          padding: "3px 8px", borderRadius: 4,
        }}>{run.overall_pass ? "PASS" : "FAIL"}</span>
        <span style={{ color: theme.textSecondary }}>score: <span style={{ color: theme.text }}>{(run.overall_score ?? 0).toFixed(3)}</span></span>
        <span style={{ color: theme.textSecondary }}>model: <span style={{ color: theme.text }}>{run.model_version || "—"}</span></span>
        {run.prompt_name && (
          <span style={{ color: theme.textSecondary }}>prompt:{" "}
            <Link to={`/prompts/${run.prompt_name}`} style={{ color: theme.accent, textDecoration: "none" }}>
              v{run.prompt_version}
            </Link>
          </span>
        )}
        <span style={{ color: theme.textSecondary }}>{run.timestamp}</span>
      </div>

      {/* Assertions by test */}
      {Object.entries(byTest).map(([testName, testAssertions]) => (
        <div key={testName} style={{
          background: theme.surface, border: `1px solid ${theme.border}`,
          borderRadius: 6, marginBottom: 10, overflow: "hidden",
        }}>
          <div style={{ padding: "8px 12px", borderBottom: `1px solid ${theme.border}`, fontSize: 10, color: theme.textSecondary }}>
            {testName} ({testAssertions.length} assertions)
          </div>
          {testAssertions.map((a) => (
            <div key={a.id}>
              <div onClick={() => setExpanded(expanded === a.id ? null : a.id)} style={{ cursor: "pointer" }}>
                <AssertionBar type={a.assertion_type} score={a.score} passed={a.passed} />
              </div>
              {expanded === a.id && a.details && (
                <div style={{ padding: "8px 12px", background: `${theme.bg}`, borderBottom: `1px solid ${theme.border}` }}>
                  {a.assertion_type === "grounded" && a.details.claims ? (
                    <ClaimBreakdown claims={a.details.claims as { claim: string; verdict: string; reason: string }[]} />
                  ) : (
                    <pre style={{ fontSize: 10, color: theme.textSecondary, whiteSpace: "pre-wrap", margin: 0 }}>
                      {JSON.stringify(a.details, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd dashboard-ui && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add dashboard-ui/src/pages/Overview.tsx dashboard-ui/src/pages/SuiteDetail.tsx dashboard-ui/src/pages/RunDetail.tsx
git commit -m "feat(dashboard-ui): add Overview, SuiteDetail, RunDetail pages"
```

---

## Task 7: Frontend — Pages (Prompts, PromptDetail, Models, Cost)

**Files:**
- Create: `dashboard-ui/src/pages/Prompts.tsx`
- Create: `dashboard-ui/src/pages/PromptDetail.tsx`
- Create: `dashboard-ui/src/pages/Models.tsx`
- Create: `dashboard-ui/src/pages/Cost.tsx`

- [ ] **Step 1: Create Prompts.tsx**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { theme } from "../theme";
import type { PromptSummary } from "../api/types";

export function Prompts() {
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  useEffect(() => { api.prompts().then(setPrompts); }, []);

  return (
    <div>
      <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 12 }}>Prompts</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {prompts.map((p) => (
          <Link to={`/prompts/${p.name}`} key={p.name} style={{ textDecoration: "none" }}>
            <div style={{
              background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6,
              padding: "10px 14px", display: "flex", alignItems: "center", gap: 12,
            }}>
              <span style={{ color: theme.text, fontSize: 12, fontWeight: 600 }}>{p.name}</span>
              <span style={{ color: theme.textSecondary, fontSize: 10 }}>v{p.latest_version}</span>
              <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                {p.tags.map((t) => (
                  <span key={t} style={{
                    fontSize: 9, background: `${theme.success}15`, color: theme.success,
                    padding: "1px 6px", borderRadius: 3,
                  }}>{t}</span>
                ))}
              </div>
            </div>
          </Link>
        ))}
        {prompts.length === 0 && <div style={{ color: theme.textMuted, fontSize: 11 }}>No prompts tracked yet.</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create PromptDetail.tsx**

```tsx
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { theme } from "../theme";
import { DiffView } from "../components/DiffView";
import type { PromptVersion, DiffResponse } from "../api/types";

export function PromptDetail() {
  const { name } = useParams<{ name: string }>();
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [v1, setV1] = useState<number>(0);
  const [v2, setV2] = useState<number>(0);

  useEffect(() => {
    if (!name) return;
    api.promptVersions(name).then((d) => {
      setVersions(d.versions);
      if (d.versions.length >= 2) {
        const latest = d.versions[0].version;
        const prev = d.versions[1].version;
        setV1(prev);
        setV2(latest);
      } else if (d.versions.length === 1) {
        setV1(d.versions[0].version);
        setV2(d.versions[0].version);
      }
    });
  }, [name]);

  useEffect(() => {
    if (!name || !v1 || !v2 || v1 === v2) { setDiff(null); return; }
    api.promptDiff(name, v1, v2).then(setDiff);
  }, [name, v1, v2]);

  if (!name) return null;

  return (
    <div>
      <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 12 }}>
        <Link to="/prompts" style={{ color: theme.accent, textDecoration: "none" }}>Prompts</Link>
        <span style={{ color: theme.textMuted, margin: "0 4px" }}>/</span>
        <span style={{ color: theme.text }}>{name}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 10 }}>
        {/* Version sidebar */}
        <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 8 }}>
          <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 6 }}>Versions</div>
          {versions.map((ver) => (
            <div
              key={ver.version}
              onClick={() => {
                if (v2 === ver.version) return;
                setV1(ver.version);
              }}
              style={{
                padding: "5px 6px", borderRadius: 3, marginBottom: 2, cursor: "pointer", fontSize: 10,
                display: "flex", justifyContent: "space-between",
                background: (v1 === ver.version || v2 === ver.version) ? `${theme.accent}15` : "transparent",
                color: (v1 === ver.version || v2 === ver.version) ? theme.accent : theme.text,
              }}
            >
              <span style={{ fontWeight: (v2 === ver.version) ? 600 : 400 }}>v{ver.version}</span>
              <span style={{ color: theme.textMuted }}>{ver.created_at.slice(0, 10)}</span>
            </div>
          ))}
          {versions.some((v) => v.tags.length > 0) && (
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${theme.border}` }}>
              <div style={{ fontSize: 9, color: theme.textSecondary, marginBottom: 4 }}>Tags</div>
              <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                {versions.flatMap((v) => v.tags.map((t) => (
                  <span key={`${v.version}-${t}`} style={{
                    fontSize: 8, background: `${theme.success}15`, color: theme.success,
                    padding: "1px 6px", borderRadius: 3,
                  }}>{t}: v{v.version}</span>
                )))}
              </div>
            </div>
          )}
        </div>

        {/* Diff */}
        {diff ? (
          <DiffView lines={diff.lines} additions={diff.additions} deletions={diff.deletions} v1={v1} v2={v2} />
        ) : (
          <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 20, fontSize: 11, color: theme.textMuted, display: "flex", alignItems: "center", justifyContent: "center" }}>
            {versions.length < 2 ? "Only one version — no diff available." : "Select two versions to compare."}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create Models.tsx**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { theme } from "../theme";
import type { SuiteSummary, ModelVersion, ModelCompareReport } from "../api/types";

export function Models() {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [selectedSuite, setSelectedSuite] = useState("");
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [report, setReport] = useState<ModelCompareReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api.suites().then(setSuites); }, []);

  useEffect(() => {
    if (!selectedSuite) return;
    api.modelVersions(selectedSuite).then((d) => {
      setVersions(d.versions);
      if (d.versions.length >= 2) {
        setBaseline(d.versions[0].model_version);
        setCandidate(d.versions[1].model_version);
      }
    });
  }, [selectedSuite]);

  const compare = () => {
    if (!selectedSuite || !baseline || !candidate) return;
    setError("");
    api.modelCompare(selectedSuite, baseline, candidate).then(setReport).catch((e) => setError(e.message));
  };

  const sel = { background: theme.border, color: theme.text, padding: "3px 8px", borderRadius: 4, border: "none", fontSize: 11, fontFamily: theme.font };

  const verdictColor = { switch: theme.success, comparable: theme.textSecondary, keep_baseline: theme.error };

  return (
    <div>
      <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 12 }}>
        <Link to="/" style={{ color: theme.accent, textDecoration: "none" }}>Overview</Link>
        <span style={{ color: theme.textMuted, margin: "0 4px" }}>/</span>
        <span style={{ color: theme.text }}>Models</span>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center", fontSize: 10, flexWrap: "wrap" }}>
        <span style={{ color: theme.textSecondary }}>Suite:</span>
        <select value={selectedSuite} onChange={(e) => setSelectedSuite(e.target.value)} style={sel}>
          <option value="">select...</option>
          {suites.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
        </select>
        {versions.length >= 2 && (
          <>
            <span style={{ color: theme.textSecondary }}>Baseline:</span>
            <select value={baseline} onChange={(e) => setBaseline(e.target.value)} style={sel}>
              {versions.map((v) => <option key={v.model_version} value={v.model_version}>{v.model_version} ({v.run_count})</option>)}
            </select>
            <span style={{ color: theme.textMuted }}>vs</span>
            <span style={{ color: theme.textSecondary }}>Candidate:</span>
            <select value={candidate} onChange={(e) => setCandidate(e.target.value)} style={sel}>
              {versions.map((v) => <option key={v.model_version} value={v.model_version}>{v.model_version} ({v.run_count})</option>)}
            </select>
            <button onClick={compare} style={{
              background: theme.accent, color: "#fff", border: "none", padding: "4px 12px",
              borderRadius: 4, fontSize: 10, cursor: "pointer", fontFamily: theme.font,
            }}>Compare</button>
          </>
        )}
      </div>

      {error && <div style={{ color: theme.error, fontSize: 11, marginBottom: 8 }}>{error}</div>}

      {report && (
        <>
          {/* Score + Cost cards */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
            <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 12 }}>
              <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 8 }}>Overall Score</div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 16 }}>
                <div>
                  <div style={{ fontSize: 9, color: theme.textSecondary }}>{report.baseline.model_version}</div>
                  <div style={{ fontSize: 20, color: theme.text, fontWeight: 700 }}>{report.baseline.overall_mean.toFixed(3)}</div>
                  <div style={{ fontSize: 9, color: theme.textMuted }}>± {report.baseline.overall_std.toFixed(3)}</div>
                </div>
                <div style={{ fontSize: 16, color: theme.textMuted, paddingBottom: 4 }}>→</div>
                <div>
                  <div style={{ fontSize: 9, color: theme.accent }}>{report.candidate.model_version}</div>
                  <div style={{ fontSize: 20, color: theme.accent, fontWeight: 700 }}>{report.candidate.overall_mean.toFixed(3)}</div>
                  <div style={{ fontSize: 9, color: report.overall_delta >= 0 ? theme.success : theme.error }}>
                    {report.overall_delta >= 0 ? "+" : ""}{report.overall_delta.toFixed(3)} ({report.percentile.toFixed(0)}th pctl)
                  </div>
                </div>
              </div>
            </div>
            {report.cost_ratio !== null && (
              <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 12 }}>
                <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 8 }}>Cost Efficiency</div>
                <div style={{ fontSize: 11, color: theme.textSecondary }}>
                  Cost ratio: <span style={{ color: report.cost_ratio < 1 ? theme.success : theme.error }}>{(report.cost_ratio * 100).toFixed(0)}%</span>
                  {report.cost_ratio < 1 ? ` (${((1 - report.cost_ratio) * 100).toFixed(0)}% cheaper)` : ` (${((report.cost_ratio - 1) * 100).toFixed(0)}% more expensive)`}
                </div>
              </div>
            )}
          </div>

          {/* Assertion table */}
          {report.assertion_comparisons.length > 0 && (
            <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 10, marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 6 }}>By Assertion Type</div>
              <div style={{ fontSize: 10 }}>
                <div style={{ display: "grid", gridTemplateColumns: "100px 110px 80px 60px 70px", gap: 4, padding: "4px 0", borderBottom: `1px solid ${theme.border}`, color: theme.textMuted }}>
                  <span>assertion</span><span>baseline</span><span>candidate</span><span>delta</span><span>verdict</span>
                </div>
                {report.assertion_comparisons.map((ac) => (
                  <div key={ac.assertion_type} style={{ display: "grid", gridTemplateColumns: "100px 110px 80px 60px 70px", gap: 4, padding: "5px 0", borderBottom: `1px solid ${theme.border}22` }}>
                    <span style={{ color: theme.text }}>{ac.assertion_type}</span>
                    <span style={{ color: theme.textSecondary }}>{ac.baseline_mean.toFixed(3)} ± {ac.baseline_std.toFixed(3)}</span>
                    <span style={{ color: theme.text }}>{ac.candidate_score.toFixed(3)}</span>
                    <span style={{ color: ac.delta >= 0 ? theme.success : theme.error }}>{ac.delta >= 0 ? "+" : ""}{ac.delta.toFixed(3)}</span>
                    <span style={{ color: ac.verdict === "better" ? theme.success : ac.verdict === "worse" ? theme.error : theme.textSecondary }}>{ac.verdict}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Verdict */}
          <div style={{
            background: `${verdictColor[report.verdict]}12`,
            border: `1px solid ${verdictColor[report.verdict]}33`,
            borderRadius: 6, padding: 12, display: "flex", alignItems: "center", gap: 12,
          }}>
            <div style={{ fontSize: 18, color: verdictColor[report.verdict], fontWeight: 700 }}>
              {report.verdict === "switch" ? "SWITCH" : report.verdict === "keep_baseline" ? "KEEP BASELINE" : "COMPARABLE"}
            </div>
            <div style={{ fontSize: 10, color: theme.textSecondary }}>{report.verdict_reason}</div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create Cost.tsx**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api/client";
import { theme } from "../theme";
import type { CostResponse } from "../api/types";

export function Cost() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<CostResponse | null>(null);

  useEffect(() => { api.cost(days).then(setData); }, [days]);

  const sel = { background: theme.border, color: theme.text, padding: "3px 8px", borderRadius: 4, border: "none", fontSize: 11, fontFamily: theme.font };

  return (
    <div>
      <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
        <Link to="/" style={{ color: theme.accent, textDecoration: "none" }}>Overview</Link>
        <span style={{ color: theme.textMuted }}>/</span>
        <span style={{ color: theme.text }}>Cost</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ ...sel, marginLeft: 8 }}>
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
        </select>
      </div>

      {data && (
        <>
          {/* Summary cards */}
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            {[
              { label: "total cost", value: `$${data.summary.total_cost.toFixed(2)}` },
              { label: "total calls", value: data.summary.total_calls.toLocaleString() },
              { label: "tokens", value: `${((data.summary.total_tokens_in + data.summary.total_tokens_out) / 1000).toFixed(0)}K` },
              { label: "avg $/call", value: `$${data.summary.avg_cost.toFixed(4)}` },
            ].map((c) => (
              <div key={c.label} style={{ flex: 1, background: theme.surface, border: `1px solid ${theme.border}`, padding: 10, borderRadius: 6 }}>
                <div style={{ fontSize: 9, color: theme.textSecondary }}>{c.label}</div>
                <div style={{ fontSize: 18, color: theme.text, fontWeight: 700 }}>{c.value}</div>
              </div>
            ))}
          </div>

          {/* Daily chart */}
          {data.by_date.length > 1 && (
            <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 12, marginBottom: 14 }}>
              <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 8 }}>Daily cost</div>
              <ResponsiveContainer width="100%" height={120}>
                <BarChart data={data.by_date}>
                  <XAxis dataKey="date" tick={{ fontSize: 8, fill: theme.textMuted }} stroke={theme.border} />
                  <YAxis tick={{ fontSize: 9, fill: theme.textMuted }} stroke={theme.border} />
                  <Tooltip
                    contentStyle={{ background: theme.surface, border: `1px solid ${theme.border}`, fontSize: 10, fontFamily: theme.font }}
                    formatter={(v: number) => [`$${v.toFixed(4)}`, "cost"]}
                  />
                  <Bar dataKey="cost" fill={theme.accent} opacity={0.7} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* By prompt table */}
          <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 10, color: theme.textSecondary, marginBottom: 6 }}>By prompt name</div>
            <div style={{ fontSize: 10 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 60px 80px 80px 60px 80px", gap: 4, padding: "4px 0", borderBottom: `1px solid ${theme.border}`, color: theme.textMuted }}>
                <span>prompt</span><span>calls</span><span>tokens in</span><span>tokens out</span><span>cost</span><span>models</span>
              </div>
              {data.by_name.map((r) => (
                <div key={r.name} style={{ display: "grid", gridTemplateColumns: "1fr 60px 80px 80px 60px 80px", gap: 4, padding: "5px 0", borderBottom: `1px solid ${theme.border}22` }}>
                  <span style={{ color: theme.text }}>{r.name}</span>
                  <span style={{ color: theme.textSecondary }}>{r.calls.toLocaleString()}</span>
                  <span style={{ color: theme.textSecondary }}>{r.tokens_in.toLocaleString()}</span>
                  <span style={{ color: theme.textSecondary }}>{r.tokens_out.toLocaleString()}</span>
                  <span style={{ color: theme.text }}>${r.cost.toFixed(2)}</span>
                  <span style={{ color: theme.textSecondary }}>{r.models.join(", ")}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Build the SPA**

```bash
cd dashboard-ui && npm run build
```
Expected: Output in `promptry/dashboard/static/` with `index.html` and `assets/`.

- [ ] **Step 6: Verify the full stack**

```bash
# Terminal 1: start the dashboard
python -c "
import uvicorn
from promptry.dashboard.server import app
uvicorn.run(app, host='127.0.0.1', port=8420)
" &

# Terminal 2: test API
curl http://localhost:8420/api/health
# Expected: {"status":"ok","version":"0.4.0",...}

# Open http://localhost:8420/ in browser — should show the SPA
```

- [ ] **Step 7: Commit**

```bash
git add dashboard-ui/src/pages/ promptry/dashboard/static/
git commit -m "feat(dashboard-ui): add all pages — Overview, SuiteDetail, RunDetail, Prompts, PromptDetail, Models, Cost"
```

---

## Task 8: Final Integration and Tests

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run full backend test suite**

```bash
pytest tests/ -q
```
Expected: ALL PASS (190+ tests)

- [ ] **Step 2: Run dashboard API tests specifically**

```bash
pytest tests/test_dashboard_api.py -v
```
Expected: ALL PASS

- [ ] **Step 3: Update README with dashboard section**

Add a "Dashboard" section to README.md after the CLI reference:

```markdown
## Dashboard

```bash
pip install promptry[dashboard]
promptry dashboard
```

Opens a web dashboard at `http://localhost:8420` showing:
- **Overview** — all eval suites with pass/fail status, sparklines, drift detection
- **Suite detail** — score history chart, assertion breakdown, root cause hints
- **Run detail** — per-assertion results with expandable details and grounding claim breakdowns
- **Prompts** — version history with git-diff style comparison
- **Models** — statistical model comparison with cost efficiency analysis
- **Cost** — token usage and cost charts over time
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add dashboard section to README"
```

- [ ] **Step 5: Final verification**

```bash
# Full test suite
pytest tests/ -q
# Frontend builds
cd dashboard-ui && npm run build
# Server starts
python -c "from promptry.dashboard.server import app; print('OK')"
# CLI command exists
python -m promptry.cli dashboard --help
```

All should succeed.
