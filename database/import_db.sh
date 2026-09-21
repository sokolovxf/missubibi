#!/bin/bash
# ---------------------------------------------------------------
# database/import_db.sh
#
# Rebuilds your local `missubibi` MySQL database from the repo's
# database/schema.sql + database/seed.sql.
#
# Run this AFTER `git pull`, before you start working, so you're
# always working from the latest shared data.
#
# WARNING: drops and recreates your local `missubibi` database.
# Export first if you have local changes you haven't pushed yet.
# ---------------------------------------------------------------
set -e

AUTO_APPROVE=0
if [ "${1:-}" = "--yes" ] || [ "${1:-}" = "-y" ]; then
  AUTO_APPROVE=1
elif [ "${1:-}" != "" ]; then
  echo "Usage: $0 [--yes]"
  exit 2
fi

DB_NAME="missubibi"
DB_USER="root"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/schema.sql"
SEED_FILE="$SCRIPT_DIR/seed.sql"

if [ ! -f "$SCHEMA_FILE" ] || [ ! -f "$SEED_FILE" ]; then
  echo "ERROR: schema.sql or seed.sql not found in database/."
  echo "Did you run 'git pull' first?"
  exit 1
fi

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

if [ "$AUTO_APPROVE" -ne 1 ]; then
  echo "WARNING: this will DROP and recreate the local '$DB_NAME' database."
  printf "Type REPLACE to continue: "
  read -r CONFIRM
  if [ "$CONFIRM" != "REPLACE" ]; then
    echo "Cancelled."
    exit 1
  fi
fi

SCHEMA_SHA256="$(hash_file "$SCHEMA_FILE")"
SEED_SHA256="$(hash_file "$SEED_FILE")"

echo "==> Dropping and recreating local '$DB_NAME'..."
mysql -u "$DB_USER" -p -e "DROP DATABASE IF EXISTS $DB_NAME; CREATE DATABASE $DB_NAME;"

echo "==> Loading schema..."
mysql -u "$DB_USER" -p "$DB_NAME" < "$SCHEMA_FILE"

echo "==> Loading data (this can take a minute for 272k+ rows)..."
mysql -u "$DB_USER" -p "$DB_NAME" < "$SEED_FILE"

echo "==> Recording the imported repository snapshot..."
mysql -u "$DB_USER" -p "$DB_NAME" <<SQL
CREATE TABLE IF NOT EXISTS _missubibi_seed_metadata (
  metadata_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
  schema_sha256 CHAR(64) NOT NULL,
  seed_sha256 CHAR(64) NOT NULL,
  imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
REPLACE INTO _missubibi_seed_metadata (metadata_id, schema_sha256, seed_sha256)
VALUES (1, '$SCHEMA_SHA256', '$SEED_SHA256');
SQL

echo ""
echo "Done. Local '$DB_NAME' is now up to date with the repo."
echo "  seed fingerprint: $SEED_SHA256"
