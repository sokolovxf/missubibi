# Missubibi

## Run the current system

After cloning or pulling the repository, make sure the local MySQL snapshot is
the same version as the checked-out code and seed files:

```bash
./start-local.sh --sync-db
```

This verifies the repository fingerprints recorded in MySQL and refreshes the
`missubibi` database from `database/schema.sql` and `database/seed.sql` only
when the local database is missing or stale. It then starts the backend on
`http://127.0.0.1:8100` and the frontend on `http://localhost:5174`.

On Windows PowerShell:

```powershell
.\start-local.ps1 -SyncDatabase
```

If the database is already known to be current, use `./start-local.sh` or
`.\start-local.ps1` without the sync flag; the startup check will stop with a
clear refresh command if the local data does not match the repository.
