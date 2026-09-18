#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE_DIR="$ROOT/agent_bridge"
VENV_DIR="$BRIDGE_DIR/.venv"
SOCKET_PATH="$ROOT/data/ge360-codex.sock"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/ge360-codex-bridge.service"

if ! command -v codex >/dev/null 2>&1; then
  echo "Codex CLI non trovato."
  echo "Installa Codex CLI e accedi con il tuo account ChatGPT prima di continuare."
  exit 1
fi

mkdir -p "$ROOT/data" "$SERVICE_DIR"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$BRIDGE_DIR/requirements.txt"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=GE360 Codex CLI Bridge
After=default.target

[Service]
Type=simple
WorkingDirectory=$BRIDGE_DIR
Environment=GE360_PROJECT_DIR=$ROOT
Environment=GE360_CODEX_TIMEOUT=120
ExecStartPre=/usr/bin/rm -f $SOCKET_PATH
ExecStart=$VENV_DIR/bin/uvicorn app:app --uds $SOCKET_PATH
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ge360-codex-bridge.service

echo
echo "GE360 Codex Bridge installato."
echo "Socket: $SOCKET_PATH"
echo "Stato: systemctl --user status ge360-codex-bridge.service"
