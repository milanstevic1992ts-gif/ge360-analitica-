#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$ROOT/mcp_server/requirements.txt"

echo
echo "GE360 MCP pronto."
echo "Plugin root: $ROOT"
echo
echo "Ora importa questa cartella come plugin locale in ChatGPT Desktop."
echo "Il server MCP è in sola lettura e userà: $ROOT/data/ge360.db"
