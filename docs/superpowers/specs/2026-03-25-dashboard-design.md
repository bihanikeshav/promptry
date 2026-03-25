# promptry Dashboard — Design Spec

## Overview

A web dashboard for promptry that visualizes eval history, prompt versions, model comparisons, and cost data. Primary use case: debugging LLM pipeline regressions. Secondary: ongoing health monitoring.

## Architecture

**Hosted-first, local fallback:**

- Frontend SPA hosted at `promptry.meownikov.xyz/dashboard` (static, CDN-cached, updated independently of PyPI releases)
- `promptry dashboard` starts a local FastAPI server that exposes a JSON REST API on `localhost:8420`
- The hosted SPA makes fetch calls to `http://localhost:8420/api/...` — browsers allow HTTPS→HTTP for localhost (Chrome and Firefox both treat localhost as a secure context)
- FastAPI also bundles a copy of the SPA at `/` as offline fallback
- Data never leaves the user's machine — all reads from local SQLite

**Port discovery for hosted SPA:** The hosted version defaults to `http://localhost:8420`. Users can override via query parameter: `promptry.meownikov.xyz/dashboard?port=9000`. The SPA reads `?port=` on load and uses it as the API base. The `promptry dashboard` command prints the full hosted URL including the port param.

**Tech stack:**

- Backend: FastAPI (optional dependency `pip install promptry[dashboard]`)
- Frontend: React + Vite SPA
- Charts: recharts (lightweight, React-native)
- No auth, no accounts — local dev tool

**CORS:** FastAPI allows origins `https://promptry.meownikov.xyz`, `http://promptry.meownikov.xyz`, and `http://localhost:*`.

**Thread safety:** SQLiteStorage uses a single connection with `threading.Lock`. FastAPI/uvicorn runs sync route handlers in a thread pool. Concurrent API requests will serialize on the lock. Acceptable for a local dev tool.

## Visual Style

GitHub Dark theme:
- Background: `#0d1117`
- Surface: `#161b22`
- Border: `#21262d`
- Text primary: `#e6edf3`
- Text secondary: `#7d8590`
- Text muted: `#484f58`
- Accent/links: `#58a6ff`
- Success: `#3fb950`
- Warning: `#d29922`
- Error: `#f85149`
- Font: `SF Mono, SFMono-Regular, Consolas, monospace`

## Navigation

Contextual drill-down with breadcrumb navigation (Sentry-style):

- Top bar: `promptry` logo + horizontal page links (Overview, Prompts, Models, Cost) + localhost:port indicator
- Breadcrumb below: `Overview / pricing-extract / Run #47`
- Clicking breadcrumb segments navigates up
- Manual refresh button on Overview and Suite Detail pages (no auto-polling)

## Pages

### Level 0: Overview (/)

List of all eval suites. Each suite shows:
- Pass/fail dot (green/red)
- Suite name + "REGRESSION" badge if `latest_run.overall_pass == False`
- Model version, prompt version, time since last run
- Latest score (colored: ≥0.8 green, ≥0.6 yellow, <0.6 red)
- Drift status (stable/drifting) — from `DriftMonitor.check()`
- Sparkline of recent scores (last 10 runs)

**Data source:** Suites are derived from `SELECT DISTINCT suite_name FROM eval_runs`. For each suite, the API fetches the latest run and last 10 scores. Drift is computed on demand per suite. For a small number of suites (<20) this is instant. For larger deployments, consider caching drift results.

### Level 1: Suite Detail (/suite/:name)

Drill-down for a single suite:

**Status bar:** Cards showing: status (PASS/FAIL from latest run), latest score, drift slope, model version, root cause hint.

**Root cause logic:** Compare the two most recent runs. If `prompt_version` changed → "prompt vN→vM". If `model_version` changed → "model X→Y". If neither changed but score dropped → "possible retrieval drift". Link to prompt diff if prompt changed.

