# Database Setup

## First time setup (or after pulling new DB changes)

1. Make sure MySQL is installed and running locally.
2. From the repo root, run:
   ```bash
   ./database/import_db.sh
   ```
   This will prompt for your local MySQL root password and rebuild
   the `missubibi` database from `schema.sql` + `seed.sql`.
3. Copy the backend env template and fill in your own local password:
   ```bash
   cp backend/.env.example backend/.env
   ```
   Edit `backend/.env` and replace `YOUR_PASSWORD_HERE` with your
   local MySQL root password.
4. Install the MySQL driver if you haven't already:
   ```bash
   cd backend && uv add pymysql
   ```
5. Run the backend on port 8100 (not 8000 — that's reserved for a
   different project):
   ```bash
   uv run uvicorn app.main:app --reload --port 8100
   ```

## Before you push changes to the database

If you've changed any data locally that the team needs, run:
```bash
./database/export_db.sh
```
This regenerates `schema.sql` and `seed.sql` from your local database.
Then commit and push both files as usual.

## ⚠️ Important: this workflow does NOT merge database changes

`schema.sql` and `seed.sql` are full dumps, not incremental changes.
**Git cannot merge two different versions of these files** — whoever
pushes last will silently overwrite whatever the other person changed,
with no conflict warning.

To avoid losing work:
- **Pull and re-import before you start editing the database** (`git
  pull` then `./database/import_db.sh`), so you're always starting
  from the latest shared version.
- **Announce in the team chat before you push** a new `seed.sql`, so
  nobody else is mid-edit when you overwrite it.
