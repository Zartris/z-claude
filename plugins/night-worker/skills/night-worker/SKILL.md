# Night Worker

Protect long-running autonomous Claude Code sessions from crashing due to
Anthropic API rate limits (429 Too Many Requests).

## How it works

This plugin uses two components that share state via a local file:

1. **Status line bridge** (`statusline-bridge.sh`) — runs after every assistant
   message. Reads the `rate_limits` JSON that Claude Code pipes to status line
   scripts (5-hour and 7-day windows with `used_percentage` and `resets_at`),
   and writes it to `~/.claude/night-worker-rate-limits.json`.

2. **PreToolUse hook** (`rate_limit_monitor.py`) — runs before every tool call.
   Reads the cached rate limit state. If any window exceeds the threshold
   (default 80%), the script sleeps in 60-second loops, re-checking the state
   file each cycle. Once limits reset, it exits cleanly and the tool call
   proceeds as if nothing happened.

Zero extra API calls. The rate limit data comes from response headers that
Claude Code already parses (`anthropic-ratelimit-unified-5h-utilization`,
`anthropic-ratelimit-unified-7d-utilization`).

## Setup

The plugin hooks are installed automatically. You only need to configure the
status line bridge so the hook has rate limit data to read.

Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "<plugin-install-path>/hooks/statusline-bridge.sh"
  }
}
```

Or add the state-writing block to your existing status line script:

```bash
STATE_FILE="${HOME}/.claude/night-worker-rate-limits.json"
rate_limits=$(echo "$input" | jq -e '.rate_limits // empty' 2>/dev/null) || true
if [ -n "$rate_limits" ]; then
    echo "$rate_limits" > "$STATE_FILE"
fi
```

## Configuration

Override defaults via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NIGHT_WORKER_THRESHOLD` | `95` | Pause when usage exceeds this % |
| `NIGHT_WORKER_RECHECK_INTERVAL` | `60` | Seconds between re-checks during pause |
| `NIGHT_WORKER_STATE_FILE` | `~/.claude/night-worker-rate-limits.json` | Shared state file path |
| `NIGHT_WORKER_MAX_SLEEP` | `21600` | Maximum sleep duration in seconds (6h) |
| `NIGHT_WORKER_MAX_STATE_AGE` | `300` | Ignore state file if older than this (seconds) |