**Score history chart:** Line chart of `overall_score` over last 30 runs. No threshold line (there is no stored threshold — the pass/fail boundary varies by assertion).

**Assertion breakdown:** Table showing each assertion type that appeared in the latest run, with its score. Computed from `get_eval_results(latest_run.id)`. Grouped by `test_name` first if the run has multiple tests, then assertions under each test.

**Recent runs table:** Last 20 runs. Columns: pass/fail dot, timestamp, model, prompt version, score. Clickable → Run Detail. No pagination needed (20 rows is enough for a drill-down view).

### Level 2: Run Detail (/suite/:name/run/:id)

Individual eval run inspection. The API validates that `run.suite_name == :name` and returns 404 if mismatched.

**Run metadata:** FAIL/PASS badge, score, model, prompt version (linked to diff view), timestamp.

**Assertion results:** Grouped by `test_name`. Each test shows its assertions as rows:
- Pass/fail icon (✓/✗)
- Assertion type name
- Score bar (horizontal fill, colored by value)
- Score number

**Expandable details:** Click an assertion row to expand and show its `details` JSON. Special rendering for known types:
- `grounded`: claim-by-claim table (claim text, verdict, reason). Fabricated claims get red background row.
- `schema`: show validation errors list.
- Others: formatted JSON.

**Prompt link:** If `prompt_version` is set, link to `/prompts/:prompt_name?v1=<prev>&v2=<current>`.

### Prompts Page (/prompts, /prompts/:name)

**Prompt list view:** Grouped by name. Each shows: name, latest version number, tags (prod, canary badges).

**Prompt detail view:** Two-panel layout:
- Left: version list sidebar (v1, v2, ... with timestamps, tag badges). Click a version to select it.
- Right: git-diff view comparing two selected versions.

**Diff format:** The API returns structured diff lines:
```json
{
  "additions": 2,
  "deletions": 1,
  "lines": [
    {"type": "unchanged", "old_num": 1, "new_num": 1, "content": "You are a pricing assistant."},
    {"type": "deleted",   "old_num": 4, "new_num": null, "content": "Return ONLY data found in the document."},
    {"type": "added",     "old_num": null, "new_num": 4, "content": "Return data from the document. You may"},
    {"type": "added",     "old_num": null, "new_num": 5, "content": "infer reasonable values when not explicit."}
  ]
}
```

