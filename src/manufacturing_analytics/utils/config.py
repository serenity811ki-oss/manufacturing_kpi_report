"""
config.py
=========
Loads and caches the project's central YAML configuration
(``config/config.yaml``) so every module works from a single source of
truth instead of hard-coded constants.

Also provides configuration validation and resolution utilities.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from manufacturing_analytics.utils.logger import get_logger

logger = get_logger(__name__)

# Project root = two levels up from src/manufacturing_analytics/utils/
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


@lru_cache(maxsize=1)
def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load ``config.yaml`` into a dictionary (cached after first call).

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.

    Returns
    -------
    dict
        Parsed configuration.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.
    ConfigError
        If the configuration file is invalid YAML.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {path}")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {str(e)}") from e

    if not isinstance(config, dict):
        raise ConfigError(f"Configuration must be a dictionary, got {type(config)}")

    logger.info("Loaded configuration from {}", path)
    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Validate configuration structure and required sections.

    Parameters
    ----------
    config : dict
        Configuration dictionary

    Returns
    -------
    list[str]
        List of validation error messages (empty if valid)
    """
    from manufacturing_analytics.utils.validators import ConfigValidator
    return ConfigValidator.validate(config)


def resolve_path(relative_path: str | Path) -> Path:
    """Resolve a path from ``config.yaml`` relative to the project root."""
    return PROJECT_ROOT / relative_path


def get_config_section(config: dict[str, Any], section: str) -> dict[str, Any]:
    """
    Safely get a configuration section with validation.

    Parameters
    ----------
    config : dict
        Configuration dictionary
    section : str
        Section name to retrieve

    Returns
    -------
    dict
        The requested section or empty dict if not found

    Raises
    ------
    ConfigError
        If section exists but is not a dictionary
    """
    if section not in config:
        logger.warning("Configuration section '{}' not found, using defaults", section)
        return {}

    section_data = config[section]
    if not isinstance(section_data, dict):
        raise ConfigError(f"Configuration section '{section}' must be a dict, "
                         f"got {type(section_data)}")
    
    return section_data

