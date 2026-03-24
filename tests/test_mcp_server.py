"""Tests for the MCP server tools.

Calls tool functions directly (not through MCP transport) to verify
they return the expected plain-text results.
"""
import pytest

mcp_mod = pytest.importorskip("mcp", reason="mcp package not installed")

from promptry.config import reset_config
from promptry.storage import reset_storage


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
    reset_config()
    reset_storage()
    yield
    reset_storage()
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


# ---- Model Comparison tools ----


class TestModelCompareTools:

    def test_compare_no_data(self):
        from promptry.mcp_server import compare_models
        result = compare_models(
            suite_name="test-suite",
            candidate="new-model",
            baseline="old-model",
        )
        assert "Error" in result

    def test_compare_with_data(self):
        from promptry.mcp_server import compare_models
        from promptry.storage import get_storage

        storage = get_storage()
        # seed baseline runs
        for score in [0.85, 0.87, 0.89]:
            run_id = storage.save_eval_run(
                suite_name="test-suite",
                model_version="gpt-4o",
                overall_pass=True,
                overall_score=score,
            )
            storage.save_eval_result(
                run_id=run_id, test_name="test", assertion_type="semantic",
                passed=True, score=score,
            )
        # seed candidate run
        run_id = storage.save_eval_run(
            suite_name="test-suite",
            model_version="claude-sonnet",
            overall_pass=True,
            overall_score=0.92,
        )
        storage.save_eval_result(
            run_id=run_id, test_name="test", assertion_type="semantic",
            passed=True, score=0.92,
        )

        result = compare_models(
            suite_name="test-suite",
            candidate="claude-sonnet",
            baseline="gpt-4o",
        )
        assert "gpt-4o" in result
        assert "claude-sonnet" in result
        assert "Verdict" in result


# ---- Cost Report tools ----


class TestCostReportTools:

    def test_cost_report_empty(self):
        from promptry.mcp_server import cost_report
        result = cost_report(days=7)
        assert "No prompts" in result

    def test_cost_report_with_data(self):
        import json
        from promptry.mcp_server import cost_report
        from promptry.storage import get_storage

        storage = get_storage()
        storage.save_prompt(
            name="my-prompt",
            content="test content",
            content_hash="abc123",
            metadata={"tokens_in": 500, "tokens_out": 100, "model": "gpt-4o", "cost": 0.005},
        )
        result = cost_report(days=7)
        assert "my-prompt" in result
        assert "500" in result
        assert "gpt-4o" in result


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
