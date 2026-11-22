#!/usr/bin/env bash
# Build the web app and serve web/dist on the local network (port 4173).
set -euo pipefail
cd "$(dirname "$0")/../web"
[ -d node_modules ] || npm ci
npm run build
LAN=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<lan-address>")
echo "Local: http://localhost:4173"
echo "LAN:   http://${LAN}:4173"
exec npx vite preview --host --port 4173 --strictPort
