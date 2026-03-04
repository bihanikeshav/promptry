"""Config loading for promptry.

Looks for config in this order:
  1. Built-in defaults
  2. promptry.toml in the current directory
  3. ~/.promptry/config.toml
  4. Environment variables (PROMPTRY_DB, PROMPTRY_EMBEDDING_MODEL, etc.)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class StorageConfig:
    db_path: str = ""
    mode: str = "sync"  # "sync", "async", or "off"

    def __post_init__(self):
        if not self.db_path:
            self.db_path = str(Path.home() / ".promptry" / "promptry.db")
        if self.mode not in ("sync", "async", "off"):
            raise ValueError(f"storage.mode must be sync, async, or off (got '{self.mode}')")


@dataclass
class TrackingConfig:
    sample_rate: float = 1.0           # for track() -- 1.0 means every call
    context_sample_rate: float = 1.0   # for track_context() -- set lower in prod


@dataclass
class ModelConfig:
    embedding_model: str = "all-MiniLM-L6-v2"
    semantic_threshold: float = 0.8


@dataclass
class MonitorConfig:
    interval_minutes: int = 1440  # daily
    threshold: float = 0.05
    window: int = 30


@dataclass
class NotificationsConfig:
    webhook_url: str = ""
    email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""


@dataclass
class Config:
    storage: StorageConfig = field(default_factory=StorageConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)


def _find_config_file() -> Path | None:
    candidates = [
        Path.cwd() / "promptry.toml",
        Path.home() / ".promptry" / "config.toml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _apply_toml(config: Config, data: dict):
    """Apply a parsed TOML dict onto the config."""
    if "storage" in data:
        s = data["storage"]
        if "db_path" in s:
            config.storage.db_path = s["db_path"]
        if "mode" in s:
            config.storage.mode = s["mode"]

    if "tracking" in data:
        t = data["tracking"]
        if "sample_rate" in t:
            config.tracking.sample_rate = float(t["sample_rate"])
        if "context_sample_rate" in t:
            config.tracking.context_sample_rate = float(t["context_sample_rate"])

    if "model" in data:
        m = data["model"]
        if "embedding_model" in m:
            config.model.embedding_model = m["embedding_model"]
        if "semantic_threshold" in m:
            config.model.semantic_threshold = float(m["semantic_threshold"])

    if "monitor" in data:
        mon = data["monitor"]
        if "interval_minutes" in mon:
            config.monitor.interval_minutes = int(mon["interval_minutes"])
        if "threshold" in mon:
            config.monitor.threshold = float(mon["threshold"])
        if "window" in mon:
            config.monitor.window = int(mon["window"])

    if "notifications" in data:
        n = data["notifications"]
        if "webhook_url" in n:
            config.notifications.webhook_url = n["webhook_url"]
        if "email" in n:
            config.notifications.email = n["email"]
        if "smtp_host" in n:
            config.notifications.smtp_host = n["smtp_host"]
        if "smtp_port" in n:
            config.notifications.smtp_port = int(n["smtp_port"])
        if "smtp_user" in n:
            config.notifications.smtp_user = n["smtp_user"]
        if "smtp_password" in n:
            config.notifications.smtp_password = n["smtp_password"]


def _apply_env_overrides(config: Config):
    if db := os.environ.get("PROMPTRY_DB"):
        config.storage.db_path = db
    if mode := os.environ.get("PROMPTRY_STORAGE_MODE"):
        config.storage.mode = mode
    if model := os.environ.get("PROMPTRY_EMBEDDING_MODEL"):
        config.model.embedding_model = model
    if threshold := os.environ.get("PROMPTRY_SEMANTIC_THRESHOLD"):
        config.model.semantic_threshold = float(threshold)
    if webhook := os.environ.get("PROMPTRY_WEBHOOK_URL"):
        config.notifications.webhook_url = webhook
    if smtp_pw := os.environ.get("PROMPTRY_SMTP_PASSWORD"):
        config.notifications.smtp_password = smtp_pw


def load_config() -> Config:
    config = Config()

    config_file = _find_config_file()
    if config_file:
        with open(config_file, "rb") as f:
            data = tomllib.load(f)
        _apply_toml(config, data)

    _apply_env_overrides(config)
    return config


# loaded once on first access
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config():
    global _config
    _config = None
