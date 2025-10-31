#!/usr/bin/env python3
"""
Visualize Break & Re-Test signals on a candlestick chart

Usage:
    python3 break-and-retest/visualize_results.py --ticker AAPL --out /tmp/aapl_br.html
    python3 break-and-retest/visualize_results.py --demo --demo-scenario long
    python3 break-and-retest/visualize_results.py --show-test

This will run the scanner (first 90m) and plot detected signals with entry/stop/target and opening range.
"""
import argparse
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from break_and_retest_strategy import scan_ticker, scan_dataframe
import os
from datetime import datetime
import webbrowser


def create_chart(df: pd.DataFrame, signals: list, output_file: str = None, title: str = "Break & Re-Test"):
    df = df.copy()
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    df.set_index("Datetime", inplace=True)

    # Debug info: surface basic df + OHLC stats so tests and CI can show what's being plotted.
    try:
        print(f"[create_chart] rows={len(df)} index_min={df.index.min()} index_max={df.index.max()}")
        print(f"[create_chart] Open min/max={df['Open'].min()}/{df['Open'].max()} High min/max={df['High'].min()}/{df['High'].max()} Low min/max={df['Low'].min()}/{df['Low'].max()} Close min/max={df['Close'].min()}/{df['Close'].max()}")
    except Exception:
        # Best-effort logging — don't fail the plot if something odd is present.
        pass

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)

    # Candles
    # Explicit candlestick styling to ensure bodies are visible across environments
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
            increasing=dict(line=dict(color="green", width=1), fillcolor="rgba(0,200,0,0.3)"),
            decreasing=dict(line=dict(color="red", width=1), fillcolor="rgba(200,0,0,0.3)"),
            visible=True,
        ),
        row=1, col=1
    )

    # Volume
    colors = ["green" if c >= o else "red" for o, c in zip(df["Open"], df["Close"]) ]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], marker_color=colors, name="Volume", opacity=0.5),
        row=2, col=1
    )

    # Plot opening range from first candle
    if len(df) > 0:
        or_high = df["High"].iloc[0]
        or_low = df["Low"].iloc[0]
        fig.add_hline(y=or_high, line_dash="dash", line_color="gray", row=1, col=1)
        fig.add_hline(y=or_low, line_dash="dash", line_color="gray", row=1, col=1)

    # Plot signals
    for sig in signals:
        entry = sig.get("entry")
        stop = sig.get("stop")
        target = sig.get("target")
        direction = sig.get("direction")
        dt = pd.to_datetime(sig.get("datetime"))
        color = "green" if direction == "long" else "red"
        # Entry line
        fig.add_hline(y=entry, line_color=color, line_width=2, row=1, col=1)
        fig.add_annotation(x=dt, y=entry, text=f"Entry ({direction})", showarrow=True, arrowhead=2)
        # Stop line
        fig.add_hline(y=stop, line_color="black", line_dash="dot", row=1, col=1)
        fig.add_annotation(x=dt, y=stop, text="Stop", showarrow=False, yshift=-10)
        # Target line
        fig.add_hline(y=target, line_color=color, line_dash="dash", row=1, col=1)
        fig.add_annotation(x=dt, y=target, text="Target", showarrow=False, yshift=10)

    # Set explicit y-axis ranges to prevent signal lines from squashing candles/volume
    # Price chart (row 1): based on OHLC data with 2% padding
    y_min = df["Low"].min()
    y_max = df["High"].max()
    y_padding = (y_max - y_min) * 0.02
    y_range = [y_min - y_padding, y_max + y_padding]
    
    # Volume chart (row 2): start from 0 to volume max with 5% padding on top
    vol_max = df["Volume"].max()
    vol_range = [0, vol_max * 1.05]
    
    fig.update_layout(
        title=title, 
        xaxis_rangeslider_visible=False, 
        height=700,
        yaxis=dict(range=y_range),
        yaxis2=dict(range=vol_range)
    )
    
    if output_file:
        fig.write_html(output_file)

        # Attempt to write a raster snapshot (PNG) next to the HTML for deterministic inspection.
        # This uses plotly's image engine (kaleido). If it's not available, print a helpful message.
        try:
            import plotly.io as pio
            png_path = os.path.splitext(output_file)[0] + ".png"
            try:
                pio.write_image(fig, png_path)
                print(f"Wrote PNG snapshot to {png_path}")
            except Exception as e:
                print(f"Could not write PNG snapshot (is 'kaleido' installed?): {e}")
        except Exception:
            print("plotly.io not available; cannot write PNG snapshot")

    return fig


