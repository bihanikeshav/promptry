# promptry

[![PyPI](https://img.shields.io/pypi/v/promptry)](https://pypi.org/project/promptry/)
[![npm](https://img.shields.io/npm/v/promptry-js)](https://www.npmjs.com/package/promptry-js)
[![CI](https://github.com/bihanikeshav/promptry/actions/workflows/ci.yml/badge.svg)](https://github.com/bihanikeshav/promptry/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**LLM regression testing that lives in your repo.** Version your prompts, write eval suites in Python, run them in CI. One `pip install`, one SQLite file, zero services — your prompts never leave your laptop.

```python
from promptry import track, suite, assert_semantic

# track() content-hashes your prompt and stores a new version if it changed
prompt = track(system_prompt, "rag-qa")
response = llm.chat(system=prompt, ...)

# suites are regular Python functions. run them via CLI or in CI.
@suite("rag-regression")
def test_quality():
    response = my_pipeline("What is photosynthesis?")
    assert_semantic(response, "Converts light into chemical energy")
```

When a suite regresses against its baseline, promptry reports **what** changed:

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
| **Prompt versioning** | Content-hashed, automatic dedup. No manual bumps, no YAML, no git dance. |
| **Python-native suites** | `@suite` decorators, not YAML. Loops, fixtures, and your IDE's debugger all work. |
| **Deterministic assertions** | Semantic, schema, JSON, regex, grounding, tool-use. Zero API calls at CI time. |
| **LLM-as-judge** | Opt-in, not default. You decide when to spend tokens on evaluation. |
| **Drift detection** | Mann-Whitney U on a rolling window with real p-values, not vibes. |
| **Regression diff** | Tells you *what* changed — prompt version, model, or data — not just that it broke. |
| **Model comparison** | Statistical comparison against the historical baseline, not snapshot-to-snapshot. |
| **Cost tracking** | Per-token cost per prompt across OpenAI, Anthropic, Gemini, Grok — with cache awareness. |
| **Safety suite** | 25 jailbreak / injection / PII / encoding templates across 6 categories. Extensible via `templates.toml`. |
| **MCP server** | First-class: your LLM agent drives the whole test runner. Native, not a plugin. |
| **Dashboard** | Local web UI for eval history, prompt diffs, model comparison, cost. No account, no cloud. |
| **JS/TS client** | Ship prompt events from frontend/Node apps to the same SQLite store. |

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

## Why promptry

Three things you won't get elsewhere — together, in one tool:

1. **Code, not YAML.** Suites are pytest-style decorators. Loops, fixtures, debugger breakpoints, IDE autocomplete. Promptfoo makes you generate YAML from Python scripts once your suite grows past a few dozen tests. Just skip the round trip.
2. **Local by design.** One SQLite file. No account, no API key for the framework, no cloud to trust. LangSmith and DeepEval's flagship features push your prompts and outputs to their servers — disqualifying for regulated industries, IP-sensitive work, or anyone who reads their procurement policy.
3. **No per-run judge tax.** Most assertions are deterministic: semantic similarity, schema, JSON, regex, grounding, tool-use. CI runs cost $0. RAGAS's headline metrics (faithfulness, answer relevancy, context precision) all need judge-model calls — every run costs tokens, adds latency, and drifts when the judge model updates. We treat LLM-as-judge as an opt-in, not a default.

| | Promptfoo | RAGAS | LangSmith | DeepEval | **promptry** |
|---|---|---|---|---|---|
| **Config** | YAML | Python metrics | SaaS UI | Python | **Python decorators** |
| **Data location** | Local | Local | **Their cloud** | Local + push | **Local SQLite** |
| **Account required** | No | No | **Yes** | No (for OSS) | **No, ever** |
| **CI cost per run** | Mixed | **Per-judge-call** | Trace volume | **Per-judge-call** | **$0 (deterministic)** |
| **Prompt versioning** | Manual + git | None | Prompt Hub | None | **Automatic content-hash** |
| **Drift detection** | None | None | Dashboards only | None | **Mann-Whitney U + p-values** |
| **MCP server** | Plugin | None | None | Partial | **Native** |
| **Commercial tier** | Promptfoo Enterprise | None | LangSmith (SaaS) | Confident AI | **None planned** |

## GitHub Action

Run eval suites in CI with one line. On pull requests it posts (or updates) a single comment summarizing the eval: overall score, pass/fail counts, and any regressed tests vs. the previous run. [View on Marketplace.](https://github.com/marketplace/actions/promptry-eval)

```yaml
# .github/workflows/eval.yml
name: Eval
on: [push, pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write  # required for PR comments
    steps:
      - uses: actions/checkout@v4
      - uses: bihanikeshav/promptry@v0.6.0
        with:
          suite: rag-regression
          module: evals
          compare: prod  # optional — compare against baseline
```

Example PR comment on a regression:

```markdown
## promptry eval: rag-regression

| | Current | Baseline | Delta |
|---|---|---|---|
| Overall score | 0.891 | 0.910 | -0.019 |
| Passed | 8/10 | 9/10 | -1 |
| Status | REGRESSED | PASS | |

**Regressions:**
- `test_photosynthesis_answer`: semantic 0.89 -> 0.72 (-0.17)
- `test_schema_validation`: passed -> **failed**

_Generated by [promptry](https://github.com/bihanikeshav/promptry)_
```

Subsequent pushes edit the same comment instead of spamming new ones.

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `suite` | Yes | | Eval suite name |
| `module` | Yes | | Python module containing the suite |
| `compare` | No | | Baseline tag to compare against |
| `python-version` | No | `3.12` | Python version |
| `extras` | No | `semantic` | pip extras to install |
| `pr-comment` | No | `true` | Post/update a PR comment with results |
| `github-token` | No | `${{ github.token }}` | Token used to post PR comments |

## MCP server

```bash
claude mcp add promptry -- promptry mcp    # Claude Code
```

Works with Claude Desktop, Cursor, Windsurf, VS Code. See [full setup](docs/guide.md#mcp-server-llm-agent-integration).

## Documentation

The [full guide](docs/guide.md) covers all assertions, cost tracking, model comparison, safety templates, notifications, storage modes, JS client, CLI reference, MCP setup, and config options.

## Scope

Promptry is a test runner, not a tracing product. If you need an always-on observability dashboard for production traffic with team seats and SSO, use LangSmith or Arize — different product category. Promptry is the thing you wire into CI so a bad prompt change never reaches production in the first place.

On the roadmap: agent trajectory analysis, production capture/replay, LLM-powered root cause. Shipped: everything in the feature table above, across Python + JS + CLI + dashboard + MCP + GitHub Action.

## License

MIT
