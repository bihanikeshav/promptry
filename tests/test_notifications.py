import json
from unittest.mock import patch, MagicMock

import pytest

from promptry.models import SuiteResult, TestResult
from promptry.notifications import notify_regression, _build_message, _send_webhook


@pytest.fixture
def failing_result():
    return SuiteResult(
        suite_name="rag-regression",
        tests=[TestResult(test_name="test_quality", passed=False, assertions=[], error="score too low")],
        overall_pass=False,
        overall_score=0.65,
        prompt_name="rag-qa",
        prompt_version=3,
        model_version="gpt-4o",
    )


class TestBuildMessage:

    def test_basic_message(self, failing_result):
        msg = _build_message(failing_result, "")
        assert "rag-regression" in msg
        assert "0.650" in msg
        assert "False" in msg

    def test_includes_prompt_info(self, failing_result):
        msg = _build_message(failing_result, "")
        assert "rag-qa" in msg
        assert "v3" in msg

    def test_includes_model(self, failing_result):
        msg = _build_message(failing_result, "")
        assert "gpt-4o" in msg

    def test_includes_details(self, failing_result):
        msg = _build_message(failing_result, "Drift: scores trending down")
        assert "Drift:" in msg
        assert "trending down" in msg


class TestNotifyRegression:

    def test_no_config_does_nothing(self, failing_result, monkeypatch):
        """No webhook or email configured, should silently return."""
        monkeypatch.setenv("PROMPTRY_WEBHOOK_URL", "")
        from promptry.config import reset_config
        reset_config()
        # should not raise
        notify_regression(failing_result)
        reset_config()

    @patch("promptry.notifications._send_webhook")
    def test_calls_webhook(self, mock_webhook, failing_result, monkeypatch):
        monkeypatch.setenv("PROMPTRY_WEBHOOK_URL", "https://hooks.slack.com/test")
        from promptry.config import reset_config
        reset_config()
        notify_regression(failing_result)
        mock_webhook.assert_called_once()
        reset_config()

    @patch("promptry.notifications._send_webhook")
    def test_webhook_failure_does_not_raise(self, mock_webhook, failing_result, monkeypatch):
        mock_webhook.side_effect = Exception("connection failed")
        monkeypatch.setenv("PROMPTRY_WEBHOOK_URL", "https://hooks.slack.com/test")
        from promptry.config import reset_config
        reset_config()
        # should not raise despite webhook failure
        notify_regression(failing_result)
        reset_config()


class TestSendWebhook:

    def test_rejects_bad_url_scheme(self):
        """URLs that aren't http/https should be skipped."""
        # should not raise, just log and return
        _send_webhook("file:///etc/passwd", "test", "body")
