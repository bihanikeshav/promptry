from promptry.evaluator import (
    suite, get_suite, list_suites,
    AssertionResult, run_context, append_result,
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
