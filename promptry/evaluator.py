"""Eval suite registration and result collection.

The @suite decorator registers test functions. The run_context() collects
assertion results during execution without the user having to wire anything.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

# global registry of suites
_SUITES: dict[str, SuiteDefinition] = {}


@dataclass
class AssertionResult:
    """One assertion's outcome."""
    assertion_type: str  # "semantic", "contains", "schema", etc.
    passed: bool
    score: float | None = None
    details: dict | None = None
    test_name: str = ""


@dataclass
class SuiteDefinition:
    name: str
    fn: Callable
    description: str = ""


def suite(name: str, description: str = ""):
    """Decorator to register a function as an eval suite.

    Usage::

        @suite("rag_regression")
        def test_rag():
            response = my_pipeline("What is X?")
            assert_semantic(response, "Expected answer about X")
            assert_contains(response, ["keyword1", "keyword2"])
    """
    def decorator(fn):
        if name in _SUITES:
            import warnings
            warnings.warn(
                f"Suite '{name}' already registered (was {_SUITES[name].fn.__name__}, "
                f"now {fn.__name__}). The previous definition will be overwritten.",
                stacklevel=2,
            )
        _SUITES[name] = SuiteDefinition(name=name, fn=fn, description=description)
        return fn
    return decorator


def get_suite(name: str) -> SuiteDefinition | None:
    return _SUITES.get(name)


def list_suites() -> list[SuiteDefinition]:
    return list(_SUITES.values())


def clear_suites():
    _SUITES.clear()


# ---- result collection context ----
#
# When a suite runs, assertions append their results here via the
# thread-local. This keeps the user API clean -- just call assert_semantic()
# and it works. The runner pulls results out after the function returns.

_context = threading.local()


def get_current_results() -> list[AssertionResult] | None:
    return getattr(_context, "results", None)


def append_result(result: AssertionResult):
    results = get_current_results()
    if results is not None:
        results.append(result)


@contextmanager
def run_context():
    """Collects assertion results during a suite execution."""
    _context.results = []
    try:
        yield _context.results
    finally:
        _context.results = None
