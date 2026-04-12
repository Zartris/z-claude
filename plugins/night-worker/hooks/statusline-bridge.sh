#!/usr/bin/env bash
# statusline-bridge.sh
#
# Status line script that serves two purposes:
# 1. Extracts rate_limits from Claude Code's JSON and writes them
#    to a shared state file for the PreToolUse rate_limit_monitor to read.
# 2. Renders a compact status line showing model, context, cost, and limits.
#
# Setup: add this to ~/.claude/settings.json:
#   {
#     "statusLine": {
#       "type": "command",
#       "command": "/path/to/statusline-bridge.sh"
#     }
#   }
#
# Or if you already have a status line, just add the "write state" block
# to your existing script (the section between the --- markers below).

set -euo pipefail

STATE_FILE="${NIGHT_WORKER_STATE_FILE:-${HOME}/.claude/night-worker-rate-limits.json}"

# Read the full JSON from Claude Code via stdin
input=$(cat)

# --- Write rate limit state for the PreToolUse hook ---
rate_limits=$(echo "$input" | jq -e '.rate_limits // empty' 2>/dev/null) || true
if [ -n "$rate_limits" ]; then
    mkdir -p "$(dirname "$STATE_FILE")"
    echo "$rate_limits" > "$STATE_FILE"
fi
# --- End rate limit state block ---

# Render the status line
MODEL=$(echo "$input" | jq -r '.model.display_name // "?"')
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
COST=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')

# Format cost
if command -v printf &>/dev/null; then
    COST_FMT=$(printf '$%.2f' "$COST")
else
    COST_FMT="\$${COST}"
fi

# Rate limit bars
RL_5H=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty' 2>/dev/null) || true
RL_7D=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty' 2>/dev/null) || true

rl_color() {
    local pct="${1%.*}"  # truncate to int
    if [ "$pct" -ge 90 ] 2>/dev/null; then
        echo "\033[31m"  # red
    elif [ "$pct" -ge 70 ] 2>/dev/null; then
        echo "\033[33m"  # yellow
    else
        echo "\033[32m"  # green
    fi
}

RESET="\033[0m"
DIM="\033[2m"

RL_STR=""
if [ -n "$RL_5H" ]; then
    COLOR=$(rl_color "$RL_5H")
    RL_STR=" ${DIM}|${RESET} 5h:${COLOR}${RL_5H%.*}%${RESET}"
fi
if [ -n "$RL_7D" ]; then
    COLOR=$(rl_color "$RL_7D")
    RL_STR="${RL_STR} 7d:${COLOR}${RL_7D%.*}%${RESET}"
fi

echo -e "[${MODEL}] ctx:${PCT}% ${COST_FMT}${RL_STR}"
