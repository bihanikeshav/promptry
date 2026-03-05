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
from promptry import suite, assert_semantic


# replace this with your actual LLM call
def my_pipeline(question: str) -> str:
    return "This is a placeholder response. Hook up your LLM here."


@suite("smoke-test")
def test_basic_quality():
    """Basic sanity check that your pipeline returns something reasonable."""
    response = my_pipeline("What is machine learning?")
    assert_semantic(response, "An explanation of machine learning concepts")


# to define a pipeline function for safety template testing:
# promptry templates run --module evals
def pipeline(prompt: str) -> str:
    return my_pipeline(prompt)
'''


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
        console.print("  3. Run safety tests: promptry templates run --module evals")
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


def main():
    app()
