# Security Overview

This document summarises the security measures built into AIAuto and the
results of the internal audit performed during development.

## Authentication & sessions

- Passwords hashed with **bcrypt** (cost 12); verification is constant-time.
- **JWT** access tokens (30 min) + refresh tokens (7 days), HS256 with a
  64-byte random `SECRET_KEY`.
- **Refresh rotation**: every refresh invalidates the old token (jti
  blacklist in Redis). Reuse of a rotated token is rejected.
- **Logout revocation**: the access token used to log out is blacklisted
  for its remaining lifetime. Revocation checks **fail secure** — if Redis
  is unreachable the token is rejected, not accepted.
- **Brute-force lockout**: 5 failed logins (configurable) lock the account
  for 15 minutes; failed attempts are audit-logged. Login endpoints also
  have a stricter per-IP rate limit.
- **API keys** are random 72-hex-char values stored only as SHA-256 hashes;
  the plain key is displayed exactly once.

## Authorization

- Role checks (`admin`/`staff`) are FastAPI dependencies on every admin
  route — including router-level dependencies so a new endpoint cannot
  accidentally ship unprotected.
- Staff can only read/cancel/retry **their own** prompts, files,
  notifications, schedules and API keys; cross-user access returns 404
  (existence is not leaked). Covered by automated tests.
- Staff cannot raise queue priority or see other users' data via any
  list endpoint (`all_users` is admin-only).

## Injection & web attacks

- **SQL injection**: all queries go through SQLAlchemy bound parameters;
  no string-built SQL anywhere.
- **XSS**: React escapes all rendered content; the API returns JSON with
  `X-Content-Type-Options: nosniff`, and responses are never reflected
  into HTML.
- **CSRF**: tokens travel in the `Authorization` header (no auth cookies),
  which neutralises classic CSRF. CORS is locked to configured origins.
- **Clickjacking**: `X-Frame-Options: DENY`.
- **SSRF**: the platform makes outbound requests only to configured
  endpoints (GitHub API, AI provider APIs, admin-configured webhook/
  Telegram). No user-supplied URLs are fetched.

## Files & paths

- Upload filenames are sanitised (basename only, safe character set,
  length-capped); files are stored under per-prompt directories with
  random prefixes.
- Every stored path is re-resolved and must remain inside the storage
  root (`is_relative_to` check) — path traversal returns an error.
  Backup names are validated the same way before restore.
- Per-file download authorization joins through the owning prompt.
- Upload size is capped (`MAX_UPLOAD_MB`) and total storage is capped
  (`STORAGE_LIMIT_GB`).

## Update system

- GitHub tokens are stored **encrypted** (Fernet keyed from SECRET_KEY)
  and never returned by any API after saving.
- Tarball extraction guards against path traversal and skips symlinks.
- Protected paths (`.env`, `storage/`, `uploads/`, `config.php`,
  `plugins/`, `backups/`) can never be overwritten by an update or a
  rollback, and the critical entries cannot be removed from the list.
- Every update takes a backup first and rolls back automatically on error.

## Secrets

- `.env` is git-ignored, update-protected, and auto-generated with a
  random SECRET_KEY on first run.
- No secrets are logged; the update config endpoint returns only
  `token_set: true/false`.

## Reporting

If you find a vulnerability, please contact the repository owner
directly rather than opening a public issue.
