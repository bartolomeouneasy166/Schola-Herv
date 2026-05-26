"""
Configuration loader for Schola-herv.
Reads config.yaml and environment variables.
"""

import copy
import os
from pathlib import Path
from typing import Any, Dict

import yaml

# Default locations to search for config.yaml
SEARCH_PATHS = [
    Path.cwd() / "config.yaml",           # current working directory
    Path(__file__).parent.parent / "config.yaml"  # project root (if running from package)
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "user_agent": "Schola-herv/1.0",
    "rate_limits": {
        "arxiv": 1.0,
        "pubmed": 0.5,
        "crossref": 0.5,
        "unpaywall": 1.0,
        "default": 2.0,
    },
    "download": {
        "max_concurrent": 10,
        "retry_attempts": 3,
        "retry_delay": 5,
        "timeout": 60,
    },
    "extraction": {
        "min_text_length": 500,
        "ocr_fallback": False,
        "output_format": "jsonl",
    },
}


def _find_config_file() -> Path | None:
    """Return the first existing config.yaml from search paths."""
    for path in SEARCH_PATHS:
        if path.exists():
            return path
    return None


def _merge_env_overrides(config: Dict[str, Any], prefix: str = "SCHOLAHERV_") -> Dict[str, Any]:
    """
    Override config keys with environment variables.
    Env vars like SCHOLAHERV_DOWNLOAD__MAX_CONCURRENT become download.max_concurrent.
    Double underscore represents nested access.
    """
    for env_key, value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        # Remove prefix and split by '__'
        key_path = env_key[len(prefix):].lower().split("__")
        if not key_path:
            continue
        # Walk into nested dict and set the value
        d = config
        for part in key_path[:-1]:
            d = d.setdefault(part, {})
        try:
            # Convert to appropriate type (int, float, bool, or leave as string)
            if value.lower() in ("true", "false"):
                typed_value = value.lower() == "true"
            else:
                try:
                    typed_value = int(value)
                except ValueError:
                    try:
                        typed_value = float(value)
                    except ValueError:
                        typed_value = value
            d[key_path[-1]] = typed_value
        except Exception:
            pass
    return config


class Config:
    """Configuration holder with attribute access."""
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getattr__(self, key: str) -> Any:
        if key in self._data:
            value = self._data[key]
            if isinstance(value, dict):
                return Config(value)
            return value
        raise AttributeError(f"No such config key: {key}")

    def get(self, key: str, default: Any = None) -> Any:
        """Return the config value for *key*, or *default* if not present."""
        try:
            value = self._data[key]
            if isinstance(value, dict):
                return Config(value)
            return value
        except KeyError:
            return default

    def __repr__(self):
        return f"Config({self._data})"


def load_config(config_path: Path = None) -> Config:
    """Load configuration from YAML file and environment overrides."""
    config_dict = copy.deepcopy(DEFAULT_CONFIG)

    if config_path is None:
        config_path = _find_config_file()

    if config_path and config_path.exists():
        with open(config_path, "r") as f:
            file_config = yaml.safe_load(f)
            if file_config:
                # Shallow merge (nested dicts will be merged recursively)
                _deep_merge(config_dict, file_config)

    config_dict = _merge_env_overrides(config_dict)
    return Config(config_dict)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Recursively merge override into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
