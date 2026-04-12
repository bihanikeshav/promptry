# promptry

[![PyPI](https://img.shields.io/pypi/v/promptry)](https://pypi.org/project/promptry/)
[![npm](https://img.shields.io/npm/v/promptry-js)](https://www.npmjs.com/package/promptry-js)
[![CI](https://github.com/bihanikeshav/promptry/actions/workflows/ci.yml/badge.svg)](https://github.com/bihanikeshav/promptry/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Sentry for prompts.** Local-first regression testing for LLM pipelines — track prompt versions, run eval suites, catch regressions before your users do.

```python
from promptry import track

prompt = track(system_prompt, "rag-qa")
# promptry automatically versions prompts, runs evals, and flags regressions
```

When something regresses, promptry tells you **what** changed, **when**, and whether it caused it:

```
Overall score: 0.910 -> 0.720  REGRESSION

Probable cause:
  -> Prompt changed (v3 -> v4)
```

## Install

```bash
pip install promptry                       # core
pip install promptry[semantic]             # + semantic assertions (sentence-transformers)
pip install promptry[dashboard]            # + web dashboard
pip install promptry[semantic,dashboard]   # everything
```

## Quick start

```bash
promptry init                              # scaffold project + starter eval
promptry run smoke-test --module evals     # run it
```

```
PASS test_basic_quality (142ms)
  semantic (0.891) ok

Overall: PASS  score: 0.891
```

## Features

| Feature | What it does |
|---------|--------------|
| **Prompt versioning** | Content-hashed, automatic dedup |
| **Eval suites** | Semantic, schema, LLM-as-judge, JSON, regex, grounding assertions |
| **Regression detection** | Compare against baselines, get root cause hints |
| **Drift detection** | Catch slow quality degradation over time |
| **Model comparison** | Statistical comparison against historical baseline (not just snapshots) |
| **Cost tracking** | Token usage and cost per prompt, aggregated reports |
| **Safety templates** | 25+ built-in jailbreak / injection / PII tests |
| **MCP server** | Expose everything as tools for Claude, Cursor, VS Code, etc. |
| **Dashboard** | Web UI for eval history, prompt diffs, model comparison, cost |
| **JS/TS client** | Ship prompt events from frontend/Node apps |

## Dashboard

```bash
pip install promptry[dashboard]
promptry dashboard
```

![Overview](docs/screenshots/dashboard-overview.png)
![Suite Detail](docs/screenshots/dashboard-suite-detail.png)
![Prompts](docs/screenshots/dashboard-prompts.png)
![Models](docs/screenshots/dashboard-models.png)
![Cost](docs/screenshots/dashboard-cost.png)

## How it differs

| | Promptfoo | LangSmith | RAGAS | **promptry** |
|---|---|---|---|---|
| **Approach** | External YAML + CLI | Hosted platform | Metrics library | Python-native, instruments your code |
| **Production tracking** | No | Yes | No | Yes (`track()`) |
| **Drift detection** | No | No | No | Yes |
| **Root cause hints** | No | No | No | Yes |
| **Model comparison** | Snapshot (A vs B now) | No | No | Historical (statistical) |
| **Local-first** | Yes | No (SaaS) | Yes | Yes (SQLite) |
| **Cost** | Free | Paid | Free | Free |

## MCP server

```bash
claude mcp add promptry -- promptry mcp    # Claude Code
```

Works with Claude Desktop, Cursor, Windsurf, VS Code. See [full setup](docs/guide.md#mcp-server-llm-agent-integration).

## Documentation

The [full guide](docs/guide.md) covers all assertions, cost tracking, model comparison, safety templates, notifications, storage modes, JS client, CLI reference, MCP setup, and config options.

## Known limitations

- **No auto-instrumentation.** You add `track()` calls manually. Explicit > magic.
- **Local-first.** No hosted multi-user UI. For that, look at LangSmith or Arize.
- **Early-stage.** v0.5 — API is stable but the project is young. [Issues welcome.](https://github.com/bihanikeshav/promptry/issues)

## License

MIT
