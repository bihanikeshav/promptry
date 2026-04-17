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
from typing import Any, Callable, TYPE_CHECKING, Type

from pydantic import BaseModel, ValidationError

from promptry.evaluator import AssertionResult, append_result

if TYPE_CHECKING:
    from promptry.conversation import Conversation

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


# ---------------------------------------------------------------------------
# tool-use assertions -- evaluate agent traces (lists of tool calls)
# ---------------------------------------------------------------------------

def _normalize_tool_call(item: Any) -> dict:
    """Extract a canonical tool-call dict from various trace formats.

    Accepts:
      - Native format: {"name": ..., "args": [...], "kwargs": {...}}
      - OpenAI:        {"function": {"name": ..., "arguments": "..."}}
                       (arguments may be a JSON string or dict)
      - Anthropic:     {"type": "tool_use", "name": ..., "input": {...}}

    Returns a dict with keys: name (str), args (list), kwargs (dict).
    Raises ValueError if no tool name can be extracted.
    """
    if not isinstance(item, dict):
        raise ValueError(
            f"Tool call entry must be a dict, got {type(item).__name__}"
        )

    # anthropic: {"type": "tool_use", "name": ..., "input": {...}}
    if item.get("type") == "tool_use" and "name" in item:
        raw_input = item.get("input", {}) or {}
        if not isinstance(raw_input, dict):
            raw_input = {}
        return {"name": str(item["name"]), "args": [], "kwargs": dict(raw_input)}

    # openai: {"function": {"name": ..., "arguments": "..."}}
    fn = item.get("function")
    if isinstance(fn, dict) and "name" in fn:
        raw_args = fn.get("arguments", {})
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args) if raw_args else {}
            except (json.JSONDecodeError, ValueError):
                parsed = {}
        else:
            parsed = raw_args or {}
        if not isinstance(parsed, dict):
            parsed = {}
        return {"name": str(fn["name"]), "args": [], "kwargs": dict(parsed)}

    # native format: {"name": ..., "args": [...], "kwargs": {...}}
    if "name" in item:
        args = item.get("args") or []
        kwargs = item.get("kwargs") or {}
        if not isinstance(args, list):
            args = list(args) if hasattr(args, "__iter__") else []
        if not isinstance(kwargs, dict):
            kwargs = {}
        return {"name": str(item["name"]), "args": list(args), "kwargs": dict(kwargs)}

    raise ValueError(
        f"Could not extract tool name from trace entry: {item!r}. "
        f"Expected a dict with 'name', 'function.name', or type 'tool_use'."
    )


def _normalize_trace(trace: list) -> list[dict]:
    """Normalize an entire trace list. Raises ValueError on malformed entries."""
    if not isinstance(trace, list):
        raise ValueError(
            f"Trace must be a list of tool calls, got {type(trace).__name__}"
        )
    return [_normalize_tool_call(item) for item in trace]


def _args_match(expected: list, actual: list) -> bool:
    """Positional args match iff every expected arg appears in the actual list
    in the same order (prefix match). Empty expected always matches."""
    if not expected:
        return True
    if len(expected) > len(actual):
        return False
    return all(a == b for a, b in zip(expected, actual))


def _kwargs_match(expected: dict, actual: dict) -> bool:
    """kwargs partial match: every expected key/value present in actual."""
    if not expected:
        return True
    for k, v in expected.items():
        if k not in actual or actual[k] != v:
            return False
    return True


