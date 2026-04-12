#!/usr/bin/env bash
# queue-server.sh
# Placeholder MCP server for the night-worker task queue.
# Replace this with a real implementation (e.g. Node.js, Python) that
# speaks the MCP protocol over stdio.

set -euo pipefail

echo "night-worker queue server starting..." >&2
echo "Log directory: ${NIGHT_WORKER_LOG_DIR:-./logs}" >&2

# Placeholder -- a real server would read JSON-RPC from stdin and respond.
exec cat
