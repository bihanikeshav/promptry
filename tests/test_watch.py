"""Tests for `promptry watch`.

Real file-watching is intentionally not exercised here: it depends on OS
filesystem events and is flaky in CI. We mock `watchfiles.watch` and focus
on the module reload + suite discovery logic plus CLI wiring.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from promptry.cli import app, _resolve_module_paths, _run_suite_reload
from promptry.evaluator import clear_suites, list_suites

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
    from promptry.config import reset_config
    from promptry.storage import reset_storage
    reset_storage()
    reset_config()
    clear_suites()
    yield
    reset_storage()
    reset_config()
    clear_suites()


def _write_module(dir_path: Path, name: str, body: str) -> Path:
    file = dir_path / f"{name}.py"
    file.write_text(textwrap.dedent(body), encoding="utf-8")
    return file


def test_watch_command_registered_with_expected_options():
    """The command is discoverable and exposes the documented flags."""
    # Force a wide terminal so Rich doesn't truncate option names
    # (CI runners default to ~80 cols, which collapses "--compare" to "--compa…").
    result = runner.invoke(app, ["watch", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    out = result.output
    assert "Watch files and re-run suites" in out
    assert "--module" in out
    assert "--compare" in out
    assert "--debounce" in out


def test_resolve_module_paths_finds_module_and_siblings(tmp_path, monkeypatch):
    """Resolving a module picks up the file plus .py siblings and promptry.toml."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    main = _write_module(tmp_path, "my_evals", "X = 1\n")
    helper = _write_module(tmp_path, "my_helper", "Y = 2\n")
    (tmp_path / "promptry.toml").write_text("# config\n", encoding="utf-8")

    # Ensure the module is resolvable
    sys.modules.pop("my_evals", None)

    paths = _resolve_module_paths("my_evals")

    resolved = {p.resolve() for p in paths}
    assert main.resolve() in resolved
    assert helper.resolve() in resolved
    assert (tmp_path / "promptry.toml").resolve() in resolved


def test_run_suite_reload_picks_up_file_changes(tmp_path, monkeypatch, capsys):
    """Editing the module between runs must be reflected after reload."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    module_name = "watch_sample_evals"
    _write_module(tmp_path, module_name, """
        from promptry import suite

        @suite("first-suite")
        def first():
            pass
    """)
    sys.modules.pop(module_name, None)

    _run_suite_reload(None, module_name, compare=None)
    names = {s.name for s in list_suites()}
    assert "first-suite" in names
    assert "second-suite" not in names

    # Overwrite the file -- this is what the watcher would trigger on.
    _write_module(tmp_path, module_name, """
        from promptry import suite

        @suite("second-suite")
        def second():
            pass
    """)

    _run_suite_reload(None, module_name, compare=None)
    names = {s.name for s in list_suites()}
    assert "second-suite" in names
    # Old suite must be gone -- registry cleared + module reloaded.
    assert "first-suite" not in names


def test_run_suite_reload_handles_import_errors(tmp_path, monkeypatch, capsys):
    """A broken user module must not crash the watch loop."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    module_name = "watch_broken_evals"
    _write_module(tmp_path, module_name, "this is not valid python ::::\n")
    sys.modules.pop(module_name, None)

    # Should not raise
    _run_suite_reload(None, module_name, compare=None)
    out = capsys.readouterr().out
    assert "Import error" in out or "error" in out.lower()


def test_watch_cmd_runs_initial_then_iterates_mocked_watcher(tmp_path, monkeypatch):
    """End-to-end: mock watchfiles.watch and verify the reload helper is called."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    module_name = "watch_cli_evals"
    _write_module(tmp_path, module_name, """
        from promptry import suite

        @suite("demo")
        def demo():
            pass
    """)
    sys.modules.pop(module_name, None)

    # One fake change event, then stop iteration.
    fake_changes = [[(1, str(tmp_path / f"{module_name}.py"))]]

    def fake_watch(*paths, **kwargs):
        for c in fake_changes:
            yield c

    with patch("watchfiles.watch", side_effect=fake_watch) as mock_watch, \
         patch("promptry.cli._run_suite_reload") as mock_reload:
        result = runner.invoke(app, ["watch", "--module", module_name, "--debounce", "10"])

    assert result.exit_code == 0, result.output
    assert mock_watch.called
    # Initial run + one per change event = 2 calls total.
    assert mock_reload.call_count == 2
    # The args match the CLI invocation.
    for call in mock_reload.call_args_list:
        args, _ = call
        assert args[0] is None  # suite_name default
        assert args[1] == module_name
        assert args[2] is None  # compare default
