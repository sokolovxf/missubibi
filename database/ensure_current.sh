#!/bin/bash
# ---------------------------------------------------------------
# database/ensure_current.sh
#
# Verifies that the local MySQL database was imported from the same
# schema.sql + seed.sql files in this checkout. Use --sync to rebuild
# it automatically when the recorded repository fingerprint differs.
# ---------------------------------------------------------------
set -e

DB_NAME="missubibi"
DB_USER="root"
MODE="check"
if [ "${1:-}" = "--sync" ] || [ "${1:-}" = "--refresh" ]; then
  MODE="sync"
elif [ "${1:-}" != "" ] && [ "${1:-}" != "--check" ]; then
  echo "Usage: $0 [--check|--sync]"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/schema.sql"
SEED_FILE="$SCRIPT_DIR/seed.sql"

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

if [ ! -f "$SCHEMA_FILE" ] || [ ! -f "$SEED_FILE" ]; then
  echo "ERROR: schema.sql or seed.sql not found in database/."
  exit 1
fi

EXPECTED_SCHEMA_SHA256="$(hash_file "$SCHEMA_FILE")"
EXPECTED_SEED_SHA256="$(hash_file "$SEED_FILE")"

if ! command -v mysql >/dev/null 2>&1; then
  echo "ERROR: mysql was not found on PATH. Install MySQL and try again."
  exit 1
fi

METADATA="$(mysql -u "$DB_USER" -p -N -B "$DB_NAME" \
  -e "SELECT schema_sha256, seed_sha256 FROM _missubibi_seed_metadata WHERE metadata_id = 1" || true)"

CURRENT_SCHEMA_SHA256="$(printf '%s\n' "$METADATA" | awk '{print $1}')"
CURRENT_SEED_SHA256="$(printf '%s\n' "$METADATA" | awk '{print $2}')"

if [ "$CURRENT_SCHEMA_SHA256" = "$EXPECTED_SCHEMA_SHA256" ] && [ "$CURRENT_SEED_SHA256" = "$EXPECTED_SEED_SHA256" ]; then
  echo "Local '$DB_NAME' is current with this checkout."
  echo "  seed fingerprint: $CURRENT_SEED_SHA256"
  exit 0
fi

echo "Local '$DB_NAME' is missing or out of date with this checkout."
if [ -n "$CURRENT_SEED_SHA256" ]; then
  echo "  database seed: $CURRENT_SEED_SHA256"
else
  echo "  database seed: no repository fingerprint recorded"
fi
echo "  checkout seed: $EXPECTED_SEED_SHA256"

if [ "$MODE" = "sync" ]; then
  echo "==> Rebuilding '$DB_NAME' from the checked-out schema and seed..."
  "$SCRIPT_DIR/import_db.sh" --yes
  exit 0
fi

echo "Run './database/ensure_current.sh --sync' to refresh the local database."
exit 2
