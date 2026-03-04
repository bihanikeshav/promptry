"""Example: using assert_llm with an LLM-as-judge.

This demo shows how to wire up an LLM to grade your pipeline's
responses against criteria you define.

You need an OpenAI API key for this example:
    export OPENAI_API_KEY=sk-...
    pip install openai promptry
    python examples/llm_judge.py

Or swap out the judge for any other provider — Anthropic, local
models, whatever takes a string and returns a string.
"""
from promptry import suite, assert_semantic, assert_llm, set_judge


# ---- wire up your LLM as the judge ----
# uncomment the provider you use:

# --- OpenAI ---
# from openai import OpenAI
# client = OpenAI()
#
# def judge(prompt: str) -> str:
#     r = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[{"role": "user", "content": prompt}],
#     )
#     return r.choices[0].message.content

# --- Anthropic ---
# import anthropic
# client = anthropic.Anthropic()
#
# def judge(prompt: str) -> str:
#     r = client.messages.create(
#         model="claude-haiku-4-5-20251001",
#         max_tokens=256,
#         messages=[{"role": "user", "content": prompt}],
#     )
#     return r.content[0].text

# --- fake judge for demo purposes ---
def judge(prompt: str) -> str:
    """Returns a passing score. Replace with a real LLM."""
    return '{"score": 0.85, "reason": "Response is accurate and grounded"}'


set_judge(judge)


# ---- your pipeline (replace with your real one) ----

def my_pipeline(question: str) -> str:
    return (
        "Photosynthesis is the process by which plants convert sunlight "
        "into chemical energy, producing glucose and oxygen."
    )


# ---- eval suite mixing cheap + LLM checks ----

@suite("quality-check")
def test_rag_quality():
    response = my_pipeline("What is photosynthesis?")

    # fast semantic check
    assert_semantic(response, "Explains how plants convert sunlight into energy")

    # LLM grading — slower but catches nuance
    assert_llm(
        response,
        criteria="Accurately explains the process, uses only factual information, "
                 "no hallucinated details.",
        threshold=0.7,
    )


def pipeline(prompt: str) -> str:
    return my_pipeline(prompt)


if __name__ == "__main__":
    from promptry.runner import run_suite
    result = run_suite("quality-check")

    for test in result.tests:
        status = "PASS" if test.passed else "FAIL"
        print(f"  {status} {test.test_name}")
        for a in test.assertions:
            print(f"    {a.assertion_type} ({a.score:.3f})")

    print(f"\nOverall: {'PASS' if result.overall_pass else 'FAIL'}  "
          f"score: {result.overall_score:.3f}")