def assert_tool_called(
    trace: list,
    name: str,
    args: list | None = None,
    kwargs: dict | None = None,
) -> float:
    """Check that a tool with the given name was called at least once.

    Optionally verify that specific positional args and/or keyword args
    were passed. kwargs match is partial — extra kwargs in the actual
    call are fine; all expected kwargs must be present with matching values.

    Args:
        trace: List of tool-call dicts. Accepts native format, OpenAI
               tool_calls, or Anthropic tool_use blocks.
        name: Tool name to look for.
        args: Optional list of expected positional args (prefix match).
        kwargs: Optional dict of expected keyword args (partial match).

    Returns:
        1.0 on pass.

    Raises:
        AssertionError: If no matching call was found.
    """
    normalized = _normalize_trace(trace)
    matches = [c for c in normalized if c["name"] == name]

    passed = False
    reason = ""
    if not matches:
        reason = f"tool '{name}' was never called"
    else:
        for call in matches:
            args_ok = _args_match(args or [], call["args"])
            kwargs_ok = _kwargs_match(kwargs or {}, call["kwargs"])
            if args_ok and kwargs_ok:
                passed = True
                break
        if not passed:
            reason = (
                f"tool '{name}' was called {len(matches)} time(s) but none "
                f"matched args={args!r} kwargs={kwargs!r}"
            )

    tool_names = [c["name"] for c in normalized]
    append_result(AssertionResult(
        assertion_type="tool_called",
        passed=passed,
        score=1.0 if passed else 0.0,
        details={
            "tool_name": name,
            "expected_args": args,
            "expected_kwargs": kwargs,
            "call_count": len(matches),
            "trace_tool_names": tool_names,
        },
    ))

    if not passed:
        raise AssertionError(f"assert_tool_called failed: {reason}")
    return 1.0


def assert_tool_sequence(trace: list, expected_sequence: list[str]) -> float:
    """Check that tools were called in the given order (subsequence match).

    The expected sequence must appear as a subsequence within the trace,
    but not necessarily as consecutive calls. Other tools may be
    interleaved.

    Args:
        trace: List of tool-call dicts.
        expected_sequence: List of tool names that should appear in order.

    Returns:
        1.0 on pass.

    Raises:
        AssertionError: If the sequence is not a subsequence of the trace.
    """
    normalized = _normalize_trace(trace)
    actual_names = [c["name"] for c in normalized]

    # two-pointer subsequence check
    i = 0
    for tool_name in actual_names:
        if i < len(expected_sequence) and tool_name == expected_sequence[i]:
            i += 1
        if i == len(expected_sequence):
            break

    passed = i == len(expected_sequence)
    missing_from = expected_sequence[i:] if not passed else []

    append_result(AssertionResult(
        assertion_type="tool_sequence",
        passed=passed,
        score=1.0 if passed else 0.0,
        details={
            "expected_sequence": list(expected_sequence),
            "actual_sequence": actual_names,
            "matched_through_index": i,
            "missing_from": missing_from,
        },
    ))

    if not passed:
        raise AssertionError(
            f"assert_tool_sequence failed: expected {expected_sequence} "
            f"as a subsequence of {actual_names}, missing from index {i} "
            f"({missing_from!r})"
        )
    return 1.0


def assert_no_tool_called(trace: list, name: str) -> float:
    """Check that a specific tool was never called.

    Useful for safety invariants: "don't call delete_database",
    "don't call send_email outside of the notify flow", etc.

    Args:
        trace: List of tool-call dicts.
        name: Tool name that must not appear.

    Returns:
        1.0 on pass.

    Raises:
        AssertionError: If the tool was called one or more times.
    """
    normalized = _normalize_trace(trace)
    hits = [c for c in normalized if c["name"] == name]
    passed = len(hits) == 0

    append_result(AssertionResult(
        assertion_type="no_tool_called",
        passed=passed,
        score=1.0 if passed else 0.0,
        details={
            "tool_name": name,
            "forbidden_call_count": len(hits),
            "trace_tool_names": [c["name"] for c in normalized],
        },
    ))

    if not passed:
        raise AssertionError(
            f"assert_no_tool_called failed: tool '{name}' was called "
            f"{len(hits)} time(s) but should not have been called"
        )
    return 1.0


# ---------------------------------------------------------------------------
# Conversation-level assertions
# ---------------------------------------------------------------------------

