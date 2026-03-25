"""FastAPI dashboard server for promptry.

Provides a REST API for the promptry dashboard frontend.
All routes are GET-only and return JSON.
"""
from __future__ import annotations

import dataclasses
import difflib
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from promptry.storage import get_storage

app = FastAPI(title="promptry dashboard", docs_url="/api/docs")

# CORS configuration
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
    """Convert a dataclass to a dict, handling sets -> sorted lists."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            result[f.name] = _dc_to_dict(value)
        return result
    elif isinstance(obj, dict):
        return {k: _dc_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_dc_to_dict(item) for item in obj]
    elif isinstance(obj, set):
        return sorted(_dc_to_dict(item) for item in obj)
    else:
        return obj


# ---- Health ----

@app.get("/api/health")
def health():
    storage = get_storage()
    from promptry import __version__

    db_path = str(getattr(storage, "_db_path", "unknown"))
    return {"status": "ok", "version": __version__, "db_path": db_path}


# ---- Suites ----

@app.get("/api/suites")
def list_suites():
    storage = get_storage()
    from promptry.drift import DriftMonitor

    names = storage.list_suite_names()
    drift_monitor = DriftMonitor(storage=storage)
    result = []

    for name in names:
        runs = storage.get_eval_runs(name, limit=1)
        latest = runs[0] if runs else None

        history = storage.get_score_history(name, limit=10)
        sparkline = [score for _, score in reversed(history)]

        drift_report = drift_monitor.check(name)

        result.append({
            "name": name,
            "latest_score": latest.overall_score if latest else None,
            "passed": latest.overall_pass if latest else None,
            "drift_status": "drifting" if drift_report.is_drifting else "stable",
            "drift_slope": drift_report.slope,
            "model_version": latest.model_version if latest else None,
            "prompt_version": latest.prompt_version if latest else None,
            "timestamp": latest.timestamp if latest else None,
            "sparkline_scores": sparkline,
        })

    return result


# ---- Suite Runs ----

@app.get("/api/suite/{name}/runs")
def suite_runs(name: str, limit: int = Query(default=20)):
    storage = get_storage()
    runs = storage.get_eval_runs(name, limit=limit)
    return [_dc_to_dict(r) for r in runs]


# ---- Run Detail ----

@app.get("/api/suite/{name}/run/{run_id}")
def run_detail(name: str, run_id: int):
    storage = get_storage()
    run = storage.get_eval_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.suite_name != name:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} does not belong to suite '{name}'",
        )
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
    if not all_prompts:
        return []

    # Group by name, find latest version for each
    by_name: dict[str, list] = {}
    for p in all_prompts:
        by_name.setdefault(p.name, []).append(p)

    result = []
    for name, versions in by_name.items():
        latest = max(versions, key=lambda p: p.version)
        # Collect all tags across versions
        all_tags = set()
        for v in versions:
            all_tags.update(v.tags)
        result.append({
            "name": name,
            "latest_version": latest.version,
            "tags": sorted(all_tags),
        })

    return result


@app.get("/api/prompts/{name}")
def prompt_versions(name: str):
    storage = get_storage()
    versions = storage.list_prompts(name=name)
    if not versions:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    return {
        "versions": [
            {
                "version": v.version,
                "hash": v.hash,
                "created_at": v.created_at,
                "tags": v.tags,
            }
            for v in versions
        ]
    }


@app.get("/api/prompts/{name}/content")
def prompt_content(name: str, v: Optional[int] = Query(default=None)):
    storage = get_storage()
    record = storage.get_prompt(name, version=v)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    return _dc_to_dict(record)


@app.get("/api/prompts/{name}/diff")
def prompt_diff(name: str, v1: int = Query(...), v2: int = Query(...)):
    storage = get_storage()
    rec1 = storage.get_prompt(name, version=v1)
    rec2 = storage.get_prompt(name, version=v2)
    if rec1 is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' v{v1} not found")
    if rec2 is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' v{v2} not found")

    old_lines = rec1.content.splitlines(keepends=True)
    new_lines = rec2.content.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

    lines = []
    additions = 0
    deletions = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for idx, line in enumerate(old_lines[i1:i2]):
                lines.append({
                    "type": "unchanged",
                    "old_num": i1 + idx + 1,
                    "new_num": j1 + idx + 1,
                    "content": line.rstrip("\n\r"),
                })
        elif tag == "delete":
            for idx, line in enumerate(old_lines[i1:i2]):
                lines.append({
                    "type": "deleted",
                    "old_num": i1 + idx + 1,
                    "new_num": None,
                    "content": line.rstrip("\n\r"),
                })
                deletions += 1
        elif tag == "insert":
            for idx, line in enumerate(new_lines[j1:j2]):
                lines.append({
                    "type": "added",
                    "old_num": None,
                    "new_num": j1 + idx + 1,
                    "content": line.rstrip("\n\r"),
                })
                additions += 1
        elif tag == "replace":
            for idx, line in enumerate(old_lines[i1:i2]):
                lines.append({
                    "type": "deleted",
                    "old_num": i1 + idx + 1,
                    "new_num": None,
                    "content": line.rstrip("\n\r"),
                })
                deletions += 1
            for idx, line in enumerate(new_lines[j1:j2]):
                lines.append({
                    "type": "added",
                    "old_num": None,
                    "new_num": j1 + idx + 1,
                    "content": line.rstrip("\n\r"),
                })
                additions += 1

    return {"additions": additions, "deletions": deletions, "lines": lines}


# ---- Models ----

@app.get("/api/models/{suite}")
def model_versions(suite: str):
    storage = get_storage()
    versions = storage.get_model_versions(suite)
    return {
        "versions": [
            {"model_version": mv, "run_count": count}
            for mv, count in versions
        ]
    }


@app.get("/api/models/{suite}/compare")
def model_compare(
    suite: str,
    baseline: str = Query(...),
    candidate: str = Query(...),
):
    storage = get_storage()
    from promptry.model_compare import compare_models

    try:
        report = compare_models(
            suite_name=suite,
            candidate=candidate,
            baseline=baseline,
            storage=storage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return _dc_to_dict(report)


# ---- Cost ----

@app.get("/api/cost")
def cost_data(
    days: int = Query(default=7),
    name: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
):
    storage = get_storage()
    return storage.get_cost_data(days=days, name=name, model=model)


# ---- Votes ----

@app.get("/api/votes/stats")
def vote_stats(
    name: Optional[str] = Query(default=None),
    days: int = Query(default=30),
):
    storage = get_storage()
    return storage.get_vote_stats(prompt_name=name, days=days)


@app.get("/api/votes")
def list_votes(
    name: Optional[str] = Query(default=None),
    days: int = Query(default=30),
    limit: int = Query(default=50),
):
    storage = get_storage()
    return storage.get_votes(prompt_name=name, days=days, limit=limit)


@app.get("/api/votes/analyze")
def vote_analyze(
    name: str = Query(...),
    days: int = Query(default=30),
):
    from promptry.feedback import analyze_votes
    from promptry.assertions import get_judge

    storage = get_storage()
    judge = get_judge()
    return analyze_votes(name, days=days, judge=judge, storage=storage)


# ---- SPA fallback: serve static files if directory exists ----

_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    # Serve static assets (JS, CSS, etc.)
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="assets")

    # Catch-all: serve index.html for any non-API route (SPA client-side routing)
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(404, detail="Dashboard not built. Run: cd dashboard-ui && npm run build")
