from promptry.templates import get_templates, get_categories, run_safety_audit


class TestTemplates:

    def test_has_templates(self):
        templates = get_templates()
        assert len(templates) >= 25

    def test_filter_by_category(self):
        injection = get_templates("prompt_injection")
        assert len(injection) >= 3
        assert all(t.category == "prompt_injection" for t in injection)

    def test_categories(self):
        cats = get_categories()
        assert "prompt_injection" in cats
        assert "jailbreak" in cats
        assert "pii_leakage" in cats
        assert "hallucination" in cats

    def test_each_template_has_required_fields(self):
        for t in get_templates():
            assert t.id, "template missing id"
            assert t.category, f"{t.id} missing category"
            assert t.name, f"{t.id} missing name"
            assert t.prompt, f"{t.id} missing prompt"
            assert t.expect_behavior, f"{t.id} missing expect_behavior"
            assert t.severity in ("critical", "high", "medium"), f"{t.id} bad severity"


class TestSafetyAudit:

    def test_safe_pipeline_passes(self):
        def safe_pipeline(prompt):
            return "I can't help with that request. I'm not able to follow those instructions."

        results = run_safety_audit(safe_pipeline)
        # most should pass since the response is a clear refusal
        pass_rate = sum(1 for r in results if r["passed"]) / len(results)
        assert pass_rate > 0.5

    def test_result_has_score_and_reason(self):
        def safe_pipeline(prompt):
            return "I cannot help with that."

        results = run_safety_audit(safe_pipeline, categories=["prompt_injection"])
        for r in results:
            assert "score" in r
            assert "reason" in r
            assert isinstance(r["score"], float)

    def test_pipeline_exception_handled(self):
        def broken_pipeline(prompt):
            raise RuntimeError("connection failed")

        results = run_safety_audit(broken_pipeline, categories=["jailbreak"])
        assert all(not r["passed"] for r in results)
        assert "Pipeline error" in results[0]["reason"]

    def test_filter_categories(self):
        def noop(prompt):
            return "I cannot do that."

        all_results = run_safety_audit(noop)
        injection_only = run_safety_audit(noop, categories=["prompt_injection"])
        assert len(injection_only) < len(all_results)

    def test_llm_judge_used_when_available(self):
        """When a judge is configured, safety audit uses it."""
        from promptry.assertions import set_judge
        import promptry.assertions as _mod

        def fake_judge(prompt):
            return '{"score": 0.95, "reason": "Safe refusal"}'

        old = _mod._judge
        set_judge(fake_judge)
        try:
            def pipeline(prompt):
                return "I cannot help with that."

            results = run_safety_audit(pipeline, categories=["prompt_injection"])
            # all should pass with the high-scoring judge
            assert all(r["passed"] for r in results)
            assert all(r["score"] == 0.95 for r in results)
        finally:
            _mod._judge = old
