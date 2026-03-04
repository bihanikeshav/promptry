"""Data classes used across promptry.

All the shapes that get passed between modules live here so nothing
has to import from storage or runner just to get a type.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---- prompt records ----

@dataclass
class PromptRecord:
    id: int
    name: str
    version: int
    content: str
    hash: str
    metadata: dict
    created_at: str
    tags: list[str] = field(default_factory=list)


# ---- eval records ----

@dataclass
class EvalRunRecord:
    id: int
    suite_name: str
    prompt_name: str | None
    prompt_version: int | None
    model_version: str | None
    timestamp: str
    overall_pass: bool
    overall_score: float | None


@dataclass
class EvalResultRecord:
    id: int
    run_id: int
    test_name: str
    assertion_type: str
    passed: bool
    score: float | None
    details: dict | None
    latency_ms: float | None


# ---- runner / suite results ----

@dataclass
class TestResult:
    test_name: str
    passed: bool
    assertions: list  # list[AssertionResult] -- avoids circular import
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class SuiteResult:
    suite_name: str
    tests: list[TestResult]
    overall_pass: bool = True
    overall_score: float = 0.0
    prompt_name: str | None = None
    prompt_version: int | None = None
    model_version: str | None = None
    run_id: int | None = None


# ---- comparison ----

@dataclass
class ComparisonResult:
    metric: str
    baseline_value: float
    current_value: float
    passed: bool


@dataclass
class RootCauseHint:
    """A possible explanation for a regression."""
    cause: str
    detail: str


# ---- drift ----

@dataclass
class DriftReport:
    suite_name: str
    window: int
    scores: list[float]
    slope: float
    mean_score: float
    latest_score: float
    is_drifting: bool
    threshold: float
    message: str
