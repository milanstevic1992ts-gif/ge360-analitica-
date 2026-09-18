#!/usr/bin/env bash
set -euo pipefail

VENV="${GE360_MCP_VENV:-$HOME/.local/share/ge360-analitica/mcp-venv}"
SERVER="${PLUGIN_ROOT:?PLUGIN_ROOT non definito}/mcp_server/server.py"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "GE360 MCP non configurato. Esegui scripts/setup-chatgpt-plugin.sh dalla repo." >&2
  exit 1
fi

exec "$VENV/bin/python" "$SERVER"
