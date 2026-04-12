# /night-status

Show the current rate limit status and night-worker state.

When invoked, read `~/.claude/night-worker-rate-limits.json` and report:

- 5-hour window: usage percentage and time until reset
- 7-day window: usage percentage and time until reset
- Current threshold setting (from `NIGHT_WORKER_THRESHOLD` env var, default 80%)
- Whether the monitor would currently pause (usage >= threshold)

If the state file is missing or stale (>5 minutes old), report that the status
line bridge is not configured or not running, and point the user to the setup
instructions in the plugin README.
