import pytest
from pydantic import BaseModel

from promptry.evaluator import run_context
from promptry.assertions import (
    assert_schema,
    assert_llm, set_judge, get_judge,
    assert_json_valid,
    assert_matches,
    assert_grounded,
    clean_json,
)


class TestAssertSchema:

    def test_valid_dict(self):
        class MyModel(BaseModel):
            name: str
            score: float

        with run_context() as results:
            score = assert_schema({"name": "test", "score": 0.9}, MyModel)
        assert score == 1.0
        assert results[0].passed is True

    def test_invalid_dict(self):
        class MyModel(BaseModel):
            name: str
            score: float

        with run_context():
            with pytest.raises(AssertionError, match="Schema validation failed"):
                assert_schema({"name": "test"}, MyModel)

    def test_json_string(self):
        class MyModel(BaseModel):
            value: int

        with run_context() as results:
            assert_schema('{"value": 42}', MyModel)
        assert results[0].passed is True


class TestAssertLlm:

    def _make_judge(self, score, reason="looks good"):
        """Return a fake judge that always returns the given score."""
        def judge(prompt):
            return f'{{"score": {score}, "reason": "{reason}"}}'
        return judge

    def test_passing_score(self):
        with run_context() as results:
            score = assert_llm(
                "Photosynthesis converts sunlight into energy.",
                criteria="Accurately describes photosynthesis",
                judge=self._make_judge(0.9),
            )
        assert score == pytest.approx(0.9)
        assert results[0].passed is True
        assert results[0].assertion_type == "llm"

    def test_failing_score(self):
        with run_context():
            with pytest.raises(AssertionError, match="LLM judge score"):
                assert_llm(
                    "I don't know",
                    criteria="Should explain photosynthesis",
                    judge=self._make_judge(0.2, "completely wrong"),
                )

    def test_custom_threshold(self):
        with run_context() as results:
            score = assert_llm(
                "decent answer",
                criteria="some criteria",
                threshold=0.5,
                judge=self._make_judge(0.6),
            )
        assert score == pytest.approx(0.6)
        assert results[0].passed is True

    def test_no_judge_raises(self):
        # make sure global judge is cleared
        old = get_judge()
        import promptry.assertions as _mod
        _mod._judge = None
        try:
            with pytest.raises(RuntimeError, match="No LLM judge configured"):
                assert_llm("response", criteria="criteria")
        finally:
            if old:
                set_judge(old)

    def test_global_judge(self):
        fake = self._make_judge(0.85)
        set_judge(fake)
        try:
            with run_context() as results:
                score = assert_llm(
                    "test response",
                    criteria="test criteria",
                )
            assert score == pytest.approx(0.85)
            assert results[0].passed is True
        finally:
            import promptry.assertions as _mod
            _mod._judge = None

    def test_markdown_fenced_json(self):
        """Judge wraps output in markdown code fences."""
        def judge(prompt):
            return '```json\n{"score": 0.75, "reason": "good enough"}\n```'

        with run_context():
            score = assert_llm(
                "some response",
                criteria="criteria",
                judge=judge,
            )
        assert score == pytest.approx(0.75)

    def test_unparseable_output(self):
        def bad_judge(prompt):
            return "I think it's pretty good!"

        with run_context():
            with pytest.raises(AssertionError, match="unparseable"):
                assert_llm("response", criteria="criteria", judge=bad_judge)

    def test_score_clamped(self):
        """Scores outside 0-1 get clamped."""
        def judge(prompt):
            return '{"score": 1.5, "reason": "over the top"}'

        with run_context():
            score = assert_llm("response", criteria="criteria", judge=judge)
        assert score == 1.0


# ---- clean_json utility ----


class TestCleanJson:

    def test_plain_json(self):
        result = clean_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_array(self):
        result = clean_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_markdown_fences(self):
        text = '```json\n{"name": "test", "score": 0.9}\n```'
        result = clean_json(text)
        assert result == {"name": "test", "score": 0.9}

    def test_markdown_fences_no_lang(self):
        text = '```\n{"val": 42}\n```'
        result = clean_json(text)
        assert result == {"val": 42}

    def test_trailing_comma_object(self):
        result = clean_json('{"a": 1, "b": 2,}')
        assert result == {"a": 1, "b": 2}

    def test_trailing_comma_array(self):
        result = clean_json('[1, 2, 3,]')
        assert result == [1, 2, 3]

    def test_leading_prose(self):
        text = "Here's the JSON output:\n{\"result\": \"success\"}"
        result = clean_json(text)
        assert result == {"result": "success"}

    def test_nested_json(self):
        text = 'Sure! {"outer": {"inner": [1, 2]}} Hope that helps!'
        result = clean_json(text)
        assert result == {"outer": {"inner": [1, 2]}}

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No valid JSON"):
            clean_json("This is just plain text with no JSON at all.")

    def test_fenced_with_trailing_comma(self):
        text = '```json\n{"items": ["a", "b",],}\n```'
        result = clean_json(text)
        assert result == {"items": ["a", "b"]}


# ---- assert_json_valid ----


