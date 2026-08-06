# Deployment Guide (Production)

## Architecture

```
[Staff browsers] ── HTTPS ──▶ nginx ──▶ frontend static files
                                 └────▶ backend :8000 (REST + WebSocket)
backend ──▶ PostgreSQL, Redis
master PC worker ──▶ Redis (queue) + PostgreSQL (results) + Chrome/ChatGPT
```

## HTTPS

Terminate TLS at nginx (or any reverse proxy). Example with Let's Encrypt:

```nginx
server {
    listen 443 ssl;
    server_name ai.yourcompany.com;
    ssl_certificate     /etc/letsencrypt/live/ai.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai.yourcompany.com/privkey.pem;
    client_max_body_size 100M;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;   # WebSocket
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 600s;
    }
    location / { root /var/www/aiauto; try_files $uri /index.html; }
}
```

Set `CORS_ORIGINS=https://ai.yourcompany.com` in `.env`.

## Security checklist

- [ ] `SECRET_KEY` is a unique 64+ char random string
- [ ] PostgreSQL and Redis are **not** exposed to the internet
      (bind to the LAN / VPN between server and master PC only)
- [ ] HTTPS everywhere; HTTP redirected
- [ ] Admin password rotated after first login
- [ ] GitHub token is fine-grained, read-only, single-repo
- [ ] Backups directory included in your off-machine backup routine
- [ ] `UPDATE_AUTO_RESTART=true` only when a service manager restarts the app

Notes: JWTs are sent in the `Authorization` header (no cookies), which
neutralises classic CSRF; SQL injection is prevented by SQLAlchemy bound
parameters; XSS is mitigated by React's escaping plus API-side validation;
rate limiting and audit logging are built in.

## Running as services

**Docker:** `restart: unless-stopped` is already configured; the one-click
updater's auto-restart relies on this policy. The backend image is built
from the **repo root** (`context: .`, `dockerfile: backend/Dockerfile`) so
the container mirrors the repository layout and the updater operates on
the right tree (`AIAUTO_ROOT=/app` is set in the image). If you deploy
with a custom layout, always set `AIAUTO_ROOT` to the directory that
contains `VERSION` — the updater refuses to run otherwise.

**systemd (native Linux):**

```ini
[Unit]
Description=AIAuto backend
After=network.target postgresql.service redis.service

[Service]
WorkingDirectory=/opt/aiauto/backend
ExecStart=/opt/aiauto/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
User=aiauto

[Install]
WantedBy=multi-user.target
```

**Windows master PC:** NSSM service for the worker (see INSTALLATION.md);
put `start_master_chrome.bat` in the Startup folder so Chrome (with the
logged-in profile) comes back after reboots.

## Scaling & performance

- 50 users / 500+ prompts per day is easily handled by one server;
  the bottleneck is the single ChatGPT session (one generation at a time).
- `MAX_CONCURRENT_JOBS` stays at 1 for one ChatGPT account. With
  `AI_PROVIDER=api` you can raise it safely.
- Redis persistence (`appendonly yes`) is enabled in docker-compose so the
  queue survives restarts.
- Old backups are pruned automatically (Admin → Settings → *Backups to keep*).

## Backups

- **Automatic:** every one-click update zips the code and dumps the DB
  (when `pg_dump` is available) into `backups/` before touching anything.
- **Recommended:** nightly `pg_dump` + copy of `storage/` to another machine.
