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

## Keep a teammate's local database current

After every `git pull`, run this one command before starting the server:

```bash
./database/ensure_current.sh --sync
```

The command compares the checked-out `schema.sql` and `seed.sql` fingerprints
with a marker recorded inside MySQL. If the local database already matches, it
does nothing. If it is missing or stale, it rebuilds `missubibi` from the
checked-out Mitsubishi snapshot. The rebuild is intentionally explicit because
it drops and recreates the local database.

For a one-command macOS/Linux startup that checks the database first:

```bash
./start-local.sh --sync-db
```

For Windows PowerShell:

```powershell
.\database\ensure_current.ps1 -Sync
.\start-local.ps1 -SyncDatabase
```

The import marker is excluded from future database exports, so it never becomes
part of the source data or changes the shared seed dump.

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
