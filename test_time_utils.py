from pathlib import Path

from time_utils import get_display_timezone


def test_get_display_timezone_default(tmp_path: Path):
    tz, label = get_display_timezone(tmp_path)
    # Default per module is PDT / America/Los_Angeles
    assert label in {"PDT", "UTC"}
    assert hasattr(tz, "key")


def test_get_display_timezone_config_pst(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"timezone": "PST"}')
    tz, label = get_display_timezone(tmp_path)
    assert label == "PST"
    assert tz.key == "America/Los_Angeles"


def test_get_display_timezone_invalid(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"timezone": "INVALID"}')
    tz, label = get_display_timezone(tmp_path)
    # Fallback to default mapping (PDT) or UTC safeguard
    assert label in {"PDT", "UTC"}
    assert hasattr(tz, "key")


def test_get_display_timezone_est(tmp_path: Path):
    """Test Eastern timezone mapping"""
    cfg = tmp_path / "config.json"
    cfg.write_text('{"timezone": "EST"}')
    tz, label = get_display_timezone(tmp_path)
    assert label == "EST"
    assert tz.key == "America/New_York"


def test_get_display_timezone_cst(tmp_path: Path):
    """Test Central timezone mapping"""
    cfg = tmp_path / "config.json"
    cfg.write_text('{"timezone": "CST"}')
    tz, label = get_display_timezone(tmp_path)
    assert label == "CST"
    assert tz.key == "America/Chicago"


def test_get_display_timezone_mst(tmp_path: Path):
    """Test Mountain timezone mapping"""
    cfg = tmp_path / "config.json"
    cfg.write_text('{"timezone": "MST"}')
    tz, label = get_display_timezone(tmp_path)
    assert label == "MST"
    assert tz.key == "America/Denver"


def test_get_display_timezone_utc(tmp_path: Path):
    """Test UTC timezone mapping"""
    cfg = tmp_path / "config.json"
    cfg.write_text('{"timezone": "UTC"}')
    tz, label = get_display_timezone(tmp_path)
    assert label == "UTC"
    assert tz.key == "UTC"


def test_get_display_timezone_no_config_file(tmp_path: Path):
    """Test default behavior when config.json doesn't exist"""
    tz, label = get_display_timezone(tmp_path)
    # Should use default (PDT)
    assert label in {"PDT", "UTC"}
    assert hasattr(tz, "key")


def test_get_display_timezone_malformed_json(tmp_path: Path):
    """Test fallback when config.json has invalid JSON"""
    cfg = tmp_path / "config.json"
    cfg.write_text("{invalid json")
    tz, label = get_display_timezone(tmp_path)
    # Should fall back to default
    assert label in {"PDT", "UTC"}
    assert hasattr(tz, "key")
