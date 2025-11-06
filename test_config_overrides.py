import copy
import pytest

from config_utils import apply_config_overrides, parse_config_value


@pytest.fixture()
def base_config():
    return {
        "tickers": ["AAPL", "AMZN"],
        "initial_capital": 7500,
        "leverage": 2.0,
        "timeframe_5m": "5m",
        "timeframe_1m": "1m",
        "lookback": "2d",
        "session_start": "09:30",
        "session_end": "16:00",
        "market_open_minutes": 90,
        "timezone": "PST",
        "backtest_results_dir": "backtest_results",
        "feature_level0_enable_vwap_check": True,
        "feature_cache_check_integrity": False,
    }


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("initial_capital", "12345", 12345),
        ("leverage", "3.5", 3.5),
        ("market_open_minutes", "120", 120),
        ("timeframe_5m", "10m", "10m"),
        ("timeframe_1m", "1m", "1m"),
        ("lookback", "5d", "5d"),
        ("session_start", "08:30", "08:30"),
        ("session_end", "17:00", "17:00"),
        ("timezone", "UTC", "UTC"),
        ("backtest_results_dir", "results_alt", "results_alt"),
        ("feature_level0_enable_vwap_check", "false", False),
        ("feature_cache_check_integrity", "true", True),
    ],
)
def test_apply_config_overrides_updates_values(base_config, key, value, expected):
    cfg = copy.deepcopy(base_config)
    apply_config_overrides(cfg, [f"{key}={value}"], verbose=False)
    assert cfg[key] == expected


def test_apply_config_overrides_trims_whitespace(base_config):
    cfg = copy.deepcopy(base_config)
    apply_config_overrides(cfg, [" initial_capital =  10000 "], verbose=False)
    assert cfg["initial_capital"] == 10000


def test_apply_config_overrides_ignores_invalid_entries(base_config):
    cfg = copy.deepcopy(base_config)
    before = copy.deepcopy(cfg)
    apply_config_overrides(cfg, ["invalid-no-equals"], verbose=False)
    assert cfg == before


@pytest.mark.parametrize(
    "raw,parsed",
    [
        ("true", True),
        ("false", False),
        ("  TRUE  ", True),
        ("  false\n", False),
        ("42", 42),
        ("-7", -7),
        ("3.14", 3.14),
        ("-0.5", -0.5),
        ("text", "text"),
    ],
)
def test_parse_config_value_typing(raw, parsed):
    assert parse_config_value(raw) == parsed


def test_hyphen_key_does_not_change_underscore_key(base_config):
    """
    Current behavior: hyphenated keys are treated as different keys. This test
    documents that behavior so we can decide later whether to normalize keys.
    """
    cfg = copy.deepcopy(base_config)
    apply_config_overrides(cfg, ["initial-capital=30000"], verbose=False)
    # New key added, original remains unchanged
    assert cfg.get("initial-capital") == 30000
    assert cfg["initial_capital"] == base_config["initial_capital"]
