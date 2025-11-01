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
