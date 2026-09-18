#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$HOME/.local/share/ge360-analitica"
VENV="$STATE_DIR/mcp-venv"

mkdir -p "$STATE_DIR"

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$ROOT/mcp_server/requirements.txt"

echo
echo "GE360 MCP pronto."
echo "Ambiente MCP: $VENV"
echo "API attesa: http://127.0.0.1:8788"
echo
echo "Avvia GE360 con:"
echo "  docker compose up -d --build"
echo
echo "Poi importa la cartella del repository come plugin locale in ChatGPT Desktop."
echo "Il plugin non legge una copia del database: interroga la API GE360 locale in sola lettura."
