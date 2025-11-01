#!/usr/bin/env bash
set -euo pipefail

# run_break_and_retest.sh
# Run the live scanner on a schedule (default: every 1 minute).
# Usage:
#   ./run_break_and_retest.sh                # run forever, aligned to 1-minute clock marks
#   ./run_break_and_retest.sh --once         # run a single scan and exit
#   ./run_break_and_retest.sh --no-align     # run every INTERVAL without clock alignment
#   ./run_break_and_retest.sh --interval 30s --daemon  # run every 30 seconds in background

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
PY="$VENV/bin/python"
SCRIPT="$DIR/break_and_retest_live_scanner.py"
LOGDIR="$DIR/logs"
mkdir -p "$LOGDIR"
# Default: 60 seconds (1 minute)
INTERVAL_SEC=60
ALIGN=true
ONCE=false
DAEMON=false
LOGFILE="$LOGDIR/scan-$(date +%Y%m%d).log"
LOCKFILE="$DIR/run_break_and_retest.lock"

usage(){
    cat <<-USAGE
Usage: $0 [--once] [--no-align] [--interval N|Ns|Nm] [--daemon] [--log file]

Options:
    --once         Run a single scan and exit
    --no-align     Do not align to clock multiples; sleep fixed INTERVAL between runs
    --interval N   Interval between runs. By default N is minutes. Append 's' for seconds (e.g. 30s), or 'm' for minutes. Default: 1m
    --daemon       Run in background (uses nohup)
    --log FILE     Path to log file (default: ${LOGFILE})
    --help         Show this help
USAGE
}

while [[ ${#} -gt 0 ]]; do
    case "$1" in
        --once)
            ONCE=true; shift;;
        --no-align)
            ALIGN=false; shift;;
        -i|--interval)
            val="$2"; shift 2;
            # If suffix 's' treat as seconds, 'm' or no suffix treat as minutes
            if [[ "$val" =~ s$ ]]; then
                num=${val%s}
                INTERVAL_SEC=${num}
            elif [[ "$val" =~ m$ ]]; then
                num=${val%m}
                INTERVAL_SEC=$(( num * 60 ))
            else
                # no suffix: treat as minutes
                INTERVAL_SEC=$(( val * 60 ))
            fi
            ;;
        --daemon)
            DAEMON=true; shift;;
        --log)
            LOGFILE="$2"; shift 2;;
        -h|--help)
            usage; exit 0;;
        *)
            echo "Unknown arg: $1" >&2; usage; exit 2;;
    esac
done

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: scanner script not found: $SCRIPT" >&2
    exit 2
fi

run_once(){
    # Activate venv if present, otherwise fall back to system python
    if [ -x "$PY" ]; then
        PY_CMD=("$PY" "$SCRIPT")
    else
        PY_CMD=("python3" "$SCRIPT")
    fi

    # Run and timestamp output lines, showing in console when not in daemon mode
    ("${PY_CMD[@]}" 2>&1) | while IFS= read -r line; do
        timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
        timestamped_line="$timestamp $line"
        echo "$timestamped_line" >> "$LOGFILE"
        if [ "$DAEMON" = false ]; then
            echo "$timestamped_line"
        fi
    done || true
}

acquire_lock(){
    # Use a simple lockfile to prevent concurrent runs across processes
    exec 9>"$LOCKFILE"
    if ! flock -n 9; then
        echo "Another instance appears to be running (lockfile: $LOCKFILE). Exiting." | tee -a "$LOGFILE"
        exit 0
    fi
}

release_lock(){
    # close fd 9 to release flock
    exec 9>&-
}

seconds_until_next_interval(){
    local interval_sec=$1
    local now=$(date +%s)
    local next=$(( ((now / interval_sec) + 1) * interval_sec ))
    echo $(( next - now ))
}

main_loop(){
    acquire_lock
    trap 'release_lock; exit 0' INT TERM EXIT

    while true; do
        if [ "$ALIGN" = true ]; then
            sleep_seconds=$(seconds_until_next_interval "$INTERVAL_SEC")
            if [ "$sleep_seconds" -gt 0 ]; then
                timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
                msg="$timestamp Waiting $sleep_seconds seconds until next aligned run"
                echo "$msg" >> "$LOGFILE"
                if [ "$DAEMON" = false ]; then
                    echo "$msg"
                fi
                sleep "$sleep_seconds"
            fi
        fi

        timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
        msg="$timestamp Starting scan"
        echo "$msg" >> "$LOGFILE"
        if [ "$DAEMON" = false ]; then
            echo "$msg"
        fi
        run_once

        if [ "$ONCE" = true ]; then
            timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
            msg="$timestamp Completed one-off run, exiting"
            echo "$msg" >> "$LOGFILE"
            if [ "$DAEMON" = false ]; then
                echo "$msg"
            fi
            release_lock
            break
        fi

        if [ "$ALIGN" = false ]; then
            sleep "$INTERVAL_SEC"
        fi
    done
}

if [ "$DAEMON" = true ] && [ "$ONCE" = false ]; then
    nohup "$0" "--interval" "${INTERVAL_SEC}s" $( [ "$ALIGN" = false ] && echo "--no-align" ) >> "$LOGFILE" 2>&1 &
    echo "Launched daemon (logs -> $LOGFILE)"
    exit 0
fi

# Ensure flock exists
if ! command -v flock >/dev/null 2>&1; then
    echo "ERROR: 'flock' command not found. Install util-linux or run via cron instead." >&2
    exit 2
fi

main_loop