def find_latest_html(pattern="test_*.html"):
    """Find the latest HTML file in logs directory matching the given pattern."""
    os.makedirs("logs", exist_ok=True)
    matching_files = []
    for entry in os.scandir("logs"):
        if not entry.is_file() or not entry.name.endswith(".html"):
            continue
            
        # Match test output files (test_long_valid, test_short_valid, etc)
        if pattern == "test_*.html" and entry.name.startswith("test_"):
            matching_files.append(entry.path)
        # Match demo files if specified
        elif entry.name.startswith(pattern.replace("*", "")):
            matching_files.append(entry.path)
            
    if not matching_files:
        return None
    return max(matching_files, key=os.path.getmtime)


def make_test_df():
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    data = [
        {"Datetime": times[0], "Open": 100, "High": 102, "Low": 99.5, "Close": 101.8, "Volume": 8000},
        {"Datetime": times[1], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[2], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[3], "Open": 101.8, "High": 102.5, "Low": 101.8, "Close": 102.5, "Volume": 20000},
        {"Datetime": times[4], "Open": 102.2, "High": 102.3, "Low": 102.0, "Close": 102.3, "Volume": 10000},
        {"Datetime": times[5], "Open": 102.3, "High": 103.0, "Low": 102.3, "Close": 102.95, "Volume": 13000},
    ]
    for i in range(6,20):
        data.append({"Datetime": times[i], "Open": 102.95, "High": 103.0, "Low": 102.9, "Close": 102.95, "Volume": 9000})
    return pd.DataFrame(data)


def make_test_df_short():
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    data = [
        {"Datetime": times[0], "Open": 100, "High": 102, "Low": 99.0, "Close": 101.8, "Volume": 8000},
        {"Datetime": times[1], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[2], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[3], "Open": 99.6, "High": 99.7, "Low": 98.9, "Close": 98.9, "Volume": 20000},
        {"Datetime": times[4], "Open": 99.2, "High": 99.0, "Low": 99.0, "Close": 99.0, "Volume": 10000},
        {"Datetime": times[5], "Open": 99.1, "High": 99.2, "Low": 98.5, "Close": 98.6, "Volume": 13000},
    ]
    for i in range(6,20):
        data.append({"Datetime": times[i], "Open": 98.6, "High": 99.0, "Low": 98.5, "Close": 98.6, "Volume": 9000})
    return pd.DataFrame(data)


def make_test_df_long_fail():
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    data = [
        {"Datetime": times[0], "Open": 100, "High": 102, "Low": 99.5, "Close": 101.8, "Volume": 8000},
        {"Datetime": times[1], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[2], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[3], "Open": 101.8, "High": 102.5, "Low": 101.8, "Close": 102.5, "Volume": 20000},
        {"Datetime": times[4], "Open": 102.2, "High": 103.0, "Low": 102.0, "Close": 102.3, "Volume": 10000},
        {"Datetime": times[5], "Open": 102.3, "High": 103.0, "Low": 102.3, "Close": 102.95, "Volume": 13000},
    ]
    for i in range(6,20):
        data.append({"Datetime": times[i], "Open": 102.95, "High": 103.0, "Low": 102.9, "Close": 102.95, "Volume": 9000})
    return pd.DataFrame(data)