def assert_conversation_length(
    conv: Conversation,
    min_turns: int | None = None,
    max_turns: int | None = None,
) -> float:
    """Check that total turn count is within bounds.

    Useful for detecting runaway agents (too many turns) or conversations
    that ended prematurely.

    Args:
        conv: The Conversation to check.
        min_turns: Minimum acceptable turn count (inclusive).
        max_turns: Maximum acceptable turn count (inclusive).

    Returns 1.0 on pass.
    """
    n = len(conv.turns)
    errors = []
    if min_turns is not None and n < min_turns:
        errors.append(f"only {n} turn(s), expected >= {min_turns}")
    if max_turns is not None and n > max_turns:
        errors.append(f"{n} turn(s), expected <= {max_turns}")

    passed = not errors
    append_result(AssertionResult(
        assertion_type="conversation_length",
        passed=passed,
        score=1.0 if passed else 0.0,
        details={
            "turn_count": n,
            "min_turns": min_turns,
            "max_turns": max_turns,
        },
    ))

    if not passed:
        raise AssertionError(f"Conversation length out of bounds: {'; '.join(errors)}")
    return 1.0


def _run_predicate(predicate: Callable[[str], Any], text: str) -> tuple[bool, str | None]:
    """Run a predicate against one turn's text, isolating its results.

    Swallows assertion results appended to run_context by the predicate
    (those are per-turn internals). We re-emit one summary result per
    conversation-level assertion instead, so the suite report stays
    clean.
    """
    from promptry.evaluator import run_context

    try:
        with run_context():
            predicate(text)
        return True, None
    except AssertionError as e:
        return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def assert_all_assistant_turns(
    conv: Conversation,
    predicate: Callable[[str], Any],
) -> float:
    """Check that a predicate holds for every assistant turn.

    The predicate is any callable that takes a turn's content (str) and
    raises AssertionError on failure. Existing single-turn assertions
    (``assert_contains``, ``assert_semantic``, etc.) can be wrapped in a
    lambda::

        assert_all_assistant_turns(
            conv,
            lambda t: assert_contains(t, ["weather"]),
        )

    Returns the fraction of assistant turns that pass.
    """
    turns = conv.assistant_turns()
    if not turns:
        append_result(AssertionResult(
            assertion_type="all_assistant_turns",
            passed=False,
            score=0.0,
            details={"error": "no assistant turns in conversation"},
        ))
        raise AssertionError("No assistant turns to check")

    passed_count = 0
    failures: list[dict] = []
    for i, turn in enumerate(turns):
        ok, err = _run_predicate(predicate, turn.content)
        if ok:
            passed_count += 1
        else:
            failures.append({
                "turn_index": i,
                "content_preview": turn.content[:200],
                "error": err,
            })

    score = passed_count / len(turns)
    passed = len(failures) == 0
    append_result(AssertionResult(
        assertion_type="all_assistant_turns",
        passed=passed,
        score=score,
        details={
            "total_turns": len(turns),
            "passed_turns": passed_count,
            "failed_turns": len(failures),
            "failures": failures,
        },
    ))

    if not passed:
        first_errs = "; ".join(f"turn {f['turn_index']}: {f['error']}" for f in failures[:3])
        raise AssertionError(
            f"{len(failures)}/{len(turns)} assistant turn(s) failed predicate: {first_errs}"
        )
    return score


def assert_any_assistant_turn(
    conv: Conversation,
    predicate: Callable[[str], Any],
) -> float:
    """Check that at least one assistant turn satisfies the predicate.

    Useful when you expect the bot to eventually produce a particular
    answer but don't care which turn it came on.

    Returns 1.0 if any turn passes; raises otherwise.
    """
    turns = conv.assistant_turns()
    if not turns:
        append_result(AssertionResult(
            assertion_type="any_assistant_turn",
            passed=False,
            score=0.0,
            details={"error": "no assistant turns in conversation"},
        ))
        raise AssertionError("No assistant turns to check")

    errors: list[str] = []
    for i, turn in enumerate(turns):
        ok, err = _run_predicate(predicate, turn.content)
        if ok:
            append_result(AssertionResult(
                assertion_type="any_assistant_turn",
                passed=True,
                score=1.0,
                details={
                    "matched_turn_index": i,
                    "total_turns": len(turns),
                    "matched_preview": turn.content[:200],
                },
            ))
            return 1.0
        errors.append(f"turn {i}: {err}")

    append_result(AssertionResult(
        assertion_type="any_assistant_turn",
        passed=False,
        score=0.0,
        details={
            "total_turns": len(turns),
            "errors": errors,
        },
    ))
    raise AssertionError(
        f"No assistant turn satisfied predicate across {len(turns)} turn(s)"
    )


