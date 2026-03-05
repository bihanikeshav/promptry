"""Regression notifications via webhook or email.

Sends alerts when a suite run detects a regression. Supports
Slack/Discord webhooks and SMTP email out of the box.

Configure in promptry.toml:
    [notifications]
    webhook_url = "https://hooks.slack.com/services/..."
    email = "alerts@example.com"
    smtp_host = "smtp.gmail.com"
    smtp_port = 587
    smtp_user = "you@gmail.com"
    smtp_password = "app-password"
"""
from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
import urllib.error
from email.mime.text import MIMEText

from promptry.config import get_config
from promptry.models import SuiteResult

log = logging.getLogger(__name__)


def notify_regression(result: SuiteResult, details: str = ""):
    """Send regression notifications if configured.

    Call this after a suite run that detected a regression.
    Silently does nothing if no notification channels are configured.
    """
    config = get_config()
    notif = config.notifications

    if not notif.webhook_url and not notif.email:
        return

    subject = f"promptry regression: {result.suite_name}"
    body = _build_message(result, details)

    if notif.webhook_url:
        try:
            _send_webhook(notif.webhook_url, subject, body)
        except Exception:
            log.exception("webhook notification failed")

    if notif.email:
        try:
            _send_email(
                to=notif.email,
                subject=subject,
                body=body,
                smtp_host=notif.smtp_host,
                smtp_port=notif.smtp_port,
                smtp_user=notif.smtp_user,
                smtp_password=notif.smtp_password,
            )
        except Exception:
            log.exception("email notification failed")


def _build_message(result: SuiteResult, details: str) -> str:
    lines = [
        f"Suite: {result.suite_name}",
        f"Score: {result.overall_score:.3f}",
        f"Pass: {result.overall_pass}",
    ]
    if result.prompt_name:
        lines.append(f"Prompt: {result.prompt_name} v{result.prompt_version}")
    if result.model_version:
        lines.append(f"Model: {result.model_version}")
    if details:
        lines.append("")
        lines.append(details)
    return "\n".join(lines)


def _send_webhook(url: str, subject: str, body: str):
    """POST to a webhook URL. Works with Slack, Discord, and generic webhooks."""
    if not url.startswith(("https://", "http://")):
        log.warning("webhook URL must start with https:// or http://, skipping")
        return

    # slack and discord both accept {"text": "..."}
    payload = json.dumps({"text": f"*{subject}*\n```\n{body}\n```"}).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                log.warning("webhook returned %d", resp.status)
    except urllib.error.HTTPError as e:
        log.warning("webhook HTTP error: %d %s", e.code, e.reason)
    except urllib.error.URLError as e:
        log.warning("webhook connection failed: %s", e.reason)


def _send_email(to, subject, body, smtp_host, smtp_port, smtp_user, smtp_password):
    """Send a plain text email via SMTP."""
    if not smtp_host:
        log.warning("email configured but no smtp_host set, skipping")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user or "promptry@localhost"
    msg["To"] = to

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.send_message(msg)
