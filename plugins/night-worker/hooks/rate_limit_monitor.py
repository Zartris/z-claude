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

IMPORTANT: This monitor only tracks the 5-hour and 7-day unified quotas
exposed by Claude Code's status line JSON. Per-minute rate limits
(RPM, input-TPM, output-TPM) are NOT available to hooks and can still
cause 429 errors that this monitor cannot prevent.

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
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration — edit these or override via environment variables
# ---------------------------------------------------------------------------

# Pause when any rate limit window exceeds this percentage (0-100).
THRESHOLD_PERCENT = float(os.environ.get("NIGHT_WORKER_THRESHOLD", "95"))

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


def epoch_to_local(epoch: float) -> str:
    """Convert a Unix epoch to a human-readable local time string."""
    try:
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except (OSError, ValueError, OverflowError):
        return f"epoch={epoch}"


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration."""
    if seconds < 0:
        return "0s"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_window(name: str) -> str:
    return name.replace("_", "-")


def normalize_epoch(value: object) -> float | None:
    """
    Validate and normalize a resets_at value to Unix epoch seconds.
    Returns None if the value is not a plausible epoch.
    """
    if not isinstance(value, (int, float)):
        return None
    epoch = float(value)
    if epoch > 1e12:
        # Likely milliseconds — convert to seconds.
        epoch = epoch / 1000
    if epoch < 1e9:
        # Not a valid epoch timestamp (before ~2001).
        return None
    return epoch


def read_state_raw() -> tuple[dict | None, str]:
    """
    Read the rate limit state file. Returns (state_dict, status_message).
    Unlike read_state(), always returns a diagnostic message for logging.
    """
    try:
        mtime = os.path.getmtime(STATE_FILE)
    except FileNotFoundError:
        return None, f"state file not found: {STATE_FILE}"
    except OSError as e:
        return None, f"cannot stat state file: {e}"

    age = time.time() - mtime
    age_str = format_duration(age)

    if age > MAX_STATE_AGE:
        return None, (
            f"state file is stale ({age_str} old, max {format_duration(MAX_STATE_AGE)}): "
            f"{STATE_FILE}"
        )

    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, f"state file has invalid JSON: {e}"
    except OSError as e:
        return None, f"cannot read state file: {e}"

    return data, f"state file OK ({age_str} old)"


def dump_state(state: dict | None) -> str:
    """Format the full state for logging."""
    if state is None:
        return "  (no state)"

    now = time.time()
    lines = []

    for window_name in ("five_hour", "seven_day"):
        window = state.get(window_name)
        if not window:
            lines.append(f"  {format_window(window_name)}: not present")
            continue

        used = window.get("used_percentage", "?")
        raw_resets_at = window.get("resets_at", "?")
        epoch = normalize_epoch(raw_resets_at)

        if epoch is not None:
            time_until = epoch - now
            if time_until > 0:
                reset_str = f"{epoch_to_local(epoch)} (in {format_duration(time_until)})"
            else:
                reset_str = f"{epoch_to_local(epoch)} (already passed, {format_duration(-time_until)} ago)"
        else:
            reset_str = f"invalid ({raw_resets_at!r})"

        lines.append(
            f"  {format_window(window_name)}: "
            f"used={used}%, resets_at={reset_str}"
        )

    return "\n".join(lines)


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
        resets_at = normalize_epoch(window.get("resets_at", 0))

        if resets_at is None:
            continue

        if used >= THRESHOLD_PERCENT and resets_at > now:
            sleep_seconds = min(resets_at - now, MAX_SLEEP)
            return True, sleep_seconds, window_name

    return False, 0, ""


def main() -> None:
    # Read hook input from stdin (required by Claude Code hook protocol).
    raw_input = sys.stdin.read()

    # Parse hook input for context logging.
    tool_name = "?"
    try:
        hook_input = json.loads(raw_input)
        tool_name = hook_input.get("tool_name", "?")
    except (json.JSONDecodeError, TypeError):
        pass

    # Read and evaluate rate limit state.
    state, state_status = read_state_raw()

    if state is None:
        # No usable state — log why and allow the tool call.
        log(
            f"PASS (no state) tool={tool_name}\n"
            f"  reason: {state_status}\n"
            f"  config: threshold={THRESHOLD_PERCENT}%, "
            f"max_state_age={format_duration(MAX_STATE_AGE)}"
        )
        sys.exit(0)

    exceeded, sleep_seconds, window_name = check_limits(state)

    if not exceeded:
        log(
            f"PASS (under threshold) tool={tool_name}\n"
            f"  {state_status}\n"
            f"  threshold: {THRESHOLD_PERCENT}%\n"
            f"{dump_state(state)}"
        )
        sys.exit(0)

    # --- Rate limit threshold exceeded — sleep until resets_at ---
    # Both resets_at and time.time() are Unix epoch seconds (UTC).
    # The chain: Anthropic API sends RFC 3339 headers → Claude Code
    # converts to epoch seconds → status line JSON → our state file.
    # No timezone conversion needed; epoch is timezone-agnostic.

    resets_at = normalize_epoch(state[window_name]["resets_at"])
    used_pct = state[window_name]["used_percentage"]

    log(
        f"SLEEPING tool={tool_name}\n"
        f"  {state_status}\n"
        f"  threshold: {THRESHOLD_PERCENT}%\n"
        f"  triggered by: {format_window(window_name)} at {used_pct:.1f}%\n"
        f"  resets at: {epoch_to_local(resets_at)}\n"
        f"  sleep duration: {format_duration(sleep_seconds)} (max {format_duration(MAX_SLEEP)})\n"
        f"  re-check interval: {format_duration(RECHECK_INTERVAL)}\n"
        f"  full state:\n"
        f"{dump_state(state)}"
    )

    # Sleep in chunks. The primary wake condition is the clock reaching
    # resets_at. The state file re-check is only an early-exit optimization
    # (the file won't normally update while we're blocking the tool loop).
    cycle = 0
    while True:
        now = time.time()
        remaining = min(resets_at - now, MAX_SLEEP)

        if remaining <= 0:
            log(
                f"RESUMING (reset time reached)\n"
                f"  slept for {cycle} cycles ({cycle * RECHECK_INTERVAL}s)\n"
                f"  proceeding with tool={tool_name}"
            )
            break

        chunk = min(RECHECK_INTERVAL, remaining)
        time.sleep(chunk)
        cycle += 1

        # Early exit: if the state file happens to have been updated
        # (e.g. user interacted manually), check if limits dropped.
        fresh_state, fresh_status = read_state_raw()
        if fresh_state is not None:
            fresh_exceeded, _, _ = check_limits(fresh_state)
            if not fresh_exceeded:
                log(
                    f"RESUMING EARLY (limits dropped below threshold)\n"
                    f"  slept for {cycle} cycles ({cycle * RECHECK_INTERVAL}s)\n"
                    f"  {fresh_status}\n"
                    f"  fresh state:\n"
                    f"{dump_state(fresh_state)}\n"
                    f"  proceeding with tool={tool_name}"
                )
                break

        time_left = resets_at - time.time()
        if time_left > 0:
            log(
                f"  cycle {cycle}: ~{format_duration(time_left)} until reset "
                f"({epoch_to_local(resets_at)})"
            )

    # Exit 0 — allow the tool call to proceed.
    sys.exit(0)


if __name__ == "__main__":
    main()
