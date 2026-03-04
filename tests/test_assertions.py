import pytest
from pydantic import BaseModel

from promptry.evaluator import run_context
from promptry.assertions import assert_contains, assert_not_contains, assert_schema


# -- contains --

class TestAssertContains:

    def test_all_found(self):
        with run_context() as results:
            score = assert_contains("the cat sat on the mat", ["cat", "mat"])
        assert score == 1.0
        assert results[0].passed is True

    def test_missing_keyword(self):
        with run_context():
            with pytest.raises(AssertionError, match="Missing keywords"):
                assert_contains("hello world", ["hello", "missing"])

    def test_case_insensitive(self):
        with run_context() as results:
            assert_contains("Hello World", ["hello", "world"])
        assert results[0].passed is True

    def test_case_sensitive(self):
        with run_context():
            with pytest.raises(AssertionError):
                assert_contains("Hello World", ["hello"], case_sensitive=True)

    def test_partial_score(self):
        with run_context() as results:
            try:
                assert_contains("hello world", ["hello", "missing", "also_missing"])
            except AssertionError:
                pass
        # 1 out of 3 found
        assert results[0].score == pytest.approx(1 / 3)


# -- not_contains --

class TestAssertNotContains:

    def test_none_found(self):
        with run_context() as results:
            score = assert_not_contains("hello world", ["banana", "apple"])
        assert score == 1.0
        assert results[0].passed is True

    def test_forbidden_found(self):
        with run_context():
            with pytest.raises(AssertionError, match="Found forbidden"):
                assert_not_contains("hello world", ["hello"])


# -- schema --

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

    def test_invalid_json_string(self):
        class MyModel(BaseModel):
            value: int

        with run_context():
            with pytest.raises(AssertionError):
                assert_schema('{"value": "not_an_int"}', MyModel)
