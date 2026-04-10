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
import threading
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

_assertions_lock = threading.Lock()


def _get_model():
    global _model
    with _assertions_lock:
        if _model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for semantic assertions. "
                    "Install it with: pip install promptry[semantic]"
                )
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
    with _assertions_lock:
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
    with _assertions_lock:
        _judge = fn


def get_judge() -> Callable[[str], str] | None:
    with _assertions_lock:
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
    from sentence_transformers.util import cos_sim  # guarded by _get_model above
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

    # try direct parse first, then fall back to regex extraction
    data = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # extract JSON object with regex (handles braces inside strings correctly)
        match = re.search(r'\{[^{}]*(?:"[^"]*"[^{}]*)*\}', cleaned)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if data is None:
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


# ---------------------------------------------------------------------------
# clean_json -- utility for extracting parseable JSON from LLM output
# ---------------------------------------------------------------------------

def clean_json(text: str) -> Any:
    """Extract and parse JSON from LLM output.

    Handles common LLM quirks:
    - Markdown code fences (```json ... ```)
    - Trailing commas before } and ]
    - Leading prose ("Here's the JSON:" ...)
    - Multiple JSON blocks (returns the first valid one)

    Returns the parsed Python object (dict, list, etc.).
    Raises ValueError if no valid JSON can be extracted.
    """
    cleaned = text.strip()

    # strip markdown code fences
    # handles ```json, ```JSON, ```, with optional whitespace
    fence_match = re.search(
        r"```(?:json|JSON)?\s*\n?(.*?)\n?\s*```",
        cleaned,
        re.DOTALL,
    )
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # try direct parse first (fast path)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # fix trailing commas: ,} and ,]
    fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # find first { or [ and try to parse from there
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_idx = cleaned.find(start_char)
        if start_idx == -1:
            continue

        # walk forward to find matching close bracket
        depth = 0
        in_string = False
        escape = False
        for i in range(start_idx, len(cleaned)):
            c = cleaned[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start_idx:i + 1]
                    # fix trailing commas in the candidate too
                    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"No valid JSON found in text: {text[:200]}")


# ---------------------------------------------------------------------------
# assert_json_valid -- lightweight JSON parsability check
# ---------------------------------------------------------------------------

def assert_json_valid(text: str) -> float:
    """Check that text contains valid, parseable JSON.

    Strips markdown fences, fixes trailing commas, and extracts JSON
    from surrounding prose. Use this as a quick gate before deeper
    schema validation.

    Returns 1.0 on success. Raises AssertionError if no valid JSON found.
    The parsed data is available in the result details under "parsed_preview".
    """
    try:
        parsed = clean_json(text)
    except ValueError as e:
        append_result(AssertionResult(
            assertion_type="json_valid",
            passed=False,
            score=0.0,
            details={"error": str(e), "text_preview": text[:200]},
        ))
        raise AssertionError(f"Invalid JSON: {e}")

    # build a useful preview of what was parsed
    preview = json.dumps(parsed, ensure_ascii=False)
    if len(preview) > 200:
        preview = preview[:200] + "..."

    append_result(AssertionResult(
        assertion_type="json_valid",
        passed=True,
        score=1.0,
        details={"parsed_preview": preview, "parsed_type": type(parsed).__name__},
    ))
    return 1.0


# ---------------------------------------------------------------------------
# assert_matches -- regex pattern matching
# ---------------------------------------------------------------------------

def assert_matches(text: str, pattern: str, fullmatch: bool = True) -> float:
    """Check that text matches a regex pattern.

    Args:
        text: The text to check.
        pattern: A regex pattern string.
        fullmatch: If True (default), the entire text must match.
                   If False, the pattern just needs to be found somewhere.

    Returns 1.0 on match, raises AssertionError on no match.

    Examples::

        # single word response
        assert_matches(response, r"\\w+")

        # one of a set of values
        assert_matches(response, r"(low|medium|high)")

        # contains an email somewhere
        assert_matches(response, r"[\\w.+-]+@[\\w-]+\\.[\\w.]+", fullmatch=False)
    """
    text_stripped = text.strip()

    try:
        compiled = re.compile(pattern, re.DOTALL)
    except re.error as e:
        append_result(AssertionResult(
            assertion_type="matches",
            passed=False,
            score=0.0,
            details={"error": f"Invalid regex: {e}", "pattern": pattern},
        ))
        raise AssertionError(f"Invalid regex pattern: {e}")

    if fullmatch:
        match = compiled.fullmatch(text_stripped)
    else:
        match = compiled.search(text_stripped)

    passed = match is not None
    details = {
        "pattern": pattern,
        "fullmatch": fullmatch,
        "text_preview": text_stripped[:200],
    }
    if match:
        details["matched"] = match.group()[:200]

    append_result(AssertionResult(
        assertion_type="matches",
        passed=passed,
        score=1.0 if passed else 0.0,
        details=details,
    ))

    if not passed:
        mode = "fullmatch" if fullmatch else "search"
        raise AssertionError(
            f"Text does not {mode} pattern /{pattern}/: {text_stripped[:100]}"
        )
    return 1.0


