import pytest

from promptry.evaluator import (
    suite, get_suite, list_suites,
    AssertionResult, run_context, append_result, check_all,
)


class TestSuiteRegistration:

    def test_register_suite(self):
        @suite("my_suite")
        def my_test():
            pass

        assert get_suite("my_suite") is not None
        assert get_suite("my_suite").fn is my_test

    def test_list_suites(self):
        @suite("a")
        def test_a():
            pass

        @suite("b")
        def test_b():
            pass

        names = [s.name for s in list_suites()]
        assert "a" in names
        assert "b" in names


class TestRunContext:

    def test_collects_results(self):
        with run_context() as results:
            append_result(AssertionResult(
                assertion_type="test",
                passed=True,
                score=0.9,
            ))
            append_result(AssertionResult(
                assertion_type="test",
                passed=False,
                score=0.3,
            ))

        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    def test_context_cleans_up(self):
        from promptry.evaluator import get_current_results

        with run_context():
            assert get_current_results() is not None

        assert get_current_results() is None

    def test_append_outside_context_is_noop(self):
        append_result(AssertionResult(assertion_type="test", passed=True))


class TestCheckAll:

    def test_all_pass(self):
        def passing():
            append_result(AssertionResult(assertion_type="test", passed=True, score=0.9))
            return 0.9

        with run_context() as results:
            avg = check_all(passing, passing)

        assert avg == pytest.approx(0.9)
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_collects_all_failures(self):
        def pass_check():
            append_result(AssertionResult(assertion_type="test", passed=True, score=1.0))
            return 1.0

        def fail_check_1():
            append_result(AssertionResult(assertion_type="test", passed=False, score=0.0))
            raise AssertionError("first failure")

        def fail_check_2():
            append_result(AssertionResult(assertion_type="test", passed=False, score=0.0))
            raise AssertionError("second failure")

        with run_context() as results:
            with pytest.raises(AssertionError, match="2/3 assertion.*failed"):
                check_all(pass_check, fail_check_1, fail_check_2)

        # all 3 assertions recorded, even though 2 failed
        assert len(results) == 3

    def test_error_summary_includes_all_messages(self):
        def fail_a():
            raise AssertionError("missing keyword: price")

        def fail_b():
            raise AssertionError("schema validation failed")

        with run_context():
            try:
                check_all(fail_a, fail_b)
            except AssertionError as e:
                msg = str(e)
                assert "missing keyword: price" in msg
                assert "schema validation failed" in msg
                assert "2/2" in msg

    def test_handles_non_assertion_errors(self):
        def bad_check():
            raise ValueError("unexpected error")

        with run_context():
            with pytest.raises(AssertionError, match="ValueError"):
                check_all(bad_check)

    def test_empty_checks(self):
        with run_context():
            avg = check_all()
        assert avg == 1.0

    def test_works_inside_suite(self):
        """check_all inside a suite records all results to run_context."""
        from promptry.assertions import assert_contains

        with run_context() as results:
            try:
                check_all(
                    lambda: assert_contains("hello world", ["hello"]),
                    lambda: assert_contains("hello world", ["missing"]),
                    lambda: assert_contains("hello world", ["world"]),
                )
            except AssertionError:
                pass

        # all 3 assertions recorded
        assert len(results) == 3
        assert results[0].passed is True   # "hello" found
        assert results[1].passed is False  # "missing" not found
        assert results[2].passed is True   # "world" found
