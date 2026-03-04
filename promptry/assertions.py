"""Assertion functions for eval suites.

Each assertion:
  1. Evaluates the condition
  2. Appends an AssertionResult to the current run context
  3. Raises AssertionError on failure
  4. Returns the score (so you can use it if you want)
"""
from __future__ import annotations

import time
from typing import Any, Type

from pydantic import BaseModel, ValidationError

from promptry.evaluator import AssertionResult, append_result

# lazy-loaded embedding model -- only pay the cost if you actually
# use assert_semantic. first call downloads ~80MB, subsequent calls instant.
_model = None
_model_name = "all-MiniLM-L6-v2"


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_model_name)
    return _model


def set_model(name: str):
    """Swap the embedding model (e.g. for a larger one)."""
    global _model, _model_name
    _model_name = name
    _model = None


def assert_semantic(actual: str, expected: str, threshold: float = 0.8) -> float:
    """Check that actual and expected are semantically similar.

    Uses cosine similarity on sentence embeddings.
    Returns the similarity score. Raises if below threshold.
    """
    start = time.perf_counter()

    model = _get_model()
    embeddings = model.encode([actual, expected])
    from sentence_transformers.util import cos_sim
    score = float(cos_sim(embeddings[0], embeddings[1])[0][0])

    passed = score >= threshold
    append_result(AssertionResult(
        assertion_type="semantic",
        passed=passed,
        score=score,
        details={
            "threshold": threshold,
            "actual_preview": actual[:200],
            "expected_preview": expected[:200],
        },
    ))

    if not passed:
        raise AssertionError(
            f"Semantic similarity {score:.3f} < threshold {threshold}"
        )
    return score


def assert_contains(text: str, keywords: list[str], case_sensitive=False) -> float:
    """Check that text contains all keywords. Returns fraction found."""
    check = text if case_sensitive else text.lower()
    found = []
    missing = []
    for kw in keywords:
        if (kw if case_sensitive else kw.lower()) in check:
            found.append(kw)
        else:
            missing.append(kw)

    score = len(found) / len(keywords) if keywords else 1.0
    passed = len(missing) == 0

    append_result(AssertionResult(
        assertion_type="contains",
        passed=passed,
        score=score,
        details={"found": found, "missing": missing},
    ))

    if not passed:
        raise AssertionError(f"Missing keywords: {missing}")
    return score


def assert_not_contains(text: str, keywords: list[str], case_sensitive=False) -> float:
    """Check that text does NOT contain any of the keywords."""
    check = text if case_sensitive else text.lower()
    found_bad = []
    for kw in keywords:
        if (kw if case_sensitive else kw.lower()) in check:
            found_bad.append(kw)

    score = 1.0 - (len(found_bad) / len(keywords)) if keywords else 1.0
    passed = len(found_bad) == 0

    append_result(AssertionResult(
        assertion_type="not_contains",
        passed=passed,
        score=score,
        details={"found_forbidden": found_bad},
    ))

    if not passed:
        raise AssertionError(f"Found forbidden keywords: {found_bad}")
    return score


def assert_schema(data: Any, model: Type[BaseModel]) -> float:
    """Validate data against a Pydantic model.

    Accepts dict, JSON string, or any object with __dict__.
    Returns 1.0 on pass, 0.0 on fail.
    """
    passed = True
    error_details = None

    try:
        if isinstance(data, str):
            model.model_validate_json(data)
        elif isinstance(data, dict):
            model.model_validate(data)
        else:
            model.model_validate(data.__dict__ if hasattr(data, "__dict__") else data)
    except ValidationError as e:
        passed = False
        error_details = e.errors()

    score = 1.0 if passed else 0.0
    append_result(AssertionResult(
        assertion_type="schema",
        passed=passed,
        score=score,
        details={"errors": error_details} if error_details else None,
    ))

    if not passed:
        raise AssertionError(f"Schema validation failed: {error_details}")
    return score