# ---------------------------------------------------------------------------
# assert_grounded -- source grounding via LLM judge
# ---------------------------------------------------------------------------

_GROUNDING_PROMPT = """You are a fact-checking auditor. Verify that factual claims in the RESPONSE are supported by the SOURCE document.

SOURCE (ground truth):
---
{source}
---

RESPONSE (to verify):
---
{response}
---

Instructions:
1. Extract every factual claim from the RESPONSE. Focus on: numbers, monetary values, dates, percentages, quantities, measurements, and specific proper nouns.
2. For each claim, classify it as:
   - GROUNDED: directly stated in the SOURCE, or a correct calculation from SOURCE data
   - FABRICATED: not in the SOURCE and not correctly derivable from it
3. Be lenient with format differences. "INR 45,00,000" = "45 lakh" = "4500000". "March 15, 2025" = "15/03/2025" = "2025-03-15". The underlying value matters, not the representation.
4. Ignore generic statements, opinions, or hedging language — only check verifiable facts.
5. If the RESPONSE contains no verifiable factual claims, return score 1.0 with an empty claims list.

Return ONLY this JSON (no markdown fences, no extra text):
{{"claims": [{{"claim": "<exact text from response>", "verdict": "grounded", "reason": "<brief>"}}, {{"claim": "<exact text>", "verdict": "fabricated", "reason": "<brief>"}}], "score": <float 0.0-1.0 where score = grounded_count / total_claims>}}"""


def _parse_grounding_output(raw: str) -> tuple[float, list[dict]]:
    """Parse the grounding judge's structured output."""
    try:
        data = clean_json(raw)
    except ValueError:
        raise ValueError(f"Grounding judge did not return valid JSON: {raw[:300]}")

    score = float(data.get("score", 0.0))
    claims = data.get("claims", [])

    # clamp score
    score = max(0.0, min(1.0, score))

    # validate claims structure
    validated_claims = []
    for c in claims:
        if isinstance(c, dict) and "claim" in c and "verdict" in c:
            validated_claims.append({
                "claim": str(c["claim"]),
                "verdict": str(c.get("verdict", "unknown")),
                "reason": str(c.get("reason", "")),
            })

    return score, validated_claims


def assert_grounded(
    response: str,
    source: str,
    threshold: float = 0.8,
    judge: Callable[[str], str] | None = None,
) -> float:
    """Check that factual claims in response are grounded in the source.

    Uses an LLM judge to decompose the response into factual claims
    and verify each against the source document. Returns the fraction
    of claims that are grounded.

    This is the right assertion for document extraction, summarization,
    and any pipeline where hallucinated numbers/dates/values are dangerous.

    Args:
        response: The LLM output to verify.
        source: The source document (ground truth).
        threshold: Minimum grounding score to pass (default 0.8).
        judge: Optional override for the global judge.

    Returns:
        The grounding score (0.0-1.0).

    Raises:
        AssertionError: If the score is below threshold.
        RuntimeError: If no judge is configured.
    """
    judge_fn = judge or _judge
    if judge_fn is None:
        raise RuntimeError(
            "No LLM judge configured. Call set_judge(fn) first, "
            "or pass judge=fn to assert_grounded()."
        )

    prompt = _GROUNDING_PROMPT.format(
        source=source[:4000],
        response=response[:4000],
    )

    start = time.perf_counter()
    raw_output = judge_fn(prompt)
    latency = (time.perf_counter() - start) * 1000

    try:
        score, claims = _parse_grounding_output(raw_output)
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        append_result(AssertionResult(
            assertion_type="grounded",
            passed=False,
            score=0.0,
            details={
                "error": str(e),
                "raw_output": raw_output[:500],
                "latency_ms": latency,
            },
        ))
        raise AssertionError(f"Grounding judge returned unparseable output: {e}")

    fabricated = [c for c in claims if c["verdict"] == "fabricated"]
    grounded = [c for c in claims if c["verdict"] == "grounded"]
    passed = score >= threshold

    append_result(AssertionResult(
        assertion_type="grounded",
        passed=passed,
        score=score,
        details={
            "threshold": threshold,
            "total_claims": len(claims),
            "grounded_count": len(grounded),
            "fabricated_count": len(fabricated),
            "claims": claims,
            "fabricated": fabricated,
            "response_preview": response[:200],
            "latency_ms": latency,
        },
    ))

    if not passed:
        fab_summary = "; ".join(c["claim"] for c in fabricated[:3])
        raise AssertionError(
            f"Grounding score {score:.3f} < threshold {threshold}. "
            f"Fabricated: {fab_summary}"
        )
    return score
