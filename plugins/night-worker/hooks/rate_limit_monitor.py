#!/usr/bin/env python3
"""
PreToolUse hook: Rate limit monitor for Claude Code.

Reads cached rate limit state written by the status line bridge script.
If usage exceeds the configured threshold, sleeps until the `resets_at`
timestamp (set by Anthropic's servers), then exits cleanly.

The primary wake condition is the clock reaching `resets_at`, NOT the
state file updating. This is critical because while the hook is sleeping,
no tool calls run, no assistant messages are generated, and the status
line never re-runs — so the state file stays frozen. The re-check loop
is only an early-exit optimization for the rare case that the file does
get updated (e.g. the user interacts manually).

Architecture:
  StatusLine script (runs after every assistant message)
    → writes rate_limits JSON to STATE_FILE
  This script (runs before every tool call)
    → reads STATE_FILE
    → if over threshold: sleep until resets_at, checking periodically
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

        # Validate resets_at is a plausible Unix epoch in seconds.
        # Guards against milliseconds (13 digits), strings, or garbage.
        if not isinstance(resets_at, (int, float)):
            continue
        if resets_at > 1e12:
            # Likely milliseconds — convert to seconds.
            resets_at = resets_at / 1000
        if resets_at < 1e9:
            # Not a valid epoch timestamp (before ~2001).
            continue

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

    # --- Rate limit threshold exceeded — sleep until resets_at ---
    # Both resets_at and time.time() are Unix epoch seconds (UTC).
    # The chain: Anthropic API sends RFC 3339 headers → Claude Code
    # converts to epoch seconds → status line JSON → our state file.
    # No timezone conversion needed; epoch is timezone-agnostic.

    resets_at = state[window_name]["resets_at"]
    if resets_at > 1e12:
        resets_at = resets_at / 1000
    used_pct = state[window_name]["used_percentage"]
    log(
        f"Rate limit {format_window(window_name)} at {used_pct:.1f}% "
        f"(threshold: {THRESHOLD_PERCENT:.0f}%). "
        f"Sleeping until reset in {format_duration(sleep_seconds)}."
    )

    # Sleep in chunks. The primary wake condition is the clock reaching
    # resets_at. The state file re-check is only an early-exit optimization
    # (the file won't normally update while we're blocking the tool loop).
    while True:
        now = time.time()
        remaining = min(resets_at - now, MAX_SLEEP)

        if remaining <= 0:
            log("Reset time reached. Resuming.")
            break

        chunk = min(RECHECK_INTERVAL, remaining)
        time.sleep(chunk)

        # Early exit: if the state file happens to have been updated
        # (e.g. user interacted manually), check if limits dropped.
        fresh_state = read_state()
        if fresh_state is not None:
            fresh_exceeded, _, _ = check_limits(fresh_state)
            if not fresh_exceeded:
                log("Rate limits dropped below threshold. Resuming early.")
                break

        time_left = resets_at - time.time()
        if time_left > 0:
            log(f"Still paused. ~{format_duration(time_left)} until reset.")

    # Exit 0 — allow the tool call to proceed.
    sys.exit(0)


if __name__ == "__main__":
    main()
