#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${GE360_VERSION:-0.2.0}"
ARCH="${GE360_ARCH:-amd64}"
DIST="$ROOT/dist"
PKG="$DIST/pkgroot"
APP_ROOT="$PKG/opt/ge360-analitica"
PLUGIN_ROOT="$APP_ROOT/chatgpt-plugin"

if [[ ! -x "$DIST/ge360-analitica" ]]; then
  echo "Manca $DIST/ge360-analitica: compila prima il binario PyInstaller." >&2
  exit 1
fi

if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  echo "Manca frontend/dist: esegui prima npm run build." >&2
  exit 1
fi

rm -rf "$PKG"
mkdir -p   "$APP_ROOT/bin"   "$APP_ROOT/www"   "$PLUGIN_ROOT/mcp_server"   "$PLUGIN_ROOT/skills/ge360-analitica"   "$PLUGIN_ROOT/scripts"   "$PKG/usr/bin"   "$PKG/usr/share/applications"   "$PKG/lib/systemd/system"   "$PKG/etc/ge360-analitica"   "$PKG/DEBIAN"

install -m 0755 "$DIST/ge360-analitica" "$APP_ROOT/bin/ge360-analitica"
cp -a "$ROOT/frontend/dist/." "$APP_ROOT/www/"

cp "$ROOT/plugin.json" "$PLUGIN_ROOT/plugin.json"
cp "$ROOT/mcp.json" "$PLUGIN_ROOT/mcp.json"
cp "$ROOT/mcp_server/server.py" "$PLUGIN_ROOT/mcp_server/server.py"
cp "$ROOT/mcp_server/requirements.txt" "$PLUGIN_ROOT/mcp_server/requirements.txt"
cp "$ROOT/skills/ge360-analitica/SKILL.md" "$PLUGIN_ROOT/skills/ge360-analitica/SKILL.md"
cp "$ROOT/scripts/run-mcp.sh" "$PLUGIN_ROOT/scripts/run-mcp.sh"
cp "$ROOT/scripts/setup-chatgpt-plugin.sh" "$PLUGIN_ROOT/scripts/setup-chatgpt-plugin.sh"
chmod 0755 "$PLUGIN_ROOT/scripts/"*.sh

ln -s /opt/ge360-analitica/bin/ge360-analitica "$PKG/usr/bin/ge360-analitica"

install -m 0755 "$ROOT/packaging/linux/ge360-open" "$PKG/usr/bin/ge360-open"
install -m 0755 "$ROOT/packaging/linux/ge360-chatgpt-setup" "$PKG/usr/bin/ge360-chatgpt-setup"
install -m 0644 "$ROOT/packaging/linux/ge360-analitica.desktop"   "$PKG/usr/share/applications/ge360-analitica.desktop"
install -m 0644 "$ROOT/packaging/linux/ge360-analitica.service"   "$PKG/lib/systemd/system/ge360-analitica.service"
install -m 0640 "$ROOT/packaging/linux/ge360.env"   "$PKG/etc/ge360-analitica/ge360.env"

cat > "$PKG/DEBIAN/control" <<EOF
Package: ge360-analitica
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: GE360
Depends: adduser
Recommends: xdg-utils
Description: GE360 Analitica self-hosted marketing dashboard
 Dashboard locale per WordPress, Google, Meta e ChatGPT MCP.
 Include backend standalone, frontend web, sync automatico e plugin ChatGPT.
EOF

cat > "$PKG/DEBIAN/conffiles" <<EOF
/etc/ge360-analitica/ge360.env
EOF

install -m 0755 "$ROOT/packaging/linux/postinst" "$PKG/DEBIAN/postinst"
install -m 0755 "$ROOT/packaging/linux/prerm" "$PKG/DEBIAN/prerm"

DEB="$DIST/ge360-analitica_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$PKG" "$DEB"

PORTABLE="$DIST/ge360-analitica-linux-${ARCH}-${VERSION}.tar.gz"
tar -C "$PKG" -czf "$PORTABLE"   opt/ge360-analitica   etc/ge360-analitica   lib/systemd/system/ge360-analitica.service   usr/bin/ge360-analitica   usr/bin/ge360-open   usr/bin/ge360-chatgpt-setup   usr/share/applications/ge360-analitica.desktop

echo "$DEB"
echo "$PORTABLE"
