"""Example: chaining assertions into a validation pipeline.

Demonstrates the new assertion types and check_all() for running
every check even when some fail.

    pip install promptry
    python examples/assertion_pipeline.py
"""
from promptry import (
    suite, check_all,
    assert_json_valid, assert_matches, assert_schema, assert_grounded,
    assert_contains, assert_llm,
    clean_json, set_judge,
)
from pydantic import BaseModel


# ---- fake pipeline that returns JSON (replace with your real one) ----

SOURCE_DOCUMENT = """
Tender Reference: RFP-2025-042
Contract Value: INR 45,00,000
Delivery Period: 6 months from date of award
Vendor: Acme Solutions Pvt. Ltd.
Bid Validity: 90 days
Payment Terms: 30% advance, 70% on delivery
"""


def extract_pricing(document: str) -> str:
    """Fake LLM extraction — returns JSON with some data from the source."""
    return """{
        "tender_ref": "RFP-2025-042",
        "contract_value": "INR 45,00,000",
        "delivery_months": 6,
        "vendor": "Acme Solutions Pvt. Ltd.",
        "payment_advance_pct": 30,
        "payment_delivery_pct": 70,
        "risk_level": "low"
    }"""


def classify_document(document: str) -> str:
    """Fake LLM classification — returns a single word."""
    return "tender"


# ---- pydantic model for schema validation ----

class PricingExtract(BaseModel):
    tender_ref: str
    contract_value: str
    delivery_months: int
    vendor: str
    payment_advance_pct: int
    payment_delivery_pct: int
    risk_level: str


# ---- eval suites ----

# 1. Fail-fast pipeline — stops at the first broken gate
@suite("pricing-failfast", description="Sequential gates: JSON -> schema -> content")
def test_pricing_failfast():
    response = extract_pricing(SOURCE_DOCUMENT)

    # gate 1: is it parseable JSON?
    assert_json_valid(response)

    # gate 2: does it match our schema?
    data = clean_json(response)
    assert_schema(data, PricingExtract)

    # gate 3: does it contain expected fields?
    assert_contains(response, ["contract_value", "vendor", "tender_ref"])


# 2. Full-report pipeline — runs everything, shows all failures
@suite("pricing-full", description="Run all checks, report everything that fails")
def test_pricing_full():
    response = extract_pricing(SOURCE_DOCUMENT)
    data = clean_json(response)

    check_all(
        lambda: assert_json_valid(response),
        lambda: assert_schema(data, PricingExtract),
        lambda: assert_contains(response, ["contract_value", "vendor"]),
        lambda: assert_matches(data["risk_level"], r"(low|medium|high)"),
    )


# 3. Document classification — response must be a single word
@suite("doc-classify", description="Classification output must be exactly one word")
def test_classification():
    result = classify_document(SOURCE_DOCUMENT)
    assert_matches(result, r"\w+")
    assert_matches(result, r"(tender|rfp|rfq|eoi|contract)")


# 4. Grounding check — requires an LLM judge
# Uncomment and configure set_judge() to use this one.
#
# @suite("pricing-grounded", description="Check extraction is grounded in source")
# def test_grounding():
#     response = extract_pricing(SOURCE_DOCUMENT)
#     assert_grounded(
#         response=response,
#         source=SOURCE_DOCUMENT,
#         threshold=0.9,  # strict for financial data
#     )


# ---- fake judge for demo ----

def fake_judge(prompt: str) -> str:
    """Returns a grounding result. Replace with a real LLM."""
    import json
    return json.dumps({
        "claims": [
            {"claim": "RFP-2025-042", "verdict": "grounded", "reason": "in source"},
            {"claim": "INR 45,00,000", "verdict": "grounded", "reason": "in source"},
            {"claim": "6 months", "verdict": "grounded", "reason": "in source"},
            {"claim": "Acme Solutions", "verdict": "grounded", "reason": "in source"},
        ],
        "score": 1.0,
    })


set_judge(fake_judge)


# 5. Grounding check with fake judge (runs without API keys)
@suite("pricing-grounded-demo", description="Grounding demo with fake judge")
def test_grounding_demo():
    response = extract_pricing(SOURCE_DOCUMENT)
    assert_grounded(
        response=response,
        source=SOURCE_DOCUMENT,
        threshold=0.8,
    )


if __name__ == "__main__":
    from promptry.runner import run_suite

    suites = [
        "pricing-failfast",
        "pricing-full",
        "doc-classify",
        "pricing-grounded-demo",
    ]

    for name in suites:
        print(f"\n{'='*50}")
        print(f"Suite: {name}")
        print(f"{'='*50}")

        result = run_suite(name)

        for test in result.tests:
            status = "PASS" if test.passed else "FAIL"
            print(f"  {status} {test.test_name} ({test.latency_ms:.0f}ms)")
            for a in test.assertions:
                score_str = f"({a.score:.3f})" if a.score is not None else ""
                a_status = "ok" if a.passed else "FAIL"
                print(f"    {a.assertion_type} {score_str} {a_status}")
            if test.error:
                print(f"    Error: {test.error}")

        print(f"  Overall: {'PASS' if result.overall_pass else 'FAIL'} "
              f"score: {result.overall_score:.3f}")

    print("\n\nDone. Try these next:")
    print("  promptry run pricing-failfast --module examples.assertion_pipeline")
    print("  promptry run pricing-full --module examples.assertion_pipeline")
    print("  promptry run doc-classify --module examples.assertion_pipeline")
