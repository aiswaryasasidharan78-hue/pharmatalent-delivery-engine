#!/usr/bin/env bash
# Run the PharmaTalent pipeline from repo root.
# Usage: bash scripts/run_pipeline.sh [--fixture]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── Validate required env vars ─────────────────────────────────────────────
check_var() {
  if [[ -z "${!1:-}" ]]; then
    echo "❌  Required env var $1 is not set. Copy .env.example → .env and fill in values."
    exit 1
  fi
}

if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

check_var APIFY_TOKEN
check_var OPENROUTER_API_KEY
check_var SUPABASE_URL
check_var SUPABASE_SERVICE_ROLE_KEY

if [[ -z "${AI_ARK_TOKEN:-}" && -z "${PROSPEO_API_KEY:-}" ]]; then
  echo "❌  At least one of AI_ARK_TOKEN or PROSPEO_API_KEY must be set."
  exit 1
fi

# ── Activate venv if present ───────────────────────────────────────────────
if [[ -d .venv/bin ]]; then
  source .venv/bin/activate
fi

echo "🚀  Starting PharmaTalent pipeline…"
python -m app.main "$@"
