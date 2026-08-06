# One-Click GitHub Update System

Once configured, updating the whole platform is two clicks in
**Admin → Update** — no file uploads, no FTP, no manual SQL.

## One-time setup

1. Open **Admin → Update**.
2. Enter repository (`owner/repo`), branch (e.g. `main`), and a GitHub
   token. A fine-grained PAT with read-only **Contents** permission on that
   single repository is enough.
3. **Save Configuration.** The token is stored encrypted (Fernet, keyed from
   `SECRET_KEY`) in the database. It is never returned by the API again —
   the UI only shows *"already saved"*.

## Check for Update

Click **🔍 Check for Update**. The server asks the GitHub API for the
branch head and compares it with the installed commit, then shows:

- new version number (from the repo's `VERSION` file)
- how many commits behind you are
- each commit's short SHA, message, author, and date

## Update Now

Click **⬆ Update Now** (enabled only when an update exists). Pipeline:

| Step | What happens | On failure |
|---|---|---|
| 1. Backup | zip of all updatable code + `pg_dump` of the DB into `backups/` | update aborts, nothing changed |
| 2. Download | branch tarball fetched from GitHub (path-traversal-safe extraction) | abort → **auto-rollback** |
| 3. Apply | new files copied over the installation — **protected paths skipped** | auto-rollback |
| 4. Migrate | `alembic upgrade head` runs automatically | auto-rollback of files |
| 5. Cache | application Redis cache keys cleared | auto-rollback |
| 6. Finish | installed commit recorded, old backups pruned, optional restart | — |

Live progress (step, %, log) streams to the page over WebSocket, and every
run is recorded in **Update History** with its backup file name.

## Protected paths — never overwritten

Defaults: `.env`, `config.php`, `storage/`, `uploads/`, `backups/`, `logs/`,
`frontend/node_modules/`. You can add more via the API
(`protected_paths` in `PUT /admin/update/config`); the critical entries
cannot be removed. Matching is by whole path segment, so `.env.example`
**is** updatable while `.env` is not.

## Automatic rollback

Any error after the backup — download failure, bad archive, migration
error — restores every backed-up file from the zip. Protected paths were
never touched, so user data and secrets survive both the update and the
rollback. The record is marked `rolled_back` in history.

If a migration fails, files are rolled back but the DB may need attention:
restore the `db_*.sql` dump from `backups/` if the migration was partially
applied (PostgreSQL runs DDL transactionally, so this is rare).

## Restart behaviour

With `auto_restart` on (default), the process exits ~2 s after a successful
update and the service manager (Docker `restart: unless-stopped`, systemd
`Restart=always`, or NSSM) brings it back on the new code. Turn it off if
you prefer manual restarts.

## Worker note

The master-computer worker gets code updates the same way when it runs from
the same checkout (e.g. a shared folder or by running the updater on that
machine). Restart the worker after updating the server.
