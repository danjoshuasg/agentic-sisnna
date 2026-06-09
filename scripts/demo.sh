#!/usr/bin/env bash
# Demo pública en un comando: levanta el server local + túnel Cloudflare e imprime el LINK.
# Uso:  bash scripts/demo.sh   (o:  make demo).  Ctrl-C apaga todo.
set -euo pipefail
cd "$(dirname "$0")/.."
VENV=.venv

command -v cloudflared >/dev/null || { echo "Falta cloudflared → brew install cloudflared"; exit 1; }

echo "▸ Levantando server (FastAPI :8000)…"
"$VENV/bin/uvicorn" app.main:app --port 8000 --log-level warning > /tmp/sisnna_server.log 2>&1 &
SRV=$!
sleep 6

echo "▸ Abriendo túnel público…"
: > /tmp/sisnna_tunnel.log
cloudflared tunnel --url http://localhost:8000 > /tmp/sisnna_tunnel.log 2>&1 &
TUN=$!
trap 'kill "$SRV" "$TUN" 2>/dev/null || true' EXIT INT TERM

URL=""
for _ in $(seq 1 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/sisnna_tunnel.log | head -1 || true)
  [ -n "$URL" ] && break
  sleep 2
done

echo
echo "══════════════════════════════════════════════════════════════"
if [ -n "$URL" ]; then
  echo "  LINK PARA TU PM:   $URL"
else
  echo "  (no salió la URL; revisa /tmp/sisnna_tunnel.log)"
fi
echo "══════════════════════════════════════════════════════════════"
echo "  Déjalo abierto mientras tu PM prueba. Ctrl-C para apagar todo."
echo
wait
