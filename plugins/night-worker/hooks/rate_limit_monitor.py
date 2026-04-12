#!/usr/bin/env python3
"""
PreToolUse hook: Rate limit monitor for Claude Code.

Reads cached rate limit state written by the status line bridge script.
If usage exceeds the configured threshold, sleeps until the reset time,
re-checking periodically in case limits reset sooner than expected.

Architecture:
  StatusLine script (runs after every assistant message)
    → writes rate_limits JSON to STATE_FILE
  This script (runs before every tool call)
    → reads STATE_FILE
    → if over threshold: sleep in loops, re-checking periodically
    → exit 0 to allow the tool call to proceed
"""

import json
import os
import sys
import time

# ---------------------------------------------------------------------------
# Configuration — edit these or override via environment variables
# ---------------------------------------------------------------------------

# Pause when any rate limit window exceeds this percentage (0-100).
THRESHOLD_PERCENT = float(os.environ.get("NIGHT_WORKER_THRESHOLD", "80"))

# Seconds between re-checks while sleeping.
RECHECK_INTERVAL = int(os.environ.get("NIGHT_WORKER_RECHECK_INTERVAL", "60"))

# Shared state file written by the status line bridge script.
STATE_FILE = os.path.expanduser(
    os.environ.get(
        "NIGHT_WORKER_STATE_FILE",
        "~/.claude/night-worker-rate-limits.json",
    )
)

# Safety cap: never sleep longer than this (seconds). Default 6 hours.
MAX_SLEEP = int(os.environ.get("NIGHT_WORKER_MAX_SLEEP", str(6 * 3600)))

# How old the state file can be (seconds) before we consider it stale
# and skip the check (to avoid blocking on ancient data).
MAX_STATE_AGE = int(os.environ.get("NIGHT_WORKER_MAX_STATE_AGE", "300"))


def log(msg: str) -> None:
    """Write to stderr so the message appears in Claude Code's UI."""
    print(f"[night-worker] {msg}", file=sys.stderr, flush=True)


def read_state() -> dict | None:
    """Read the rate limit state file written by the status line bridge."""
    try:
        mtime = os.path.getmtime(STATE_FILE)
        age = time.time() - mtime
        if age > MAX_STATE_AGE:
            return None

        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def check_limits(state: dict | None) -> tuple[bool, float, str]:
    """
    Check if any rate limit exceeds the threshold.

    Returns:
        (exceeded, sleep_seconds, window_name)
    """
    if not state:
        return False, 0, ""

    now = time.time()

    for window_name in ("five_hour", "seven_day"):
        window = state.get(window_name)
        if not window:
            continue

        used = window.get("used_percentage", 0)
        resets_at = window.get("resets_at", 0)

        if used >= THRESHOLD_PERCENT and resets_at > now:
            sleep_seconds = min(resets_at - now, MAX_SLEEP)
            return True, sleep_seconds, window_name

    return False, 0, ""


def format_window(name: str) -> str:
    return name.replace("_", "-")


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    hours = seconds / 3600
    return f"{hours:.1f}h"


def main() -> None:
    # Consume stdin (required by Claude Code hook protocol).
    sys.stdin.read()

    state = read_state()

    if state is None:
        # No state file or stale data — allow the tool call.
        sys.exit(0)

    exceeded, sleep_seconds, window_name = check_limits(state)

    if not exceeded:
        sys.exit(0)

    # --- Rate limit threshold exceeded — enter sleep loop ---

    used_pct = state[window_name]["used_percentage"]
    log(
        f"Rate limit {format_window(window_name)} at {used_pct:.1f}% "
        f"(threshold: {THRESHOLD_PERCENT:.0f}%). "
        f"Pausing for up to {format_duration(sleep_seconds)} until reset."
    )

    remaining = sleep_seconds
    while remaining > 0:
        chunk = min(RECHECK_INTERVAL, remaining)
        time.sleep(chunk)
        remaining -= chunk

        # Re-read state — the status line keeps updating it.
        state = read_state()
        exceeded, new_sleep, window_name = check_limits(state)

        if not exceeded:
            log("Rate limits have reset. Resuming.")
            break

        # Use the freshest sleep estimate.
        remaining = min(new_sleep, remaining)
        current_pct = state.get(window_name, {}).get("used_percentage", 0)
        log(
            f"Still paused. {format_window(window_name)} at {current_pct:.1f}%. "
            f"~{format_duration(remaining)} remaining."
        )

    # Exit 0 — allow the tool call to proceed.
    sys.exit(0)


if __name__ == "__main__":
    main()
