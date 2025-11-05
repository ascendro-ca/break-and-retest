"""
Configuration utilities for Break & Retest strategy

Provides utilities for loading and overriding configuration values
from config.json via command-line arguments.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from config.json

    Args:
        config_path: Path to config.json (default: same directory as this file)

    Returns:
        Dict with configuration values
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.json"

    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    else:
        # Default config if file doesn't exist
        return {"tickers": ["AAPL", "AMZN", "META", "MSFT", "NVDA", "TSLA", "SPOT", "UBER"]}


def parse_config_value(value: str) -> Any:
    """
    Parse a config value string to appropriate Python type

    Args:
        value: String value to parse

    Returns:
        Parsed value (bool, int, float, or str)
    """
    value = value.strip()

    # Boolean
    if value.lower() in ("true", "false"):
        return value.lower() == "true"

    # Number (int or float)
    if value.replace(".", "").replace("-", "").isdigit():
        return float(value) if "." in value else int(value)

    # String
    return value


def apply_config_overrides(
    config: Dict[str, Any], overrides: List[str], verbose: bool = True
) -> Dict[str, Any]:
    """
    Apply command-line config overrides to a config dict

    Args:
        config: Configuration dict to modify (will be modified in-place)
        overrides: List of "KEY=VALUE" override strings
        verbose: If True, print override changes

    Returns:
        Modified config dict (same object as input)

    Example:
        >>> config = load_config()
        >>> overrides = ["feature_level0_enable_vwap_check=false", "initial_capital=10000"]
        >>> apply_config_overrides(config, overrides)
    """
    if not overrides:
        return config

    if verbose:
        print("Applying config overrides:")

    for override in overrides:
        if "=" not in override:
            if verbose:
                print(f"  Warning: Invalid override format '{override}' (expected KEY=VALUE)")
            continue

        key, value = override.split("=", 1)
        key = key.strip()

        original_value = config.get(key)
        parsed_value = parse_config_value(value)

        config[key] = parsed_value

        if verbose:
            print(f"  {key}: {original_value} -> {parsed_value}")

    if verbose:
        print()

    return config


def add_config_override_argument(parser):
    """
    Add --config-override argument to an ArgumentParser

    Args:
        parser: argparse.ArgumentParser instance

    Example:
        >>> import argparse
        >>> parser = argparse.ArgumentParser()
        >>> add_config_override_argument(parser)
        >>> args = parser.parse_args()
        >>> config = load_config()
        >>> apply_config_overrides(config, args.config_override or [])
    """
    parser.add_argument(
        "--config-override",
        action="append",
        metavar="KEY=VALUE",
        help=(
            "Override config values (can be used multiple times). "
            "Format: KEY=VALUE. Boolean values: true/false. "
            "Examples: --config-override feature_level0_enable_vwap_check=false "
            "--config-override initial_capital=10000"
        ),
    )
