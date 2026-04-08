"""CLI for promptry."""
from __future__ import annotations

import sys
import json
import importlib
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from promptry.storage import Storage
from promptry.registry import PromptRegistry

app = typer.Typer(
    name="promptry",
    help="Regression protection for LLM pipelines.",
    add_completion=False,
    no_args_is_help=True,
)
prompt_app = typer.Typer(help="Manage prompt versions.", no_args_is_help=True)
monitor_app = typer.Typer(help="Background monitoring.", no_args_is_help=True)
templates_app = typer.Typer(help="Safety and jailbreak test templates.", no_args_is_help=True)
app.add_typer(prompt_app, name="prompt")
app.add_typer(monitor_app, name="monitor")
app.add_typer(templates_app, name="templates")

console = Console()


def _get_registry() -> PromptRegistry:
    return PromptRegistry(Storage())


# ---- prompt subcommands ----


@prompt_app.command("save")
def prompt_save(
    file: Optional[Path] = typer.Argument(None, help="Prompt file. Reads stdin if omitted."),
    name: str = typer.Option(..., "--name", "-n", help="Prompt name."),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Tag to apply."),
    metadata: Optional[str] = typer.Option(None, "--metadata", "-m", help="JSON metadata."),
):
    """Save a new prompt version from file or stdin."""
    if file:
        if not file.is_file():
            console.print(f"[red]Error:[/red] File not found: {file}")
            raise typer.Exit(1)
        content = file.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            console.print("[yellow]Reading from stdin (Ctrl+D to end)...[/yellow]")
        content = sys.stdin.read()

    if not content.strip():
        console.print("[red]Error:[/red] Empty prompt content.")
        raise typer.Exit(1)

    if metadata:
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error:[/red] Invalid JSON in --metadata: {e}")
            raise typer.Exit(1)
    else:
        meta = None
    registry = _get_registry()
    record = registry.save(name=name, content=content, tag=tag, metadata=meta)

    tags_str = f" tags: {', '.join(record.tags)}" if record.tags else ""
    console.print(
        f"[green]Saved[/green] {record.name} v{record.version} "
        f"({record.hash[:8]}){tags_str}"
    )


@prompt_app.command("list")
def prompt_list(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Filter by name."),
):
    """List all prompt versions."""
    registry = _get_registry()
    records = registry.list(name)

    if not records:
        console.print("[yellow]No prompts found.[/yellow]")
        raise typer.Exit(0)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Version", justify="right")
    table.add_column("Hash", max_width=10)
    table.add_column("Tags")
    table.add_column("Created")

    for r in records:
        tags = ", ".join(r.tags) if r.tags else ""
        table.add_row(r.name, str(r.version), r.hash[:8], tags, r.created_at)

    console.print(table)


@prompt_app.command("show")
def prompt_show(
    name: str = typer.Argument(..., help="Prompt name."),
    version: Optional[int] = typer.Option(None, "--version", "-v", help="Version number."),
):
    """Show a prompt's content."""
    registry = _get_registry()
    record = registry.get(name, version)

    if not record:
        v_str = f" v{version}" if version else ""
        console.print(f"[red]Error:[/red] Prompt '{name}'{v_str} not found.")
        raise typer.Exit(1)

    tags_str = f"  tags: {', '.join(record.tags)}" if record.tags else ""
    console.print(f"[bold]{record.name}[/bold] v{record.version} ({record.hash[:8]}){tags_str}")
    console.print(f"[dim]Created: {record.created_at}[/dim]")
    console.print()
    console.print(record.content)


