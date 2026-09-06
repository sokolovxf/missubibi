#!/bin/bash
# ---------------------------------------------------------------
# database/export_db.sh
#
# Exports your local `missubibi` MySQL database into:
#   database/schema.sql  — structure only (tables, no rows)
#   database/seed.sql    — data only (INSERTs, no structure)
#
# Run this BEFORE pushing your changes back to the team repo.
# Prompts for your local MySQL root password (not stored anywhere).
# ---------------------------------------------------------------
set -e

DB_NAME="missubibi"
DB_USER="root"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/schema.sql"
SEED_FILE="$SCRIPT_DIR/seed.sql"

echo "==> Exporting schema (structure only)..."
mysqldump -u "$DB_USER" -p \
  --no-data \
  --routines \
  --triggers \
  --set-gtid-purged=OFF \
  --default-character-set=utf8mb4 \
  "$DB_NAME" > "$SCHEMA_FILE"

echo "==> Exporting seed data (rows only)..."
mysqldump -u "$DB_USER" -p \
  --no-create-info \
  --no-create-db \
  --skip-triggers \
  --single-transaction \
  --set-gtid-purged=OFF \
  --default-character-set=utf8mb4 \
  "$DB_NAME" > "$SEED_FILE"

SCHEMA_SIZE=$(du -h "$SCHEMA_FILE" | cut -f1)
SEED_SIZE=$(du -h "$SEED_FILE" | cut -f1)

echo ""
echo "Done."
echo "  database/schema.sql  ($SCHEMA_SIZE)"
echo "  database/seed.sql    ($SEED_SIZE)"
echo ""
echo "Now run:"
echo "  git add database/schema.sql database/seed.sql"
echo "  git commit -m \"Update DB\""
echo "  git push"
