#!/usr/bin/env bash
# Apply the Supabase schema manually using psql.
# Useful when SUPABASE_DB_URL is available but the pipeline's auto-migration
# path isn't working (e.g. firewall restrictions, no psycopg2 installed).
#
# Usage:
#   SUPABASE_DB_URL=postgresql://... bash scripts/apply_schema.sh
#   OR with .env:
#   bash scripts/apply_schema.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  set -a; source "$ROOT/.env"; set +a
fi

if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
  echo "❌  SUPABASE_DB_URL is not set."
  exit 1
fi

echo "⚙️  Applying schema to Supabase project…"
psql "$SUPABASE_DB_URL" -f "$ROOT/scripts/schema.sql"
echo "✅  Schema applied."