`type` is one of: `unchanged`, `added`, `deleted`. Both `old_num` and `new_num` are provided (null for the side that doesn't apply). Server generates this by parsing `difflib.unified_diff` output.

Default: compare latest version against previous. User can click any two versions to compare.

### Models Page (/models)

**Selector:** Dropdowns for suite, baseline model, candidate model. Auto-populate from `get_model_versions()`.

**Score comparison cards:** Side-by-side: baseline `mean ± std` and candidate `mean`, delta, percentile rank.

**Cost efficiency cards:** Cost per call per model, percentage cheaper/more expensive. Only shown if cost metadata exists.

**Per-assertion table:** Columns: assertion type, baseline mean±std, candidate score, delta, verdict (better/worse/~noise). Color-coded.

**Verdict banner:** Green (SWITCH), gray (COMPARABLE), or red (KEEP BASELINE) with explanation text.

**Verdict enums:**
- Overall verdict: `"switch"` | `"comparable"` | `"keep_baseline"`
- Per-assertion verdict: `"better"` | `"worse"` | `"comparable"`

**JSON contract:** The `ModelCompareReport` is serialized using `dataclasses.asdict()`. Frontend types mirror the Python dataclass structure. Key fields:
```json
{
  "suite_name": "pricing-extract",
  "baseline": {"model_version": "gpt-4o", "run_count": 47, "overall_mean": 0.887, "overall_std": 0.031, ...},
  "candidate": {"model_version": "claude-sonnet-4", "run_count": 3, "overall_mean": 0.921, ...},
  "overall_delta": 0.034,
  "percentile": 89.0,
  "assertion_comparisons": [{"assertion_type": "json_valid", "baseline_mean": 0.98, "candidate_score": 1.0, "delta": 0.02, "verdict": "better"}, ...],
  "cost_ratio": 0.6,
  "verdict": "switch",
  "verdict_reason": "Candidate scores +0.034 higher..."
}
```

### Cost Page (/cost)

**Data source:** Cost data lives in `prompts.metadata` JSON field (keys: `tokens_in`/`input_tokens`, `tokens_out`/`output_tokens`, `model`, `cost`). The API queries prompts with metadata containing any of these keys.

**Summary cards:** Total cost, total calls, total tokens (in+out), average cost per call.

**Daily cost chart:** Bar chart of cost per day. Yellow bars for days above the mean.

**By prompt table:** Rows: prompt name, call count, tokens in/out, total cost, models used. Sorted by cost descending.

**Filters:** Time window selector (7d, 30d, 90d), prompt name filter, model filter.

## API Endpoints

All under `/api/`. Error responses use `{"error": "<message>"}` with appropriate HTTP status codes (404, 400, 500).

```
GET /api/suites
  → [{name, latest_score, passed, drift_status, drift_slope, model_version,
      prompt_version, timestamp, sparkline_scores: [float]}]
  Implementation: SELECT DISTINCT suite_name, then for each:
    - latest run from get_eval_runs(name, limit=1)
    - last 10 scores from get_score_history(name, limit=10)
    - drift from DriftMonitor.check(name)

GET /api/suite/:name/runs?limit=20
  → [{id, timestamp, model_version, prompt_version, overall_score, overall_pass}]
  Implementation: get_eval_runs(name, limit)

GET /api/suite/:name/run/:id
  → {run: {id, suite_name, timestamp, model_version, prompt_version, overall_score, overall_pass},
     assertions: [{id, test_name, assertion_type, passed, score, details, latency_ms}]}
  Implementation: get_eval_run_by_id(id) + get_eval_results(id)
  Returns 404 if run.suite_name != :name

GET /api/prompts
  → [{name, latest_version, tags: [string]}]
  Implementation: list_prompts() grouped by name, take latest per group

GET /api/prompts/:name
  → {versions: [{version, hash, created_at, tags: [string]}]}
  Implementation: list_prompts(name)

GET /api/prompts/:name/content?v=5
  → {name, version, content, hash, metadata, created_at, tags}
  Implementation: get_prompt(name, version)

GET /api/prompts/:name/diff?v1=4&v2=5
  → {additions: int, deletions: int,
     lines: [{type: "unchanged"|"added"|"deleted", old_num: int|null, new_num: int|null, content: string}]}
  Implementation: get_prompt(name, v1) + get_prompt(name, v2) + difflib.unified_diff, parsed into structured format

GET /api/models/:suite
  → {versions: [{model_version: string, run_count: int}]}
  Implementation: get_model_versions(suite)

GET /api/models/:suite/compare?baseline=X&candidate=Y
  → ModelCompareReport as JSON (see Models Page section for shape)
  Implementation: compare_models(suite, candidate, baseline)

GET /api/cost?days=30&name=X&model=Y
  → {summary: {total_cost, total_calls, total_tokens_in, total_tokens_out, avg_cost},
     by_name: [{name, calls, tokens_in, tokens_out, cost, models: [string]}],
     by_date: [{date, calls, tokens_in, tokens_out, cost}]}
  Implementation: new get_cost_data() storage method that queries prompts.metadata

GET /api/health
  → {status: "ok", db_path: string, version: string}
  Implementation: version from importlib.metadata.version("promptry")
```

## New Storage Methods Required

```python
# BaseStorage abstract method additions:
@abstractmethod
def list_suite_names(self) -> list[str]:
    """SELECT DISTINCT suite_name FROM eval_runs ORDER BY suite_name"""

@abstractmethod
def get_eval_run_by_id(self, run_id: int) -> EvalRunRecord | None:
    """Fetch a single run by primary key."""

@abstractmethod
def get_cost_data(self, days: int = 7, name: str | None = None, model: str | None = None) -> dict:
    """Query prompts.metadata for token/cost info.
    Returns: {
        "by_name": [{"name": str, "calls": int, "tokens_in": int, "tokens_out": int, "cost": float, "models": [str]}],
        "by_date": [{"date": str, "calls": int, "tokens_in": int, "tokens_out": int, "cost": float}],
        "summary": {"total_cost": float, "total_calls": int, "total_tokens_in": int, "total_tokens_out": int, "avg_cost": float}
    }
    Replaces the raw SQL in cli.py cost_report_cmd and mcp_server cost_report."""
```

These must be declared as `@abstractmethod` in `BaseStorage`, implemented in `SQLiteStorage`, and added as passthroughs in `RemoteStorage` (→ `_local`) and `AsyncWriter` (→ `_storage`).

## CLI Integration

```bash
promptry dashboard              # start on :8420, open browser to hosted URL with ?port=8420
promptry dashboard --port 9000  # custom port
promptry dashboard --no-open    # don't auto-open browser
promptry dashboard --local      # open localhost instead of hosted URL
```

New optional dependency group in pyproject.toml:
```toml
[project.optional-dependencies]
dashboard = ["fastapi>=0.100.0", "uvicorn>=0.20.0"]
```

## File Structure

```
promptry/
  dashboard/
    __init__.py          # empty
    server.py            # FastAPI app, all API routes, CORS, static file serving
    static/              # pre-built React SPA (index.html, assets/)
                         # checked into git — built via `cd dashboard-ui && npm run build`
                         # pyproject.toml includes via [tool.setuptools.package-data]
```

Frontend source (lives in repo root, NOT shipped in PyPI package):

```
dashboard-ui/
  package.json
  vite.config.ts         # output dir → ../promptry/dashboard/static/
  src/
    App.tsx              # router setup (react-router)
    pages/
      Overview.tsx
      SuiteDetail.tsx
      RunDetail.tsx
      Prompts.tsx
      PromptDetail.tsx
      Models.tsx
      Cost.tsx
    components/
      ScoreChart.tsx     # recharts line chart
      DiffView.tsx       # git-diff renderer
      AssertionBar.tsx   # horizontal score bar
      ClaimBreakdown.tsx # grounded assertion detail
      Sparkline.tsx      # inline SVG sparkline
      Breadcrumb.tsx
      RefreshButton.tsx
    api/
      client.ts          # fetch wrapper, reads ?port= from URL
    theme.ts             # GitHub Dark color tokens
```

## Key Decisions

1. **No WebSocket / live updates.** Dashboard reads SQLite on each API call. Manual refresh button on pages that benefit from it. No auto-polling.

2. **Pre-built SPA checked into git.** `dashboard/static/` contains the built React app. Contributors run `cd dashboard-ui && npm run build` which outputs directly to `promptry/dashboard/static/`. This ships in the wheel. No npm needed for users.

3. **Hosted version at promptry.meownikov.xyz/dashboard.** Same SPA, different hosting. Port is passed via `?port=` query parameter. Default port is 8420.

4. **No auth.** Local dev tool. Server binds to `127.0.0.1` only by default.

5. **Diff rendering is server-side.** `/api/prompts/:name/diff` returns structured diff data with line types and both old/new line numbers. Frontend renders colors.

6. **FastAPI is optional.** `pip install promptry` works without it. `pip install promptry[dashboard]` adds FastAPI + uvicorn. The `promptry dashboard` command checks for the import and prints install instructions if missing.

7. **Cost data comes from prompt metadata, not eval runs.** The cost page queries `prompts.metadata` for `tokens_in`, `tokens_out`, `cost`, `model` fields. This is the same data source as the CLI `cost-report` command. A new `get_cost_data()` storage method replaces the raw SQL currently in cli.py.
