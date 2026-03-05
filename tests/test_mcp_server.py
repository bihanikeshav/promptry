"""Tests for the MCP server tools.

Calls tool functions directly (not through MCP transport) to verify
they return the expected plain-text results.
"""
import pytest

mcp_mod = pytest.importorskip("mcp", reason="mcp package not installed")

import os
from promptry.config import reset_config


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
    reset_config()
    yield
    reset_config()


# ---- Prompt tools ----


class TestPromptTools:

    def test_list_empty(self):
        from promptry.mcp_server import prompt_list
        result = prompt_list()
        assert result == "No prompts found."

    def test_save_and_list(self):
        from promptry.mcp_server import prompt_save, prompt_list
        result = prompt_save(name="greet", content="Hello {{name}}")
        assert "Saved" in result
        assert "greet" in result
        assert "v1" in result

        listed = prompt_list()
        assert "greet" in listed

    def test_save_empty_content(self):
        from promptry.mcp_server import prompt_save
        result = prompt_save(name="empty", content="   ")
        assert "Error" in result

    def test_save_with_tag(self):
        from promptry.mcp_server import prompt_save
        result = prompt_save(name="greet", content="Hello", tag="prod")
        assert "prod" in result

    def test_show(self):
        from promptry.mcp_server import prompt_save, prompt_show
        prompt_save(name="greet", content="Hello {{name}}")
        result = prompt_show(name="greet")
        assert "Hello {{name}}" in result
        assert "greet" in result

    def test_show_not_found(self):
        from promptry.mcp_server import prompt_show
        result = prompt_show(name="nonexistent")
        assert "Error" in result

    def test_show_specific_version(self):
        from promptry.mcp_server import prompt_save, prompt_show
        prompt_save(name="greet", content="v1 content")
        prompt_save(name="greet", content="v2 content")
        result = prompt_show(name="greet", version=1)
        assert "v1 content" in result

    def test_diff(self):
        from promptry.mcp_server import prompt_save, prompt_diff
        prompt_save(name="greet", content="Line one\nLine two\n")
        prompt_save(name="greet", content="Line one\nLine changed\n")
        result = prompt_diff(name="greet", v1=1, v2=2)
        assert "Line two" in result
        assert "Line changed" in result

    def test_diff_not_found(self):
        from promptry.mcp_server import prompt_diff
        result = prompt_diff(name="nope", v1=1, v2=2)
        assert "Error" in result

    def test_tag(self):
        from promptry.mcp_server import prompt_save, prompt_tag
        prompt_save(name="greet", content="Hello")
        result = prompt_tag(name="greet", version=1, tag="canary")
        assert "Tagged" in result
        assert "canary" in result

    def test_tag_not_found(self):
        from promptry.mcp_server import prompt_tag
        result = prompt_tag(name="nope", version=99, tag="prod")
        assert "Error" in result

    def test_list_filter_by_name(self):
        from promptry.mcp_server import prompt_save, prompt_list
        prompt_save(name="alpha", content="A content")
        prompt_save(name="beta", content="B content")
        result = prompt_list(name="alpha")
        assert "alpha" in result
        assert "beta" not in result


# ---- Template tools ----


class TestTemplateTools:

    def test_list_templates(self):
        from promptry.mcp_server import list_templates
        result = list_templates()
        assert "templates" in result.lower()

    def test_list_templates_by_category(self):
        from promptry.mcp_server import list_templates
        result = list_templates(category="prompt_injection")
        assert "prompt_injection" in result

    def test_list_templates_bad_category(self):
        from promptry.mcp_server import list_templates
        result = list_templates(category="nonexistent_category")
        assert "No templates found" in result


# ---- Monitor tools ----


class TestMonitorTools:

    def test_monitor_status_not_running(self):
        from promptry.mcp_server import monitor_status
        result = monitor_status()
        assert "not running" in result.lower()


# ---- Import error handling ----


class TestImportErrors:

    def test_list_suites_bad_module(self):
        from promptry.mcp_server import list_suites
        result = list_suites(module="nonexistent.module.path")
        assert "Error" in result

    def test_run_eval_bad_module(self):
        from promptry.mcp_server import run_eval
        result = run_eval(suite_name="test", module="nonexistent.module.path")
        assert "Error" in result

    def test_check_drift_bad_module(self):
        from promptry.mcp_server import check_drift
        result = check_drift(suite_name="test", module="nonexistent.module.path")
        assert "Error" in result

    def test_run_safety_audit_bad_module(self):
        from promptry.mcp_server import run_safety_audit
        result = run_safety_audit(module="nonexistent.module.path")
        assert "Error" in result
