#!/bin/bash
# Expose the robot web UI (port 8080) through a Cloudflare quick tunnel.
#
# ⚠️  SECURITY: a quick tunnel is PUBLIC. Anyone with the generated URL can drive
#    the robot and spend your Gemini quota. Set ROBOT_TOKEN in .env first so the
#    UI requires ?token=<value>, or prefer a private path (LAN / Tailscale / a
#    named tunnel with Cloudflare Access) instead of this.
set -e
cd "$(dirname "$0")"

WEB_PORT="${WEB_PORT:-8080}"

# Pick the binary for this machine's architecture (Raspberry Pi is arm64).
case "$(uname -m)" in
  aarch64|arm64) ARCH=arm64 ;;
  armv7l|armv6l) ARCH=arm ;;
  x86_64)        ARCH=amd64 ;;
  *) echo "Unsupported arch: $(uname -m)"; exit 1 ;;
esac

# Download cloudflared once (gitignored), then reuse it.
if [ ! -x ./cloudflared ]; then
  echo "Downloading cloudflared ($ARCH)..."
  wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}" -O cloudflared
  chmod +x cloudflared
fi

if [ -z "$ROBOT_TOKEN" ]; then
  echo "WARNING: ROBOT_TOKEN is not set — the tunnel URL will be unauthenticated."
fi

exec ./cloudflared tunnel --url "http://localhost:${WEB_PORT}"