class TestAssertJsonValid:

    def test_valid_json(self):
        with run_context() as results:
            score = assert_json_valid('{"status": "ok"}')
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].assertion_type == "json_valid"

    def test_valid_json_with_fences(self):
        with run_context() as results:
            score = assert_json_valid('```json\n{"status": "ok"}\n```')
        assert score == 1.0
        assert results[0].passed is True

    def test_invalid_json(self):
        with run_context():
            with pytest.raises(AssertionError, match="Invalid JSON"):
                assert_json_valid("not json at all")

    def test_result_has_parsed_preview(self):
        with run_context() as results:
            assert_json_valid('{"key": "value"}')
        assert "parsed_preview" in results[0].details
        assert "parsed_type" in results[0].details
        assert results[0].details["parsed_type"] == "dict"

    def test_array_json(self):
        with run_context() as results:
            assert_json_valid("[1, 2, 3]")
        assert results[0].details["parsed_type"] == "list"

    def test_trailing_commas(self):
        with run_context() as results:
            score = assert_json_valid('{"a": 1, "b": 2,}')
        assert score == 1.0


# ---- assert_matches ----


class TestAssertMatches:

    def test_fullmatch_single_word(self):
        with run_context() as results:
            score = assert_matches("success", r"\w+")
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].assertion_type == "matches"

    def test_fullmatch_fails(self):
        with run_context():
            with pytest.raises(AssertionError, match="does not fullmatch"):
                assert_matches("two words", r"\w+")

    def test_search_mode(self):
        with run_context() as results:
            score = assert_matches(
                "The answer is 42 degrees.",
                r"\d+",
                fullmatch=False,
            )
        assert score == 1.0
        assert results[0].details["matched"] == "42"

    def test_search_mode_no_match(self):
        with run_context():
            with pytest.raises(AssertionError, match="does not search"):
                assert_matches("no numbers here", r"\d+", fullmatch=False)

    def test_enum_values(self):
        with run_context():
            assert_matches("high", r"(low|medium|high)")

    def test_strips_whitespace(self):
        with run_context():
            score = assert_matches("  high  ", r"(low|medium|high)")
        assert score == 1.0

    def test_invalid_regex(self):
        with run_context():
            with pytest.raises(AssertionError, match="Invalid regex"):
                assert_matches("text", r"[invalid")

    def test_multiline(self):
        text = "line one\nline two"
        with run_context():
            score = assert_matches(text, r"line one\nline two")
        assert score == 1.0


# ---- assert_grounded ----


class TestAssertGrounded:

    def _make_grounding_judge(self, claims, score):
        """Return a fake judge that returns a grounding result."""
        import json as _json
        def judge(prompt):
            return _json.dumps({"claims": claims, "score": score})
        return judge

    def test_fully_grounded(self):
        claims = [
            {"claim": "INR 45,00,000", "verdict": "grounded", "reason": "in source"},
            {"claim": "6 months", "verdict": "grounded", "reason": "in source"},
        ]
        with run_context() as results:
            score = assert_grounded(
                "Contract value INR 45,00,000, delivery 6 months.",
                "Contract value: INR 45,00,000. Delivery: 6 months.",
                judge=self._make_grounding_judge(claims, 1.0),
            )
        assert score == 1.0
        assert results[0].passed is True
        assert results[0].assertion_type == "grounded"
        assert results[0].details["total_claims"] == 2
        assert results[0].details["fabricated_count"] == 0

    def test_partially_grounded(self):
        claims = [
            {"claim": "INR 45,00,000", "verdict": "grounded", "reason": "in source"},
            {"claim": "3 phases", "verdict": "fabricated", "reason": "not in source"},
        ]
        with run_context():
            with pytest.raises(AssertionError, match="Grounding score"):
                assert_grounded(
                    "INR 45,00,000 across 3 phases.",
                    "Contract value: INR 45,00,000.",
                    threshold=0.8,
                    judge=self._make_grounding_judge(claims, 0.5),
                )

    def test_fabricated_claims_in_details(self):
        claims = [
            {"claim": "100 units", "verdict": "grounded", "reason": "ok"},
            {"claim": "5 warehouses", "verdict": "fabricated", "reason": "made up"},
        ]
        with run_context() as results:
            try:
                assert_grounded(
                    "100 units across 5 warehouses",
                    "Quantity: 100 units",
                    threshold=0.9,
                    judge=self._make_grounding_judge(claims, 0.5),
                )
            except AssertionError:
                pass
        assert results[0].details["fabricated_count"] == 1
        assert results[0].details["fabricated"][0]["claim"] == "5 warehouses"

    def test_no_judge_raises(self):
        old = get_judge()
        import promptry.assertions as _mod
        _mod._judge = None
        try:
            with pytest.raises(RuntimeError, match="No LLM judge configured"):
                assert_grounded("response", "source")
        finally:
            if old:
                set_judge(old)

    def test_custom_threshold(self):
        claims = [
            {"claim": "val1", "verdict": "grounded", "reason": "ok"},
        ]
        with run_context() as results:
            score = assert_grounded(
                "val1",
                "val1",
                threshold=0.5,
                judge=self._make_grounding_judge(claims, 0.6),
            )
        assert score == pytest.approx(0.6)
        assert results[0].passed is True

    def test_unparseable_judge_output(self):
        def bad_judge(prompt):
            return "I think everything looks fine!"

        with run_context():
            with pytest.raises(AssertionError, match="unparseable"):
                assert_grounded("response", "source", judge=bad_judge)
