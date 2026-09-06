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

echo "==> Dropping and recreating local '$DB_NAME'..."
mysql -u "$DB_USER" -p -e "DROP DATABASE IF EXISTS $DB_NAME; CREATE DATABASE $DB_NAME;"

echo "==> Loading schema..."
mysql -u "$DB_USER" -p "$DB_NAME" < "$SCHEMA_FILE"

echo "==> Loading data (this can take a minute for 272k+ rows)..."
mysql -u "$DB_USER" -p "$DB_NAME" < "$SEED_FILE"

echo ""
echo "Done. Local '$DB_NAME' is now up to date with the repo."