def assert_conversation_coherent(
    conv: Conversation,
    threshold: float = 0.5,
) -> float:
    """Check consecutive assistant turns have semantic continuity.

    Uses the same embedding model as ``assert_semantic``. Computes cosine
    similarity between each pair of consecutive assistant turns and
    requires every pair to be >= ``threshold``. A low threshold (default
    0.5) is usually right -- coherence just means "on the same topic",
    not "nearly identical".

    Returns the minimum pairwise similarity. Raises if below threshold.
    Requires ``promptry[semantic]``.
    """
    turns = conv.assistant_turns()
    if len(turns) < 2:
        # nothing to compare -- trivially coherent
        append_result(AssertionResult(
            assertion_type="conversation_coherent",
            passed=True,
            score=1.0,
            details={"total_turns": len(turns), "note": "fewer than 2 assistant turns"},
        ))
        return 1.0

    model = _get_model()
    from sentence_transformers.util import cos_sim  # guarded by _get_model

    texts = [t.content for t in turns]
    embeddings = model.encode(texts)

    pairwise: list[float] = []
    for i in range(len(turns) - 1):
        sim = float(cos_sim(embeddings[i], embeddings[i + 1])[0][0])
        pairwise.append(sim)

    min_sim = min(pairwise)
    passed = min_sim >= threshold
    worst_idx = pairwise.index(min_sim)

    append_result(AssertionResult(
        assertion_type="conversation_coherent",
        passed=passed,
        score=min_sim,
        details={
            "threshold": threshold,
            "pairwise_similarities": pairwise,
            "min_similarity": min_sim,
            "worst_pair_indices": [worst_idx, worst_idx + 1],
        },
    ))

    if not passed:
        raise AssertionError(
            f"Conversation incoherent: min pairwise similarity "
            f"{min_sim:.3f} < threshold {threshold} "
            f"(between assistant turns {worst_idx} and {worst_idx + 1})"
        )
    return min_sim


def assert_no_repetition(
    conv: Conversation,
    similarity_threshold: float = 0.95,
) -> float:
    """Check that no two assistant turns are nearly identical.

    Loops and stuck agents often repeat themselves verbatim or with minor
    rewording. This computes pairwise cosine similarity between all
    assistant turns and fails if any pair exceeds ``similarity_threshold``.

    Returns the maximum pairwise similarity (lower is better). Raises if
    any pair is above the threshold. Requires ``promptry[semantic]``.
    """
    turns = conv.assistant_turns()
    if len(turns) < 2:
        append_result(AssertionResult(
            assertion_type="no_repetition",
            passed=True,
            score=0.0,
            details={"total_turns": len(turns), "note": "fewer than 2 assistant turns"},
        ))
        return 0.0

    model = _get_model()
    from sentence_transformers.util import cos_sim  # guarded by _get_model

    texts = [t.content for t in turns]
    embeddings = model.encode(texts)

    max_sim = 0.0
    worst_pair: tuple[int, int] | None = None
    for i in range(len(turns)):
        for j in range(i + 1, len(turns)):
            sim = float(cos_sim(embeddings[i], embeddings[j])[0][0])
            if sim > max_sim:
                max_sim = sim
                worst_pair = (i, j)

    passed = max_sim < similarity_threshold

    append_result(AssertionResult(
        assertion_type="no_repetition",
        passed=passed,
        score=max_sim,
        details={
            "similarity_threshold": similarity_threshold,
            "max_similarity": max_sim,
            "worst_pair_indices": list(worst_pair) if worst_pair else None,
            "total_turns": len(turns),
        },
    ))

    if not passed:
        i, j = worst_pair  # type: ignore[misc]
        raise AssertionError(
            f"Repetition detected: assistant turns {i} and {j} have "
            f"similarity {max_sim:.3f} >= threshold {similarity_threshold}"
        )
    return max_sim
