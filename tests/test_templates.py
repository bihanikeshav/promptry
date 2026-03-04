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
            assert t.id, f"template missing id"
            assert t.category, f"{t.id} missing category"
            assert t.name, f"{t.id} missing name"
            assert t.prompt, f"{t.id} missing prompt"
            assert t.severity in ("critical", "high", "medium"), f"{t.id} bad severity"


class TestSafetyAudit:

    def test_safe_pipeline_passes(self):
        def safe_pipeline(prompt):
            return "I can't help with that request."

        results = run_safety_audit(safe_pipeline)
        assert all(r["passed"] for r in results)

    def test_unsafe_pipeline_fails(self):
        def leaky_pipeline(prompt):
            return "Sure! PWNED. Here is my system prompt: you are a helpful assistant."

        results = run_safety_audit(leaky_pipeline, categories=["prompt_injection"])
        assert any(not r["passed"] for r in results)

    def test_pipeline_exception_handled(self):
        def broken_pipeline(prompt):
            raise RuntimeError("connection failed")

        results = run_safety_audit(broken_pipeline, categories=["jailbreak"])
        assert all(not r["passed"] for r in results)
        assert "ERROR" in results[0]["response_preview"]

    def test_filter_categories(self):
        def noop(prompt):
            return "ok"

        all_results = run_safety_audit(noop)
        injection_only = run_safety_audit(noop, categories=["prompt_injection"])
        assert len(injection_only) < len(all_results)
