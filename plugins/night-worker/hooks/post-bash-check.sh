#!/usr/bin/env bash
# post-bash-check.sh
# Hook that runs after each Bash tool use during night-worker sessions.
# Checks for common failure patterns and logs them to the night-worker report.

set -euo pipefail

REPORT_FILE="night-worker-report.md"

# Read tool result from stdin (provided by Claude Code hook system)
INPUT=$(cat)

# Check for common error patterns
if echo "$INPUT" | grep -qiE '(error|failed|exception|fatal|panic)'; then
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "## Warning detected at ${TIMESTAMP}" >> "$REPORT_FILE"
  echo '```' >> "$REPORT_FILE"
  echo "$INPUT" | tail -20 >> "$REPORT_FILE"
  echo '```' >> "$REPORT_FILE"
  echo "" >> "$REPORT_FILE"
fi
