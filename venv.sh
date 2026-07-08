#!/bin/bash
# Set up the Python venv, install deps, and load .env into the environment.
# Usage:  source venv.sh
set -e
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo ""

[ -f .env ] || cp .env.example .env

# Load .env safely (handles values with spaces/quotes, unlike `export $(cat .env)`).
set -a
# shellcheck disable=SC1091
. ./.env
set +a

echo "Environment loaded. GEMINI_API_KEY set: $([ -n "$GEMINI_API_KEY" ] && echo yes || echo NO)"
[ -z "$ROBOT_TOKEN" ] && echo "Tip: set ROBOT_TOKEN in .env to require auth on the web UI."
exec bash
