"""promptry - regression protection for LLM pipelines."""

__version__ = "0.6.1"

from promptry.registry import track, track_context, vote, save_dataset, load_dataset, PromptRegistry
from promptry.feedback import analyze_votes
from promptry.evaluator import suite, check_all
from promptry.assertions import (
    assert_semantic,
    assert_contains,
    assert_not_contains,
    assert_schema,
    assert_llm,
    assert_json_valid,
    assert_matches,
    assert_grounded,
    clean_json,
    set_judge,
)
from promptry.runner import run_suite
from promptry.drift import DriftMonitor
from promptry.templates import get_templates, run_safety_audit

__all__ = [
    "track",
    "track_context",
    "vote",
    "save_dataset",
    "load_dataset",
    "analyze_votes",
    "PromptRegistry",
    "suite",
    "check_all",
    "assert_semantic",
    "assert_contains",
    "assert_not_contains",
    "assert_schema",
    "assert_llm",
    "assert_json_valid",
    "assert_matches",
    "assert_grounded",
    "clean_json",
    "set_judge",
    "run_suite",
    "DriftMonitor",
    "get_templates",
    "run_safety_audit",
]
