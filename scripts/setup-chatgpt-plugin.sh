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
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet ge360-analitica.service 2>/dev/null; then
  echo "GE360 Analitica è già attivo come servizio systemd."
else
  echo "Verifica che GE360 Analitica sia attivo su http://127.0.0.1:8788"
fi
echo
echo "Ora importa questa cartella come plugin locale in ChatGPT Desktop:"
echo "  $ROOT"
echo
echo "Il plugin interroga GE360 in sola lettura tramite http://127.0.0.1:8788."
