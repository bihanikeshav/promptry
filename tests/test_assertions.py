import pytest
from pydantic import BaseModel

from promptry.evaluator import run_context
from promptry.assertions import (
    assert_schema,
    assert_llm, set_judge, get_judge,
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
