"""Feedback analysis -- surface patterns from user downvotes.

Uses an LLM judge (if configured) to group complaints into patterns,
or returns raw stats when no judge is available.
"""
from __future__ import annotations

from typing import Callable


def analyze_votes(
    name: str,
    days: int = 30,
    judge: Callable[[str], str] | None = None,
    storage=None,
) -> dict:
    """Analyze downvote patterns using an LLM judge.

    Returns: {
        "prompt_name": str,
        "total_downvotes": int,
        "analysis": str,  # LLM-generated summary of patterns
        "messages": [str],  # the downvote messages analyzed
    }
    """
    if storage is None:
        from promptry.storage import get_storage
        storage = get_storage()

    votes = storage.get_votes(prompt_name=name, days=days, limit=1000)
    downvotes = [v for v in votes if v["score"] == -1]

    messages = [v["message"] for v in downvotes if v.get("message")]
    response_previews = [
        v["response"][:200] for v in downvotes if v.get("response")
    ]

    result: dict = {
        "prompt_name": name,
        "total_downvotes": len(downvotes),
        "analysis": "",
        "messages": messages,
    }

    if not downvotes:
        result["analysis"] = "No downvotes found in the given time window."
        return result

    if judge is None:
        result["analysis"] = (
            f"{len(downvotes)} downvote(s) found. "
            f"{len(messages)} with comments. "
            "Configure a judge to get pattern analysis."
        )
        return result

    # Build analysis prompt
    items = []
    for v in downvotes:
        entry = f"Response: {v['response'][:200]}"
        if v.get("message"):
            entry += f"\nUser comment: {v['message']}"
        items.append(entry)

    analysis_prompt = (
        "Analyze these user complaints about an LLM's responses. "
        "Group them into patterns and summarize what's wrong. "
        "For each pattern, give the count and representative examples.\n\n"
        + "\n---\n".join(items)
    )

    try:
        analysis = judge(analysis_prompt)
        result["analysis"] = analysis
    except Exception as exc:
        result["analysis"] = f"Judge analysis failed: {exc}"

    return result