@prompt_app.command("diff")
def prompt_diff(
    name: str = typer.Argument(..., help="Prompt name."),
    v1: int = typer.Argument(..., help="First version."),
    v2: int = typer.Argument(..., help="Second version."),
):
    """Show diff between two prompt versions."""
    registry = _get_registry()

    try:
        diff_text = registry.diff(name, v1, v2)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not diff_text:
        console.print("[yellow]No differences.[/yellow]")
        return

    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            console.print(f"[bold]{line}[/bold]")
        elif line.startswith("+"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        else:
            console.print(line)


@prompt_app.command("tag")
def prompt_tag(
    name: str = typer.Argument(..., help="Prompt name."),
    version: int = typer.Argument(..., help="Version number."),
    tag: str = typer.Argument(..., help="Tag to apply (e.g. prod, canary)."),
):
    """Tag a specific prompt version."""
    registry = _get_registry()

    try:
        registry.tag(name, version, tag)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Tagged[/green] {name} v{version} as [bold]{tag}[/bold]")


# ---- eval commands ----


def _import_module(module_path: str):
    """Import a module by dotted path to trigger @suite registration."""
    try:
        importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        console.print(f"[red]Error:[/red] Could not import '{module_path}': {e}")
        raise typer.Exit(1)


@app.command("run")
def run_cmd(
    suite_name: str = typer.Argument(..., help="Suite to run."),
    module: str = typer.Option(..., "--module", "-m", help="Python module with suite definitions."),
    compare: Optional[str] = typer.Option(None, "--compare", "-c", help="Tag to compare against."),
    prompt_name: Optional[str] = typer.Option(None, "--prompt-name"),
    prompt_version: Optional[int] = typer.Option(None, "--prompt-version"),
    model_version: Optional[str] = typer.Option(None, "--model-version"),
):
    """Run an eval suite. Exit code 1 on regression."""
    _import_module(module)

    from promptry.runner import run_suite
    from promptry.comparison import compare_with_baseline, format_comparison

    try:
        result = run_suite(
            suite_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            model_version=model_version,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for test in result.tests:
        status = "[green]PASS[/green]" if test.passed else "[red]FAIL[/red]"
        console.print(f"  {status} {test.test_name} ({test.latency_ms:.0f}ms)")
        if test.error:
            console.print(f"    {test.error}")
        for a in test.assertions:
            score_str = f" ({a.score:.3f})" if a.score is not None else ""
            a_status = "ok" if a.passed else "FAIL"
            console.print(f"    {a.assertion_type}{score_str} {a_status}")

    console.print()
    console.print(
        f"Overall: {'[green]PASS[/green]' if result.overall_pass else '[red]FAIL[/red]'}"
        f"  score: {result.overall_score:.3f}"
    )

    if compare:
        console.print()
        console.print(f"Comparing against [bold]{compare}[/bold] baseline:")
        comparisons, hints = compare_with_baseline(result, baseline_tag=compare)

        if not comparisons:
            console.print("  [yellow]No baseline found to compare against.[/yellow]")
        else:
            output = format_comparison(comparisons, hints)
            console.print(output)

            if any(not c.passed for c in comparisons):
                raise typer.Exit(1)

    if not result.overall_pass:
        raise typer.Exit(1)


@app.command("suites")
def suites_cmd(
    module: str = typer.Option(..., "--module", "-m", help="Python module with suite definitions."),
):
    """List registered eval suites."""
    _import_module(module)

    from promptry.evaluator import list_suites

    suites = list_suites()
    if not suites:
        console.print("[yellow]No suites found.[/yellow]")
        raise typer.Exit(0)

    for s in suites:
        desc = f" -- {s.description}" if s.description else ""
        console.print(f"  {s.name}{desc}")


@app.command("drift")
def drift_cmd(
    suite_name: str = typer.Argument(..., help="Suite to check."),
    module: str = typer.Option(..., "--module", "-m", help="Python module with suite definitions."),
    window: Optional[int] = typer.Option(None, "--window", "-w"),
    threshold: Optional[float] = typer.Option(None, "--threshold", "-t"),
):
    """Check for score drift in a suite. Exit code 1 if drifting."""
    _import_module(module)

    from promptry.drift import DriftMonitor, format_drift_report

    monitor = DriftMonitor()
    report = monitor.check(suite_name, window=window, threshold=threshold)

    console.print(format_drift_report(report))

    if report.is_drifting:
        raise typer.Exit(1)


@app.command("compare")
def compare_cmd(
    suite_name: str = typer.Argument(..., help="Suite to compare on."),
    candidate: str = typer.Option(..., "--candidate", "-c", help="Candidate model version."),
    baseline: Optional[str] = typer.Option(None, "--baseline", "-b", help="Baseline model version (auto-detected if omitted)."),
):
    """Compare two models using historical eval data.

    Analyzes score distributions, per-assertion breakdowns, and cost
    efficiency to recommend whether to switch models.

    Requires eval runs tagged with --model-version. Example workflow:

        # run evals with your current model
        promptry run my-suite --module evals --model-version gpt-4o

        # switch to candidate model in your pipeline config, then:
        promptry run my-suite --module evals --model-version claude-sonnet-4

        # compare
        promptry compare my-suite --candidate claude-sonnet-4
    """
    from promptry.model_compare import compare_models, format_model_compare

    try:
        report = compare_models(
            suite_name=suite_name,
            candidate=candidate,
            baseline=baseline,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print()
    console.print(format_model_compare(report))
    console.print()

    if report.verdict == "keep_baseline":
        raise typer.Exit(1)


# ---- monitor subcommands ----


@monitor_app.command("start")
def monitor_start(
    suite_name: str = typer.Argument(..., help="Suite to monitor."),
    module: str = typer.Option(..., "--module", "-m", help="Python module with suite definitions."),
    interval: int = typer.Option(1440, "--interval", "-i", help="Run interval in minutes."),
):
    """Start background monitoring."""
    from promptry import scheduler

    try:
        pid = scheduler.start(suite_name, module, interval)
        console.print(f"[green]Monitor started[/green] (PID {pid})")
        console.print(f"  Suite: {suite_name}")
        console.print(f"  Interval: {interval}m")
        console.print(f"  Log: {scheduler._LOG_FILE}")
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@monitor_app.command("stop")
def monitor_stop():
    """Stop background monitoring."""
    from promptry import scheduler

    try:
        pid = scheduler.stop()
        console.print(f"[green]Monitor stopped[/green] (PID {pid})")
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@monitor_app.command("status")
def monitor_status():
    """Check if the monitor is running."""
    from promptry import scheduler

    state = scheduler.status()
    if not state:
        console.print("[yellow]Monitor is not running.[/yellow]")
        raise typer.Exit(1)

    console.print("[green]Monitor is running[/green]")
    if "suite" in state:
        console.print(f"  Suite: {state['suite']}")
    if "interval_minutes" in state:
        console.print(f"  Interval: {state['interval_minutes']}m")
    if "started_at" in state:
        console.print(f"  Started: {state['started_at']}")
    if "last_run" in state:
        console.print(f"  Last run: {state['last_run']}")
        console.print(f"  Last score: {state.get('last_score', 'N/A')}")
        drifting = state.get("drifting", False)
        if drifting:
            console.print("  Drift: [red]DRIFTING[/red]")
        else:
            console.print("  Drift: stable")


# ---- templates subcommands ----


@templates_app.command("list")
def templates_list(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category."),
):
    """List available safety/jailbreak test templates."""
    from promptry.templates import get_templates, get_categories

    templates = get_templates(category)

    if not templates:
        console.print(f"[yellow]No templates found for category '{category}'.[/yellow]")
        raise typer.Exit(0)

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Category")
    table.add_column("Name")
    table.add_column("Severity")

    for t in templates:
        table.add_row(t.id, t.category, t.name, t.severity)

    console.print(table)
    console.print(f"\n{len(templates)} templates across {len(get_categories())} categories")


@templates_app.command("run")
def templates_run(
    module: str = typer.Option(..., "--module", "-m", help="Python module with a pipeline function."),
    func: str = typer.Option("pipeline", "--func", "-f", help="Function name to use as the pipeline."),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Only run this category."),
):
    """Run safety templates against a pipeline function.

    The module should export a callable that takes a string prompt
    and returns a string response. Defaults to 'pipeline', override
    with --func.
    """
    _import_module(module)
    mod = importlib.import_module(module)

    if not hasattr(mod, func):
        console.print(f"[red]Error:[/red] Module '{module}' has no '{func}' function.")
        console.print(f"Define a function like: def {func}(prompt: str) -> str: ...")
        raise typer.Exit(1)

    pipeline_fn = getattr(mod, func)
    if not callable(pipeline_fn):
        console.print(f"[red]Error:[/red] '{func}' in '{module}' is not callable.")
        raise typer.Exit(1)

    from promptry.templates import run_safety_audit

    categories = [category] if category else None
    results = run_safety_audit(pipeline_fn, categories=categories)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    for r in results:
        status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        console.print(f"  {status} {r['template_id']} {r['name']} ({r['score']:.2f})")
        if not r["passed"] and r.get("reason"):
            console.print(f"    {r['reason']}")

    console.print()
    console.print(f"Results: {passed} passed, {failed} failed out of {len(results)}")

    if failed > 0:
        raise typer.Exit(1)


# ---- init ----

_EXAMPLE_EVAL = '''"""Example eval suite for promptry."""
from promptry import suite, assert_semantic, assert_contains, assert_matches


# ---------------------------------------------------------------------------
# Replace this with your actual LLM call.  Every suite below calls one of
# these helpers -- swap in your real model client and you're good to go.
# ---------------------------------------------------------------------------

def my_pipeline(question: str) -> str:
    """General-purpose LLM call.  Replace with your real implementation."""
    return "This is a placeholder response. Hook up your LLM here."


def my_rag_pipeline(question: str) -> str:
    """RAG pipeline: retrieve context, then generate.  Replace with yours."""
    # e.g. context = retriever.search(question)
    #      return llm(question, context=context)
    return "Machine learning is a subset of artificial intelligence."


def my_classifier(text: str) -> str:
    """Classification pipeline.  Should return a single label.  Replace with yours."""
    # e.g. return llm(f"Classify the sentiment: {text}")
    return "positive"


# ---------------------------------------------------------------------------
# Suite 1 -- smoke-test
# Basic sanity check that your pipeline returns something reasonable.
# ---------------------------------------------------------------------------

@suite("smoke-test")
def test_basic_quality():
    """Basic sanity check that your pipeline returns something reasonable."""
    response = my_pipeline("What is machine learning?")
    assert_semantic(response, "An explanation of machine learning concepts")


# ---------------------------------------------------------------------------
# Suite 2 -- rag-qa
# Evaluate a retrieval-augmented generation pipeline.
# Uses assert_semantic for answer quality and assert_contains to verify
# that key facts appear in the response.
# ---------------------------------------------------------------------------

@suite("rag-qa")
def test_rag_quality():
    """Check that the RAG pipeline returns relevant, factual answers."""
    response = my_rag_pipeline("What is machine learning?")

    # The answer should be semantically close to a good reference answer.
    assert_semantic(response, "Machine learning is a branch of AI that learns from data")

    # The answer must mention these key terms.
    assert_contains(response, ["machine learning", "artificial intelligence"])


# ---------------------------------------------------------------------------
# Suite 3 -- classification
# Verify that a classifier returns well-formed labels.
# Uses assert_matches to enforce the expected output format.
# ---------------------------------------------------------------------------

@suite("classification")
def test_classification_format():
    """Ensure the classifier returns a valid label."""
    label = my_classifier("I love this product!")

    # The label must be exactly one of the allowed values.
    assert_matches(label, r"(positive|negative|neutral)")


# ---------------------------------------------------------------------------
# Safety testing pipeline -- used by  promptry templates run --module evals
# ---------------------------------------------------------------------------
def pipeline(prompt: str) -> str:
    return my_pipeline(prompt)
'''


@app.command("votes")
def votes_cmd(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Filter by prompt name."),
    days: int = typer.Option(30, "--days", "-d", help="Number of days to look back."),
    analyze: bool = typer.Option(False, "--analyze", "-a", help="Use LLM judge to analyze downvote patterns."),
):
    """Show vote statistics for prompts."""
    from promptry.storage import get_storage

    storage = get_storage()
    stats = storage.get_vote_stats(prompt_name=name, days=days)

    if stats["total_votes"] == 0:
        console.print("[yellow]No votes found.[/yellow]")
        raise typer.Exit(0)

    table = Table(show_header=True, header_style="bold", title=f"Vote stats (last {days} days)")
    table.add_column("Prompt")
    table.add_column("Version", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Up", justify="right")
    table.add_column("Down", justify="right")
    table.add_column("Upvote %", justify="right")

    for p in stats["prompts"]:
        # prompt-level row
        rate_str = f"{p['upvote_rate'] * 100:.0f}%"
        table.add_row(
            f"[bold]{p['name']}[/bold]",
            "",
            str(p["total"]),
            str(p["upvotes"]),
            str(p["downvotes"]),
            rate_str,
        )
        # per-version rows
        for v in p["versions"]:
            v_rate = f"{v['upvote_rate'] * 100:.0f}%"
            table.add_row(
                "",
                str(v["version"]) if v["version"] is not None else "?",
                str(v["total"]),
                str(v["upvotes"]),
                str(v["downvotes"]),
                v_rate,
            )

    table.add_section()
    overall_rate = f"{stats['overall_upvote_rate'] * 100:.0f}%"
    table.add_row(
        "[bold]Total[/bold]",
        "",
        f"[bold]{stats['total_votes']}[/bold]",
        "",
        "",
        f"[bold]{overall_rate}[/bold]",
    )

    console.print(table)

    if analyze:
        from promptry.feedback import analyze_votes
        from promptry.assertions import get_judge

        judge = get_judge()

        prompt_names = [p["name"] for p in stats["prompts"]]
        if name:
            prompt_names = [name]

        for pname in prompt_names:
            result = analyze_votes(pname, days=days, judge=judge, storage=storage)
            if result["total_downvotes"] > 0:
                console.print(f"\n[bold]Downvote analysis: {pname}[/bold]")
                console.print(result["analysis"])


@app.command("cost-report")
def cost_report_cmd(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Filter by prompt name."),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to look back."),
    model: Optional[str] = typer.Option(None, "--model", help="Filter by model name."),
):
    """Show token usage and cost aggregated by prompt name.

    Reads metadata from tracked prompts. For this to work, pass token/cost
    info when calling track()::

        track(prompt, "my-prompt", metadata={
            "tokens_in": 500,
            "tokens_out": 150,
            "model": "gpt-4o",
            "cost": 0.003,
        })
    """
    from promptry.storage import get_storage

    storage = get_storage()

    # query prompts with metadata from the last N days
    with storage._lock:
        cur = storage._conn.cursor()
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
        cur.execute(query, params)
        rows = cur.fetchall()

    if not rows:
        console.print(f"[yellow]No prompts with metadata found in the last {days} days.[/yellow]")
        console.print("Tip: pass metadata when calling track():")
        console.print('  track(prompt, "name", metadata={"tokens_in": 500, "tokens_out": 150, "model": "gpt-4o", "cost": 0.003})')
        raise typer.Exit(0)

    # aggregate by prompt name and by date
    from collections import defaultdict
    by_name: dict[str, dict] = defaultdict(lambda: {
        "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0, "models": set(),
    })
    by_date: dict[str, dict] = defaultdict(lambda: {
        "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0,
    })

    skipped = 0
    for row in rows:
        try:
            meta = json.loads(row["metadata"])
        except (json.JSONDecodeError, TypeError):
            skipped += 1
            continue

        if not isinstance(meta, dict):
            skipped += 1
            continue

        # check if this row has any cost/token info
        has_cost_info = any(k in meta for k in ("tokens_in", "tokens_out", "cost", "input_tokens", "output_tokens"))
        if not has_cost_info:
            skipped += 1
            continue

        # normalize key names (support both conventions)
        tokens_in = meta.get("tokens_in", 0) or meta.get("input_tokens", 0) or 0
        tokens_out = meta.get("tokens_out", 0) or meta.get("output_tokens", 0) or 0
        cost = meta.get("cost", 0.0) or 0.0
        model_name = meta.get("model", "")

        if model and model_name and model.lower() not in model_name.lower():
            continue

        prompt_name = row["name"]
        date_str = row["created_at"][:10]  # YYYY-MM-DD

        by_name[prompt_name]["tokens_in"] += tokens_in
        by_name[prompt_name]["tokens_out"] += tokens_out
        by_name[prompt_name]["cost"] += cost
        by_name[prompt_name]["calls"] += 1
        if model_name:
            by_name[prompt_name]["models"].add(model_name)

        by_date[date_str]["tokens_in"] += tokens_in
        by_date[date_str]["tokens_out"] += tokens_out
        by_date[date_str]["cost"] += cost
        by_date[date_str]["calls"] += 1

    if not by_name:
        console.print(f"[yellow]No prompts with token/cost metadata found in the last {days} days.[/yellow]")
        raise typer.Exit(0)

    # --- by prompt name ---
    console.print(f"\n[bold]Cost report[/bold] (last {days} days)\n")

    name_table = Table(show_header=True, header_style="bold", title="By prompt name")
    name_table.add_column("Prompt")
    name_table.add_column("Calls", justify="right")
    name_table.add_column("Tokens In", justify="right")
    name_table.add_column("Tokens Out", justify="right")
    name_table.add_column("Cost", justify="right")
    name_table.add_column("Models")

    total_in = total_out = total_calls = 0
    total_cost = 0.0

    for pname, agg in sorted(by_name.items(), key=lambda x: x[1]["cost"], reverse=True):
        models_str = ", ".join(sorted(agg["models"])) if agg["models"] else "-"
        cost_str = f"${agg['cost']:.4f}" if agg["cost"] > 0 else "-"
        name_table.add_row(
            pname,
            f"{agg['calls']:,}",
            f"{agg['tokens_in']:,}",
            f"{agg['tokens_out']:,}",
            cost_str,
            models_str,
        )
        total_in += agg["tokens_in"]
        total_out += agg["tokens_out"]
        total_cost += agg["cost"]
        total_calls += agg["calls"]

    # totals row
    name_table.add_section()
    total_cost_str = f"${total_cost:.4f}" if total_cost > 0 else "-"
    name_table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_calls:,}[/bold]",
        f"[bold]{total_in:,}[/bold]",
        f"[bold]{total_out:,}[/bold]",
        f"[bold]{total_cost_str}[/bold]",
        "",
    )

    console.print(name_table)

    # --- by date ---
    if len(by_date) > 1:
        console.print()
        date_table = Table(show_header=True, header_style="bold", title="By date")
        date_table.add_column("Date")
        date_table.add_column("Calls", justify="right")
        date_table.add_column("Tokens In", justify="right")
        date_table.add_column("Tokens Out", justify="right")
        date_table.add_column("Cost", justify="right")

        for date_str in sorted(by_date.keys()):
            agg = by_date[date_str]
            cost_str = f"${agg['cost']:.4f}" if agg["cost"] > 0 else "-"
            date_table.add_row(
                date_str,
                f"{agg['calls']:,}",
                f"{agg['tokens_in']:,}",
                f"{agg['tokens_out']:,}",
                cost_str,
            )

        console.print(date_table)

    if skipped:
        console.print(f"\n[dim]{skipped} prompt(s) skipped (no token/cost metadata).[/dim]")


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


@app.command("init")
def init_cmd():
    """Scaffold a new promptry project in the current directory."""
    from pathlib import Path

    cwd = Path.cwd()
    created = []

    # promptry.toml
    config_path = cwd / "promptry.toml"
    if config_path.exists():
        console.print("[yellow]promptry.toml already exists, skipping.[/yellow]")
    else:
        config_path.write_text(
            '# promptry config\n'
            '# docs: https://promptry.meownikov.xyz\n'
            '\n'
            '[storage]\n'
            '# db_path = "~/.promptry/promptry.db"\n'
            '# mode = "sync"    # sync | async | off\n'
            '\n'
            '[tracking]\n'
            '# sample_rate = 1.0\n'
            '# context_sample_rate = 0.1\n'
            '\n'
            '[notifications]\n'
            '# webhook_url = "https://hooks.slack.com/services/..."\n'
            '# email = "you@example.com"\n'
            '\n'
            '[monitor]\n'
            '# interval_minutes = 1440\n'
            '# threshold = 0.05\n'
            '# window = 30\n',
            encoding="utf-8",
        )
        created.append("promptry.toml")

    # evals.py
    evals_path = cwd / "evals.py"
    if evals_path.exists():
        console.print("[yellow]evals.py already exists, skipping.[/yellow]")
    else:
        evals_path.write_text(_EXAMPLE_EVAL, encoding="utf-8")
        created.append("evals.py")

    if created:
        console.print(f"[green]Created:[/green] {', '.join(created)}")
        console.print()
        console.print("Next steps:")
        console.print("  1. Edit evals.py and hook up your LLM pipeline")
        console.print("  2. Run: promptry run smoke-test --module evals")
        console.print("  3. Run: promptry run rag-qa --module evals")
        console.print("  4. Run: promptry run classification --module evals")
        console.print("  5. Run safety tests: promptry templates run --module evals")
    else:
        console.print("[yellow]Nothing to create, project already initialized.[/yellow]")


@app.command("mcp")
def mcp_cmd():
    """Start the MCP server (for LLM agent integration)."""
    try:
        from promptry.mcp_server import mcp as mcp_server
    except ImportError:
        console.print("[red]Error:[/red] MCP dependencies not installed.\n  Install with: pip install promptry[mcp]")
        raise typer.Exit(1)
    mcp_server.run()


@app.command("doctor")
def doctor_cmd():
    """Check environment health: dependencies, config, storage, and optional extras."""
    ok_count = 0
    warn_count = 0

    def _ok(label: str, detail: str = ""):
        nonlocal ok_count
        ok_count += 1
        msg = f"[green]OK[/green]   {label}"
        if detail:
            msg += f"  ({detail})"
        console.print(msg)

    def _warn(label: str, detail: str = ""):
        nonlocal warn_count
        warn_count += 1
        msg = f"[yellow]WARN[/yellow] {label}"
        if detail:
            msg += f"  ({detail})"
        console.print(msg)

    def _fail(label: str, detail: str = ""):
        nonlocal warn_count  # failures also count toward warnings for summary
        warn_count += 1
        msg = f"[red]FAIL[/red] {label}"
        if detail:
            msg += f"  ({detail})"
        console.print(msg)

    console.print("[bold]promptry doctor[/bold]\n")

    # 1. Python version >= 3.10
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 10):
        _ok("Python version", version_str)
    else:
        _fail("Python version", f"{version_str} -- requires >= 3.10")

    # 2. Config file found
    from promptry.config import _find_config_file
    config_file = _find_config_file()
    if config_file:
        _ok("Config file", str(config_file))
    else:
        _warn("Config file", "promptry.toml not found -- using defaults")

    # 3. Storage writable
    try:
        storage = Storage()
        storage.save_prompt(
            name="__doctor_check__",
            version=0,
            content="health check",
            content_hash="doctor",
        )
        # clean up the test row
        with storage._lock:
            storage._conn.execute(
                "DELETE FROM prompts WHERE name = '__doctor_check__'"
            )
            storage._conn.commit()
        _ok("Storage writable", storage._db_path)
    except Exception as e:
        _fail("Storage writable", str(e))

    # 4. sentence-transformers installed (optional)
    try:
        import sentence_transformers  # noqa: F401
        _ok("sentence-transformers", sentence_transformers.__version__)
    except ImportError:
        _warn("sentence-transformers", "not installed -- needed for semantic assertions")

    # 5. Embedding model downloaded (optional)
    try:
        from promptry.assertions import _get_model
        _get_model()
        from promptry.config import get_config
        _ok("Embedding model", get_config().model.embedding_model)
    except ImportError:
        _warn("Embedding model", "sentence-transformers not available")
    except Exception as e:
        _warn("Embedding model", f"not downloaded or failed to load: {e}")

    # 6. Dashboard deps (fastapi, uvicorn -- optional)
    dashboard_ok = True
    for pkg in ("fastapi", "uvicorn"):
        try:
            importlib.import_module(pkg)
        except ImportError:
            dashboard_ok = False
            break
    if dashboard_ok:
        _ok("Dashboard deps", "fastapi, uvicorn")
    else:
        _warn("Dashboard deps", "fastapi/uvicorn not installed -- pip install promptry[dashboard]")

    # 7. LLM judge configured (optional)
    from promptry.assertions import get_judge
    if get_judge() is not None:
        _ok("LLM judge", "configured")
    else:
        _warn("LLM judge", "not configured -- call set_judge() to enable assert_llm")

    console.print(f"\n{ok_count} ok, {warn_count} warnings")


def main():
    app()