def make_test_df_short_fail():
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    data = [
        {"Datetime": times[0], "Open": 100, "High": 102, "Low": 99.5, "Close": 101.8, "Volume": 8000},
        {"Datetime": times[1], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[2], "Open": 101.8, "High": 101.9, "Low": 101.7, "Close": 101.8, "Volume": 7000},
        {"Datetime": times[3], "Open": 99.6, "High": 99.7, "Low": 99.0, "Close": 99.0, "Volume": 20000},
        {"Datetime": times[4], "Open": 99.2, "High": 99.7, "Low": 99.0, "Close": 99.1, "Volume": 10000},
        {"Datetime": times[5], "Open": 99.1, "High": 99.2, "Low": 98.5, "Close": 98.6, "Volume": 13000},
    ]
    for i in range(6,20):
        data.append({"Datetime": times[i], "Open": 98.6, "High": 99.0, "Low": 98.5, "Close": 98.6, "Volume": 9000})
    return pd.DataFrame(data)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", required=False, help="Ticker to scan (not required when using --demo or --show-test)")
    p.add_argument("--out", default=None, help="Output HTML path (optional)")
    p.add_argument("--demo", action="store_true", help="Use built-in unit-test demo data instead of live yfinance data")
    p.add_argument("--demo-scenario", choices=["long","short","long_fail","short_fail"], default="long", help="Which demo scenario to use")
    p.add_argument("--show-test", action="store_true", help="Show the latest unit test HTML output")
    p.add_argument("--no-open", action="store_true", help="Do not open browser tabs (for CI/headless runs)")
    args = p.parse_args()

    # Check for --show-test first
    if args.show_test:
        # Find the latest test output HTML
        latest_html = find_latest_html("test_*.html")
        if latest_html:
            try:
                # Extract minute-level key from filename timestamp (YYYYMMDD_HHMM)
                # Expect filenames like: test_<name>_YYYYMMDD_HHMMSS.html
                import re
                m = re.search(r"_(\d{8}_\d{6})", os.path.basename(latest_html))
                minute_key = None
                if m:
                    datetime_str = m.group(1)  # e.g. 20251031_101818
                    minute_key = datetime_str[:13]  # e.g. 20251031_1018 (to the minute)

                # Collect all test files that share the same minute key (or fall back to all test files)
                matched = []
                all_test_files = []
                for entry in os.scandir("logs"):
                    if not entry.is_file() or not entry.name.endswith(".html"):
                        continue
                    if not entry.name.startswith("test_"):
                        continue
                    all_test_files.append(entry.path)
                    if minute_key and minute_key in entry.name:
                        matched.append(entry.path)

                # If we found a minute-group, use it; otherwise fall back to all test files
                files_to_show = matched if matched else all_test_files

                if not files_to_show:
                    print("No test output HTML files found in logs/ directory. Run 'pytest test_break_and_retest_strategy.py' to generate them.")
                    return

                # Print the list of files to show
                files_to_show = sorted(files_to_show, key=os.path.getmtime)
                latest_in_group = files_to_show[-1]
                print(f"Latest test output: {latest_in_group}")
                
                if len(files_to_show) > 1:
                    print("\nTest visualization files for the same minute:")
                    for f in files_to_show:
                        marker = "(latest)" if f == latest_in_group else ""
                        print(f"  {os.path.basename(f)} {marker}")

                # Only open browser tabs if --no-open is NOT set
                if not args.no_open:
                    try:
                        webbrowser.open(f"file://{os.path.abspath(latest_in_group)}")
                        print(f"\nOpened {latest_in_group} in browser")
                    except Exception:
                        print(f"\nCould not open browser automatically")
                    
                    # Open other files in new tabs
                    for f in files_to_show:
                        if f != latest_in_group:
                            try:
                                webbrowser.open_new_tab(f"file://{os.path.abspath(f)}")
                            except Exception:
                                pass
            except Exception as e:
                print(f"Error while locating or opening test outputs: {e}")
        else:
            print("No test output HTML files found in logs/ directory. Run 'pytest test_break_and_retest_strategy.py' to generate them.")

    # Demo mode
    if args.demo:
        # Maps scenario names to data generation functions
        scenarios = {
            "long": make_test_df,
            "short": make_test_df_short,
            "long_fail": make_test_df_long_fail,
            "short_fail": make_test_df_short_fail,
        }
        df = scenarios[args.demo_scenario]()
        signals, scan_df = scan_dataframe(df)
        if not signals:
            print("No signals found in demo scenario — still plotting the data.")
        fig = create_chart(scan_df if not scan_df.empty else df, signals, title=f"Demo: {args.demo_scenario}")
        # Default to saving output into logs/ with a timestamped filename
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("logs", exist_ok=True)
        out_path = args.out if args.out else os.path.join("logs", f"demo_{args.demo_scenario}_{ts}.html")
        fig.write_html(out_path)
        print(f"Saved demo chart to {out_path}")
        if not args.no_open:
            try:
                webbrowser.open(f"file://{os.path.abspath(out_path)}")
                print(f"Opened {out_path} in the default browser.")
            except Exception:
                print("Could not open the file in a browser automatically.")
        return

    # Live ticker mode
    if not args.ticker:
        print("Please provide --ticker when not using --demo or --show-test")
        raise SystemExit(2)
    signals, df = scan_ticker(args.ticker)
    if not signals:
        print("No signals found — nothing to plot.")
    else:
        fig = create_chart(df, signals, title=f"{args.ticker} Break & Re-Test")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("logs", exist_ok=True)
        out_path = args.out if args.out else os.path.join("logs", f"{args.ticker}_break_and_retest_{ts}.html")
        fig.write_html(out_path)
        print(f"Saved chart to {out_path}")
        if not args.no_open:
            try:
                webbrowser.open(f"file://{os.path.abspath(out_path)}")
                print(f"Opened {out_path} in the default browser.")
            except Exception:
                print("Could not open the file in a browser automatically.")


if __name__ == "__main__":
    main()