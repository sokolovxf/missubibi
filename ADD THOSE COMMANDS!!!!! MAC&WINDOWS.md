macOS/zsh, let's make two simple commands:
- mbstart → starts both backend + frontend
- mbreload → stops both and starts them again
They will only affect Missubibi, not LH1.
1. Add these to ~/.zshrc
Open VS Code or Terminal and add:
mbstart() {
    echo "=== Starting Missubibi ==="

    cd /Users/mac/Documents/Missubibi/backend || return
    uv run uvicorn app.main:app --reload --port 8100 &

    cd /Users/mac/Documents/Missubibi/frontend || return
    npm run dev
}
And:
mbreload() {
    echo "=== Reloading Missubibi ==="

    pkill -f "uvicorn app.main:app.*8100" 2>/dev/null
    pkill -f "vite.*5174" 2>/dev/null

    sleep 2

    mbstart
}
Then reload your shell:
source ~/.zshrc
2. Keep the shared Mitsubishi data current
After `git pull`, run this from the repository root before starting the app:
```bash
./database/ensure_current.sh --sync
```
It checks the repository fingerprint recorded in the local MySQL database and
rebuilds only when the local data is missing or stale. The rebuild uses the
current `database/schema.sql` and `database/seed.sql` from GitHub.

3. From now on
Start everything with:
mbstart
You'll have:
Frontend → http://localhost:5174
Backend  → http://127.0.0.1:8100
To restart both:
mbreload
⚠️ One important detail
mbreload uses pkill specifically matching 8100 and 5174, so it won't intentionally kill your LH1 servers on 8000/5173.
Once you've added these, we can move directly to connecting App.tsx to the FastAPI API.










create the same one for windows













Absolutely. For Windows PowerShell, we can make the same two commands.
1. mbstart — start both
Open your PowerShell profile:
notepad $PROFILE
If PowerShell says the file doesn't exist, run:
New-Item -Path $PROFILE -ItemType File -Force
notepad $PROFILE
Add:
function mbstart {
    Write-Host "=== Starting Missubibi ==="

    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\path\to\Missubibi\backend'; uv run uvicorn app.main:app --reload --port 8100"

    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\path\to\Missubibi\frontend'; npm run dev"
}
Important: replace:
C:\path\to\Missubibi
with the actual location where your collaborator cloned the repository.
For example:
C:\Users\John\Documents\Missubibi
2. mbreload — restart both
Add this underneath:
function mbreload {
    Write-Host "=== Reloading Missubibi ==="

    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match "uvicorn.*8100" -or
            $_.CommandLine -match "vite.*5174"
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force
        }

    Start-Sleep -Seconds 2

    mbstart
}
Then close and reopen PowerShell. To sync the database and start both apps from
the cloned repository, run:
```powershell
.\start-local.ps1 -SyncDatabase
```

For Git Bash on Windows, the equivalent is:
```bash
./start-local.sh --sync-db
```
You can now use:
mbstart
to launch:
Frontend → http://localhost:5174
Backend  → http://127.0.0.1:8100
and:
mbreload
to restart both.
One improvement for your GitHub collaborators
Since everyone will clone Missubibi into a different Windows folder, I actually recommend we make the Windows command automatically detect the project location instead of hardcoding C:\Users\John\Documents\Missubibi.
We can do the same for macOS too, so collaborators can literally just run:
mbstart
regardless of where they cloned the repo.
