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
app.add_typer(prompt_app, name="prompt")

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

    meta = json.loads(metadata) if metadata else None
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

    from promptry.runner import run_suite, compare_with_baseline, format_comparison

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

    # print test results
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

    # baseline comparison
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


def main():
    app()
