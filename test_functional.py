"""
Functional Test Suite - End-to-End Testing

Tests all user-facing features documented in README:
1. Scanner CLI with various options
2. Backtest engine with caching and parameters
3. Visualization generation (demo mode, test output)
4. Signal grading with Scarface Rules
5. Continuous scanning script

These are integration/functional tests that exercise the full system.
Run with: pytest test_functional.py -v
"""

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def temp_test_dir():
    """Create a temporary directory for test outputs"""
    temp_dir = tempfile.mkdtemp(prefix="test_functional_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def python_exe():
    """Get the Python executable from the virtual environment"""
    venv_python = Path(".venv/bin/python")
    if venv_python.exists():
        return str(venv_python)
    return "python"


class TestScannerCLI:
    """Test the break_and_retest_strategy.py scanner CLI"""

    def test_scanner_help(self, python_exe):
        """Test scanner --help displays usage"""
        result = subprocess.run(
            [python_exe, "break_and_retest_strategy.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert "--tickers" in result.stdout

    def test_scanner_dry_run(self, python_exe):
        """Test scanner runs without errors (no real market data needed)"""
        # Note: This may return empty signals due to data/timing, but should not crash
        result = subprocess.run(
            [python_exe, "break_and_retest_strategy.py", "--tickers", "AAPL"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Should exit successfully even if no signals found
        assert result.returncode == 0


class TestBacktestEngine:
    """Test the backtest.py engine with various parameters"""

    def test_backtest_help(self, python_exe):
        """Test backtest --help displays usage"""
        result = subprocess.run(
            [python_exe, "backtest.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert "--symbols" in result.stdout
        assert "--start" in result.stdout
        assert "--end" in result.stdout

    def test_backtest_single_symbol(self, python_exe, temp_test_dir):
        """Test backtest with single symbol and recent dates"""
        output_file = Path(temp_test_dir) / "backtest_results.json"

        # Use recent dates (last 3 days)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

        result = subprocess.run(
            [
                python_exe,
                "backtest.py",
                "--symbols",
                "AAPL",
                "--start",
                start_date,
                "--end",
                end_date,
                "--initial-capital",
                "10000",
                "--output",
                str(output_file),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0
        assert "BACKTEST RESULTS" in result.stdout or "Total Trades" in result.stdout

        # Check output file was created with valid data
        if output_file.exists():
            with open(output_file) as f:
                data = json.load(f)
                assert isinstance(data, list), "Output should be a list of results"
                if data:  # If results found
                    assert "symbol" in data[0], "Result should have symbol field"
                    assert data[0]["symbol"] == "AAPL"

    def test_backtest_with_grading(self, python_exe):
        """Test backtest outputs Scarface Rules grading"""
        # Use recent dates
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        result = subprocess.run(
            [
                python_exe,
                "backtest.py",
                "--symbols",
                "AAPL",
                "--start",
                start_date,
                "--end",
                end_date,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Should complete successfully
        assert result.returncode == 0

        # Check for Scarface Rules output if signals found
        if "Scarface Rules" in result.stdout:
            assert "Level:" in result.stdout
            assert "Breakout:" in result.stdout
            assert "Retest:" in result.stdout
            assert "Grade:" in result.stdout


class TestVisualization:
    """Test visualize_results.py generation"""

    def test_visualize_help(self, python_exe):
        """Test visualize --help displays usage"""
        result = subprocess.run(
            [python_exe, "visualize_results.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert "--demo" in result.stdout

    def test_demo_mode_long(self, python_exe):
        """Test demo mode with long scenario"""
        result = subprocess.run(
            [
                python_exe,
                "visualize_results.py",
                "--demo",
                "--demo-scenario",
                "long",
                "--no-open",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

    def test_demo_mode_short(self, python_exe):
        """Test demo mode with short scenario"""
        result = subprocess.run(
            [
                python_exe,
                "visualize_results.py",
                "--demo",
                "--demo-scenario",
                "short",
                "--no-open",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

    def test_demo_mode_long_fail(self, python_exe):
        """Test demo mode with long_fail scenario"""
        result = subprocess.run(
            [
                python_exe,
                "visualize_results.py",
                "--demo",
                "--demo-scenario",
                "long_fail",
                "--no-open",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

    def test_demo_mode_short_fail(self, python_exe):
        """Test demo mode with short_fail scenario"""
        result = subprocess.run(
            [
                python_exe,
                "visualize_results.py",
                "--demo",
                "--demo-scenario",
                "short_fail",
                "--no-open",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0


class TestContinuousScanner:
    """Test the find_break_and_retest.sh wrapper script"""

    def test_scanner_script_exists(self):
        """Test that the scanner script exists and is executable"""
        script = Path("find_break_and_retest.sh")
        assert script.exists(), "Scanner script not found"
        assert os.access(script, os.X_OK), "Scanner script not executable"

    def test_scanner_script_once(self, python_exe):
        """Test scanner script with --once flag"""
        result = subprocess.run(
            ["./find_break_and_retest.sh", "--once"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Should exit successfully after one run
        assert result.returncode == 0


class TestSignalGrading:
    """Test signal_grader.py module functionality"""

    def test_signal_grader_import(self):
        """Test signal_grader module can be imported"""
        try:
            import signal_grader

            assert hasattr(signal_grader, "generate_signal_report")
            assert hasattr(signal_grader, "grade_breakout_candle")
            assert hasattr(signal_grader, "calculate_overall_grade")
        except ImportError as e:
            pytest.fail(f"Failed to import signal_grader: {e}")

    def test_signal_grading_integration(self):
        """Test signal grading with a mock signal"""
        from signal_grader import generate_signal_report

        mock_signal = {
            "ticker": "TEST",
            "direction": "long",
            "level": 100.0,
            "entry": 100.5,
            "stop": 99.5,
            "target": 102.5,
            "breakout_body_pct": 0.75,
            "breakout_vol_ratio": 2.5,
            "retest_vol_ratio": 0.3,
            "ignition_vol_ratio": 1.2,
            "distance_to_target": 0.6,
            "ignition_body_pct": 0.7,
            "breakout_candle": {
                "Open": 99,
                "High": 100.5,
                "Low": 99,
                "Close": 100.5,
            },
            "retest_candle": {
                "Open": 100.5,
                "High": 100.6,
                "Low": 100.0,
                "Close": 100.2,
            },
            "ignition_candle": {
                "Open": 100.2,
                "High": 101.5,
                "Low": 100.2,
                "Close": 101.4,
            },
        }

        report = generate_signal_report(mock_signal)

        assert "TEST" in report
        assert "Scarface Rules" in report
        assert "Grade:" in report
        assert "Level:" in report


class TestConfiguration:
    """Test configuration file loading"""

    def test_config_file_exists(self):
        """Test config.json exists and is valid"""
        config_path = Path("config.json")
        assert config_path.exists(), "config.json not found"

        with open(config_path) as f:
            config = json.load(f)
            assert "tickers" in config
            assert isinstance(config["tickers"], list)
            assert len(config["tickers"]) > 0


class TestMakefile:
    """Test Makefile targets work correctly"""

    def test_make_format(self):
        """Test make format runs without error"""
        result = subprocess.run(["make", "format"], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0

    def test_make_lint(self):
        """Test make lint runs without error"""
        result = subprocess.run(["make", "lint"], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0

    def test_make_test(self):
        """Test make test runs successfully"""
        result = subprocess.run(["make", "test"], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0
        assert "passed" in result.stdout.lower()

    def test_make_coverage(self):
        """Test make coverage generates report"""
        result = subprocess.run(["make", "coverage"], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0
        assert "coverage" in result.stdout.lower()
        # Check HTML report was generated
        assert Path("htmlcov/index.html").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
