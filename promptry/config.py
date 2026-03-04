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

    def __post_init__(self):
        if not self.db_path:
            self.db_path = str(Path.home() / ".promptry" / "promptry.db")


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
class Config:
    storage: StorageConfig = field(default_factory=StorageConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)


def _find_config_file() -> Path | None:
    candidates = [
        Path.cwd() / "promptry.toml",
        Path.home() / ".promptry" / "config.toml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _apply_env_overrides(config: Config):
    if db := os.environ.get("PROMPTRY_DB"):
        config.storage.db_path = db
    if model := os.environ.get("PROMPTRY_EMBEDDING_MODEL"):
        config.model.embedding_model = model
    if threshold := os.environ.get("PROMPTRY_SEMANTIC_THRESHOLD"):
        config.model.semantic_threshold = float(threshold)


def load_config() -> Config:
    config = Config()

    config_file = _find_config_file()
    if config_file:
        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        if "storage" in data:
            if "db_path" in data["storage"]:
                config.storage.db_path = data["storage"]["db_path"]
        if "model" in data:
            if "embedding_model" in data["model"]:
                config.model.embedding_model = data["model"]["embedding_model"]
            if "semantic_threshold" in data["model"]:
                config.model.semantic_threshold = data["model"]["semantic_threshold"]
        if "monitor" in data:
            if "interval_minutes" in data["monitor"]:
                config.monitor.interval_minutes = data["monitor"]["interval_minutes"]
            if "threshold" in data["monitor"]:
                config.monitor.threshold = data["monitor"]["threshold"]
            if "window" in data["monitor"]:
                config.monitor.window = data["monitor"]["window"]

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
    """For tests only."""
    global _config
    _config = None
