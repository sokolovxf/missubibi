# Session Handoff 2 — Real Data Wired In, Backend Confirmed Working

**Repo:** `/Users/mac/Documents/Missubibi`
**Date:** 2026-09-06 (continuation of the day's earlier `session.md` notes)

> Consolidating into the `SESSION_HANDOFF` series as planned — this
> picks up right after `SESSION_HANDOFF1.md` and after the earlier
> `session.md` draft from the same day. Recommend deleting/merging
> `session.md` once this is reviewed, so there's one consistent series.

---

## Where things stood coming into this session

- `app/data/sales_data.py` had just been written to replace
  `mock_data.py` as the backend's data source — real column mapping
  finalized, dedup logic applied, `forecast_units` implemented as a
  temporary lag-1 placeholder (see that file's docstring for the
  reasoning — it is explicitly not a real forecast yet).
- The one-line import swap in `analytics.py` had been made
  (`from app.data.sales_data import get_sales_data`).
- None of it had actually been run successfully yet.

## What we fixed this session

### 1. Backend port conflict avoided
- Backend now explicitly runs on **port 8100**, not 8000 — 8000 is
  reserved for the separate `lh1` project. Always start it with:
  ```bash
  cd /Users/mac/Documents/Missubibi/backend
  uv run uvicorn app.main:app --reload --port 8100
  ```

### 2. Missing `pymysql` driver
- The backend crashed on startup with `ModuleNotFoundError: No module
  named 'pymysql'` — it had been identified as a to-do earlier but
  never actually installed.
- Fixed with `uv add pymysql` run from inside `backend/`.

### 3. Relative-path `cd` failures
- Several `cd backend` attempts silently failed ("no such file or
  directory") because the shell wasn't already inside the repo, which
  then made every subsequent command run from the wrong directory and
  fail in confusing ways (`ModuleNotFoundError: No module named 'app'`).
- Always use the absolute path: `cd /Users/mac/Documents/Missubibi/backend`.

### 4. `.env.example` briefly contained the real local password
- Caught and fixed before it caused problems — confirmed the GitHub
  repo is **private**, and `.env.example` was reverted back to a
  placeholder. Worth double-checking this hasn't regressed before any
  future push.

### 5. Root cause of the persistent 500 errors: `year_month` is a MySQL reserved word
- Both `/api/dashboard` and `/api/sales` were returning `500 Internal
  Server Error`. The uvicorn traceback showed a MySQL `1064` syntax
  error pointing at the very start of the `SELECT` list in
  `sales_data.py`'s CTE query.
- Ruled out, in order: MySQL version compatibility (server is `26.7.0`,
  a very recent release that fully supports CTEs and window
  functions — confirmed directly via `mysql -u root -pmb -e "SELECT
  VERSION();"`), a second/rogue MySQL process on port 3306 (`lsof -i
  :3306` showed exactly one `mysqld`, and the Python process was
  connected to that same one), and hidden/non-ASCII characters in the
  query text (checked byte-by-byte — clean).
- Actual cause: **`year_month` is one of MySQL's reserved compound
  `INTERVAL` unit specifiers** (same family as `DAY_HOUR`,
  `HOUR_MINUTE`), so it can't be used unquoted as a column identifier.
  Confirmed directly with `mysql -u root -pmb -e "SELECT 1 AS
  year_month;"`, which throws the identical 1064 error.
- **Fix:** wrapped both references to `year_month` in backticks
  (`` `year_month` ``) inside `sales_data.py`'s `_QUERY` string.

### 6. Forecast placeholder bug: crossing customers
- The lag-1 `forecast_units` placeholder was grouped by `product`
  only. Since a product can have multiple customers in the same month,
  `shift(1)` could pull the "previous" value from a *different*
  customer's row in the same month instead of the same customer's
  prior month.
- **Fix:** now groups and sorts by `["product", "customer"]` together
  before shifting, so each customer's placeholder forecast only ever
  comes from that same customer's own prior month.

### 7. Git push rejected
- A `mbsave` run was rejected with `[rejected] main -> main (fetch
  first)` — the remote had a commit (a teammate's `SESSION_HANDOFF1.md`
  push) that wasn't pulled locally yet.
- **Not yet resolved** — needs `git pull --rebase origin main` before
  the next push. Flagging this explicitly since it's the exact "last
  push wins" risk called out in `SESSION_HANDOFF1.md`, just showing up
  as a hard rejection instead of a silent overwrite this time (which is
  actually the safer outcome).

## Confirmed working

Both endpoints now return real data pulled from the actual 272k-row
dataset instead of mock data:

- `GET /api/dashboard` → `total_units: 870623`, `total_revenue:
  ~10.88B THB`, `top_product: "PLC Q"`, `forecast_accuracy: 19.31`
  (accuracy figure is only as meaningful as the placeholder forecast
  behind it — not a real SARIMA result yet).
- `GET /api/sales` → real month-by-month series per product/customer.

## New issue found, not yet fixed

- **Trailing `\r` in `year_month` values.** The API response shows
  month values like `"2021-04\r"` instead of `"2021-04"`. This strongly
  suggests Windows-style line endings (`\r\n`) got baked into that
  column during the original data import/export. Doesn't currently
  break grouping (the `\r` is just part of the string consistently),
  but it will break anything downstream that expects a clean
  `YYYY-MM` string — date parsing on the frontend, chart axis labels,
  any string comparison against a clean value. Should be stripped
  either in the SQL (`TRIM(...)` or `REPLACE(year_month, '\r', '')`)
  or in `sales_data.py` with `.str.strip()` on the column after
  `pd.read_sql`.

## Still open (carried over, unchanged)

- [ ] Team decision: `sales_order_date` (currently all `0000-00-00`,
      unusable) vs `year_month` as the real time index for SARIMA.
- [ ] Team confirmation of the dedup key used in `sales_data.py` — it's
      a judgment call, not verified against how the source system
      generates orders.
- [ ] Wire real forecasts: call `sarima_engine.run_forecast()` as a
      cached/background step (40–90s per series, too slow inline),
      replacing the lag-1 placeholder.
- [ ] Resolve the pending `git pull --rebase` before the next push.

## Next steps — finish wiring end-to-end, publish DB for the team

Current stated priority: get SQL → backend → frontend fully wired, and
make the database easily downloadable from GitHub so both partners can
start working from it.

1. ✅ **Frontend already pointed at the real backend.** `App.tsx` was
   already fetching from `http://127.0.0.1:8100` on all four endpoints
   (`/api/dashboard`, `/api/sales`, `/api/products`, `/api/insights`) —
   no change needed. CORS `allow_origins` in `main.py` allows `5174`,
   confirmed to match the actual Vite dev server port.
2. ✅ **`year_month` `\r` bug fixed.** Turned out to be more than a
   hygiene issue — `App.tsx` builds `new Date(\`${item.month}-01\`)`
   for the revenue chart's month-axis labels, so the trailing `\r`
   was producing `Invalid Date` in the UI. Fixed with `.str.strip()`
   on the `month` column in `sales_data.py`, right after `pd.read_sql`.
3. ✅ **Real `schema.sql` / `seed.sql` exported and pushed.**
   `database/export_db.sh` / `import_db.sh` needed `chmod +x` first
   (permissions don't survive an `mv` from Downloads). Export produced
   `schema.sql` (8.0K) and `seed.sql` (80M, real 272k+ row dump).
   GitHub warned that `seed.sql` (67MB compressed) exceeds their
   recommended 50MB soft limit — under the 100MB hard limit for now,
   but worth moving to Git LFS if the dataset keeps growing.
4. ✅ **`.env` confirmed safe.** `git status` showed no trace of
   `backend/.env` before pushing.
5. ✅ **`database/README.md` written and pushed** — covers first-time
   setup, the export-before-push step, and the "git can't merge two
   DB dumps" warning with the pull-before-edit / announce-before-push
   protocol.
6. ✅ **Git divergence resolved.** Hit an actual `[rejected] ...
   non-fast-forward` (branches had diverged 3 vs 2 commits — a
   teammate had pushed in the meantime). Also caught that `mbsave`
   prints "✓ saved to GitHub" even when the underlying push fails —
   it isn't checking the push's exit code, so don't trust that message
   at face value; always read the actual git output above it. Fixed
   with `git pull --rebase origin main` then `git push`.
7. **Teammate onboarding — not yet confirmed done.** Partner still
   needs to `git pull` and follow the new `database/README.md`
   (`import_db.sh` → copy `.env.example` → `uv add pymysql` → run on
   port 8100).
