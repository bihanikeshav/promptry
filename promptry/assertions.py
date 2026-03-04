"""Assertion functions for eval suites.

Each assertion:
  1. Evaluates the condition
  2. Appends an AssertionResult to the current run context
  3. Raises AssertionError on failure
  4. Returns the score (so you can use it if you want)
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Type

from pydantic import BaseModel, ValidationError

from promptry.evaluator import AssertionResult, append_result

# lazy-loaded embedding model -- only pay the cost if you actually
# use assert_semantic. first call downloads ~80MB, subsequent calls instant.
# default model comes from config (all-MiniLM-L6-v2), overridable via set_model().
_model = None
_model_name_override: str | None = None

# LLM judge callable for assert_llm. the user sets this to their own
# LLM wrapper function: takes a string prompt, returns a string response.
_judge: Callable[[str], str] | None = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from promptry.config import get_config
        name = _model_name_override or get_config().model.embedding_model
        _model = SentenceTransformer(name)
    return _model


def set_model(name: str):
    """Override the embedding model (e.g. for a larger one).

    Takes priority over the config value. Default from config
    is all-MiniLM-L6-v2.
    """
    global _model, _model_name_override
    _model_name_override = name
    _model = None


def set_judge(fn: Callable[[str], str]):
    """Set the LLM judge function for assert_llm.

    The function should take a single string (the grading prompt)
    and return a string (the LLM's response). Provider-agnostic:
    wrap OpenAI, Anthropic, local models, whatever you use.

    Example::

        from openai import OpenAI
        client = OpenAI()

        def my_judge(prompt: str) -> str:
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            return r.choices[0].message.content

        set_judge(my_judge)
    """
    global _judge
    _judge = fn


def get_judge() -> Callable[[str], str] | None:
    return _judge


def assert_semantic(actual: str, expected: str, threshold: float | None = None) -> float:
    """Check that actual and expected are semantically similar.

    Uses cosine similarity on sentence embeddings.
    Threshold defaults to config value (0.8 if unset).
    Returns the similarity score. Raises if below threshold.
    """
    if threshold is None:
        from promptry.config import get_config
        threshold = get_config().model.semantic_threshold

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


# ---- grading prompt for assert_llm ----

_GRADING_PROMPT = """You are an eval grader. Rate the following LLM response against the given criteria.

Response to evaluate:
---
{response}
---

Criteria:
{criteria}

Score the response from 0.0 to 1.0 where:
- 1.0 = fully meets the criteria
- 0.0 = completely fails the criteria

Respond with ONLY a JSON object, nothing else:
{{"score": <float>, "reason": "<short explanation>"}}"""


def _parse_judge_output(raw: str) -> tuple[float, str]:
    """Pull score and reason out of the judge's response.

    Handles common LLM quirks: markdown code fences, extra text
    around the JSON, etc.
    """
    # strip markdown code fences if present
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # try to find a JSON object in the response (handles nested braces)
    start = cleaned.find("{")
    if start == -1:
        raise ValueError(f"Judge did not return valid JSON: {raw[:200]}")

    # find matching closing brace
    depth = 0
    end = start
    for i in range(start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    try:
        data = json.loads(cleaned[start:end])
    except json.JSONDecodeError:
        raise ValueError(f"Judge did not return valid JSON: {raw[:200]}")
    score = float(data.get("score", 0.0))
    reason = str(data.get("reason", ""))

    # clamp to [0, 1]
    score = max(0.0, min(1.0, score))
    return score, reason


def assert_llm(
    response: str,
    criteria: str,
    threshold: float = 0.7,
    judge: Callable[[str], str] | None = None,
) -> float:
    """Grade a response using an LLM judge.

    Sends the response and criteria to an LLM that scores it 0.0-1.0.
    Provider-agnostic: you supply the LLM callable via set_judge() or
    the judge parameter.

    Args:
        response: The LLM output to evaluate.
        criteria: What the response should do / contain / avoid.
        threshold: Minimum score to pass (default 0.7).
        judge: Optional override for the global judge. Takes a prompt
               string, returns a string.

    Returns:
        The score (0.0-1.0).

    Raises:
        AssertionError: If the score is below threshold.
        RuntimeError: If no judge is configured.
    """
    judge_fn = judge or _judge
    if judge_fn is None:
        raise RuntimeError(
            "No LLM judge configured. Call set_judge(fn) first, "
            "or pass judge=fn to assert_llm()."
        )

    grading_prompt = _GRADING_PROMPT.format(
        response=response[:2000],
        criteria=criteria,
    )

    start = time.perf_counter()
    raw_output = judge_fn(grading_prompt)
    latency = (time.perf_counter() - start) * 1000

    try:
        score, reason = _parse_judge_output(raw_output)
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        append_result(AssertionResult(
            assertion_type="llm",
            passed=False,
            score=0.0,
            details={
                "error": str(e),
                "raw_output": raw_output[:500],
                "criteria": criteria,
                "latency_ms": latency,
            },
        ))
        raise AssertionError(f"LLM judge returned unparseable output: {e}")

    passed = score >= threshold
    append_result(AssertionResult(
        assertion_type="llm",
        passed=passed,
        score=score,
        details={
            "criteria": criteria,
            "reason": reason,
            "threshold": threshold,
            "response_preview": response[:200],
            "latency_ms": latency,
        },
    ))

    if not passed:
        raise AssertionError(
            f"LLM judge score {score:.3f} < threshold {threshold} ({reason})"
        )
    return score
